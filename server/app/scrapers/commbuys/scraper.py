"""Selenium automation for COMMBUYS (Massachusetts), open bids.

Flow: sign in (Sign In -> User ID / Password -> Sign In) -> the seller home page
-> the open-bids list (bidList.sda?status=Open&category=all) -> read every page
of it -> read each bid's Available Date from its public page -> keep the bids
whose Available Date is in the console's range -> sign in again and open each
kept bid the way Philadelphia does (the list's own bidAck.sda link), reading its
header and line items -> PASS / REJECT / MANUAL REVIEW each with Philadelphia's
evaluation -> store in the DB, from which the one-sheet Excel is built on demand.

COMMBUYS and PHLContracts are the same platform (Periscope BSO), so the header
reader is Philadelphia's own. The Available Dates are read first, from the public
bid pages through the browser's own fetch (a plain HTTP client gets the
firewall's empty 202), because that is quick for the whole list; only the bids
in range are then opened one by one.
"""

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any
from urllib.parse import quote

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

from app.config import ENV_FILE, settings
from app.core import credentials, partials, run_manager
from app.core.base_scraper import BaseScraper, StopRequested
from app.core.exports import archive_run
from app.core.filenames import sanitize_filename
from app.scrapers.commbuys import evaluation, export, filters
from app.scrapers.philadelphia import details as phl_details
from app.scrapers.philadelphia.scraper import PhiladelphiaScraper
from app.services.notifier import notify_scrape_completion

logger = logging.getLogger(__name__)

SELLER_HOME_URL = "https://www.commbuys.com/bso/seller/sellerHome.sda"
BID_LIST_URL = "https://www.commbuys.com/bso/bid/bidList.sda?status=Open&category=all"
DETAIL_URL = "https://www.commbuys.com/bso/external/bidDetail.sdo?docId={}&external=true&parentUrl=close"
DETAIL_BATCH = 6  # bid pages fetched at once; a few hundred take a few minutes
DETAIL_SCRIPT_TIMEOUT = 180  # seconds for one batch
MAX_VISIT_FAILURES = 5  # bid pages in a row that will not open before the run stops trying
MAX_PAGES = 400  # a guard against a pager that never ends (the list is ~25 bids a page)
SETTLE_SECONDS = 1.5  # as Philadelphia: let the detail page finish drawing

# The list's rows by header name, and the "1-25 of 593" counter. One call, so a
# page change can't leave half a table read.
_READ_PAGE = """
const t = document.getElementById('resultsTable');
const counter = [...document.querySelectorAll('td.inputs-01')].map(e => e.innerText.trim())
  .find(s => /^\\d+\\s*-\\s*\\d+\\s+of\\s+\\d+/.test(s)) || null;
if (!t) return {counter, header: [], rows: []};
const all = [...t.rows].map(r => ({
  cells: [...r.cells].map(c => c.innerText.replace(/\\s+/g, ' ').trim()),
  link: (r.querySelector("a[href*='destination=detail']") || {}).href || '',
}));
const data = all.slice(1).filter(r => r.cells.length > 1);
return {counter, header: (all[0] || {cells: []}).cells, rows: data.map(r => r.cells), links: data.map(r => r.link)};
"""

# Fetch a batch of bid pages from inside the page (it holds the firewall's pass)
# and return the text after "Available Date" on each, or the HTTP status if none.
_FETCH_DATES = """
const [urls, done] = [arguments[0], arguments[arguments.length - 1]];
Promise.all(urls.map(u => fetch(u, {credentials: 'include'})
  .then(async r => {
    const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
    const text = ((doc.body && doc.body.textContent) || '').replace(/\\s+/g, ' ');
    const i = text.indexOf('Available Date');
    return i < 0 ? 'status ' + r.status : text.slice(i, i + 60);
  })
  .catch(e => 'error ' + e))).then(done);
"""

LIST_FIELDS = {
    "Bid #": "bid_number", "Organization": "organization", "Alternate Id": "alternate_id", "Buyer": "buyer",
    "Description": "description", "Purchase Method": "purchase_method", "Bid Opening Date": "opening_date",
}


def counter_range(text: str | None) -> tuple[int, int, int] | None:
    """'26-50 of 593' -> (26, 50, 593)."""
    match = re.match(r"(\d+)\s*-\s*(\d+)\s+of\s+([\d,]+)", text or "")
    return (int(match[1]), int(match[2]), int(match[3].replace(",", ""))) if match else None


def rows_to_records(header: list[str], rows: list[list[str]], links: list[str] | None = None) -> list[dict[str, Any]]:
    """List rows as records, by header name, each with its public page link and
    (when given) the list's own signed-in link to the bid."""
    missing = {"Bid #", "Description"} - set(header)
    if missing:
        raise ValueError(f"COMMBUYS bid list is missing columns: {', '.join(sorted(missing))}")
    records = []
    for row, link in zip(rows, links or [""] * len(rows)):
        raw = dict(zip(header, row))
        record = {attr: raw.get(name, "") for name, attr in LIST_FIELDS.items()}
        if not record["bid_number"]:
            continue
        record["detail_url"] = DETAIL_URL.format(quote(record["bid_number"], safe=""))
        record["ack_url"] = link
        record["raw"] = raw
        records.append(record)
    return records


# "Item # 1:   ( 25-10  -  00 )  <description>", its category under "U N S P S C
# Code:", and a "Qty  Unit Cost  UOM ..." header row with the values on the next.
_ITEM = re.compile(r"^Item #\s*(\d+):\s*\(\s*([\d\s-]+?)\s*\)\s*(.*)$")


def parse_items(page_text: str) -> list[dict[str, str]]:
    """A COMMBUYS bid page's line items, in the shape Philadelphia's evaluation reads.

    PHLContracts writes items as "Item: 1"; COMMBUYS as "Item # 1:", so the
    Philadelphia item reader finds none here and this one is COMMBUYS's own.
    """
    items: list[dict[str, str]] = []
    lines = [line.strip() for line in page_text.replace("\xa0", " ").splitlines()]
    for i, line in enumerate(lines):
        opener = _ITEM.match(line)
        if opener:
            items.append({"item_number": opener[1], "nigp_code": re.sub(r"\s+", "", opener[2]),
                          "name": opener[3].strip(), "quantity": "", "unit": "", "specification": ""})
            continue
        if not items:
            continue
        item = items[-1]
        if line.startswith("U N S P S C Code") and i + 1 < len(lines):
            item["specification"] = lines[i + 1]
        elif line.startswith("Qty") and "UOM" in line and i + 1 < len(lines):
            headings = [h.strip() for h in lines[i].split("\t")]
            values = [v.strip() for v in lines[i + 1].split("\t")]
            row = dict(zip(headings, values))
            item["quantity"] = row.get("Qty", "")
            item["unit"] = row.get("UOM", "").split(" - ")[0]  # "EA - Each" -> "EA", as the matrix's units are
    return items


class CommbuysScraper(BaseScraper):
    def __init__(self, run_id: str, criteria: dict[str, str]):
        super().__init__(run_id)
        self.criteria = criteria
        self._records: list[dict[str, Any]] = []

    def _js_click(self, element) -> None:
        self.driver.execute_script("arguments[0].click();", element)

    # -- the flow -----------------------------------------------------------

    def sign_in(self) -> None:
        self.set_step("verifying_credentials")
        username, password = settings.commbuys_username, settings.commbuys_password
        if not username or not password:
            raise RuntimeError("COMMBUYS_USERNAME / COMMBUYS_PASSWORD are not set in server/.env")
        checks = credentials.verify_all(
            {"COMMBUYS_USERNAME": username, "COMMBUYS_PASSWORD": password}, ENV_FILE, portal="commbuys",
        )
        problems = credentials.problems(checks)
        if problems:
            raise RuntimeError("; ".join(problems))

        self.set_step("signing_in")
        self.navigate(settings.commbuys_login_url)
        self.wait(60).until(lambda d: d.find_element(By.ID, "home-sign-in-btn").is_displayed())
        self.driver.find_element(By.ID, "home-sign-in-btn").click()
        self.wait(30).until(lambda d: d.find_element(By.ID, "homeLoginForm:loginId").is_displayed())
        self.driver.find_element(By.ID, "homeLoginForm:loginId").send_keys(username)
        self.driver.find_element(By.ID, "homeLoginForm:password").send_keys(password)
        self._js_click(self.driver.find_element(By.ID, "homeLoginForm:sign-in-dialog-btn"))
        try:
            self.wait(60).until(lambda d: "login.xhtml" not in d.current_url or self._login_error())
        except TimeoutException:
            pass
        if "login.xhtml" in self.driver.current_url:
            reason = self._login_error() or "still on the sign-in page after 60 s"
            raise RuntimeError(f"COMMBUYS did not accept the sign-in: {reason}")
        logger.info("[run %s] signed in to COMMBUYS", self.run_id)

    def _login_error(self) -> str:
        return self.driver.execute_script(
            "return [...document.querySelectorAll('.ui-messages-error, .ui-message-error, .ui-growl-message')]"
            ".filter(e => e.offsetParent).map(e => e.innerText.trim()).filter(Boolean).join(' ');"
        ) or ""

    def read_bid_list(self) -> list[dict[str, Any]]:
        """Seller home -> the open-bids list -> every page of it."""
        self.set_step("opening_seller_home")
        self.navigate(SELLER_HOME_URL)
        self.set_step("opening_bid_list")
        self.navigate(BID_LIST_URL)
        if "login.xhtml" in self.driver.current_url:
            raise RuntimeError("COMMBUYS sent the bid list back to the sign-in page (session not kept)")
        page = self.wait(60).until(lambda d: (p := d.execute_script(_READ_PAGE))["counter"] is not None and p)
        first = counter_range(page["counter"])
        if first is None or first[2] == 0:
            return []
        total, per_page = first[2], first[1] - first[0] + 1
        records = rows_to_records(page["header"], page["rows"], page.get("links"))
        number = 1
        while len(records) < total and number < MAX_PAGES:
            self.raise_if_stopped()
            number += 1
            self.set_step(f"reading_bid_list:page {number}")
            expected_start = (number - 1) * per_page + 1
            self.driver.execute_script("viewPage(arguments[0]);", number)
            page = self.wait(60).until(
                lambda d: (p := d.execute_script(_READ_PAGE))["counter"]
                and (counter_range(p["counter"]) or (0,))[0] == expected_start and p
            )
            records.extend(rows_to_records(page["header"], page["rows"], page.get("links")))
            run_manager.update_run(self.run_id, bids_found=len(records))
        if len(records) != total:
            run_manager.add_warning(self.run_id, f"COMMBUYS listed {total:,} open bids but {len(records):,} were read.")
        logger.info("[run %s] read %d open bids from %d page(s)", self.run_id, len(records), number)
        return records

    def _visit_bid_page(self, url: str) -> str:
        """Open one bid page as a visitor; returns its text ('' if it never showed a date).

        An ordinary visit is what earns the firewall's pass (its JavaScript
        check); the batch reads that follow only work once the browser holds it.
        """
        self.navigate(url)
        try:
            return self.wait(30).until(lambda d: (s := d.execute_script(
                "return document.body ? document.body.innerText : '';") or "") and "Available Date" in s and s)
        except TimeoutException:
            return ""

    def _fetch_batch(self, batch: list[dict[str, Any]]) -> list[str]:
        return self.driver.execute_async_script(_FETCH_DATES, [r["detail_url"] for r in batch])

    def read_available_dates(self, records: list[dict[str, Any]]) -> None:
        """Fill `available_date` from each bid's public page, a batch at a time.

        Read from the signed-in session these came back as the firewall's empty
        202 and, visited, as 401 (18 Nov). The list is already read, so the session
        is dropped (cookies cleared), and one ordinary visit earns the firewall's
        pass; read as a visitor that way, they come back whole.
        """
        self.set_step("reading_available_dates")
        self.driver.set_script_timeout(DETAIL_SCRIPT_TIMEOUT)
        self.driver.delete_all_cookies()
        self._visit_bid_page(records[0]["detail_url"])
        misses: list[str] = []
        for start in range(0, len(records), DETAIL_BATCH):
            self.raise_if_stopped()
            batch = records[start:start + DETAIL_BATCH]
            texts = self._fetch_batch(batch)
            if not any(filters.available_date(x) for x in texts):
                # Challenged again (the pass expires): earn a new one, retry once.
                self._visit_bid_page(batch[0]["detail_url"])
                texts = self._fetch_batch(batch)
            for record, text in zip(batch, texts):
                record["available_date"] = filters.available_date(text)
                if not record["available_date"]:
                    misses.append(text[:40])
            if (start // DETAIL_BATCH) % 10 == 0:
                self.set_step(f"reading_available_dates:{min(start + DETAIL_BATCH, len(records))}/{len(records)}")
        if misses:
            logger.info("[run %s] %d bid page(s) missed in the batch read (e.g. %s); visiting them",
                        self.run_id, len(misses), sorted(set(misses))[:3])
        # The few the batch could not read get one ordinary visit each; a run of
        # failures means the site is refusing us, so stop rather than crawl on.
        failures = 0
        for record in [r for r in records if not r["available_date"]]:
            self.raise_if_stopped()
            record["available_date"] = filters.available_date(self._visit_bid_page(record["detail_url"]))
            failures = 0 if record["available_date"] else failures + 1
            if failures >= MAX_VISIT_FAILURES:
                logger.warning("[run %s] %d bid pages in a row would not open; giving up on the rest",
                               self.run_id, failures)
                break
        unread = sum(not r["available_date"] for r in records)
        if unread:
            run_manager.add_warning(self.run_id, f"{unread} bid page(s) showed no Available Date; those bids are left out.")

    def read_details(self, records: list[dict[str, Any]]) -> None:
        """Open each bid as Philadelphia does and read its header and line items.

        A bid whose page cannot be read keeps its list fields and a
        `detail_error`, which sends it to MANUAL REVIEW: judged on its title
        alone it could pass unread.
        """
        for done, record in enumerate(records, start=1):
            self.raise_if_stopped()
            self.set_step(f"reading_bid:{done}/{len(records)} {record['bid_number']}")
            try:
                self.navigate(record.get("ack_url") or record["detail_url"])
                time.sleep(SETTLE_SECONDS)
                if "login.xhtml" in self.driver.current_url:
                    raise RuntimeError("COMMBUYS sent the bid back to the sign-in page")
                header = self.driver.execute_script(PhiladelphiaScraper._JS_HEADER) or {}
                if not header:
                    raise RuntimeError("the bid page showed no header")
                text = self.driver.execute_script("return document.body ? document.body.innerText : '';") or ""
            except StopRequested:
                raise
            except Exception as exc:  # noqa: BLE001 — one unreadable bid must not end the run
                record["detail_error"] = f"bid page not read ({str(exc).splitlines()[0][:120]})"
                logger.warning("[run %s] %s: %s", self.run_id, record["bid_number"], record["detail_error"])
                continue
            record["extra_header_data"] = header
            record["items"] = parse_items(text)
            record["item_details"] = phl_details.render_items_cell(record)

    def flush_partial(self) -> int:
        run = run_manager.get_run(self.run_id) or {}
        return partials.flush_records(
            self,
            self._records,
            save_bids=export.save_bids,
            write_sheet=export.generate_excel_from_records,
            sheet_name=f"COMMBUYS_({(run.get('search') or 'all open bids').strip()})",
        )

    def run(self) -> None:
        run_manager.update_run(self.run_id, status="running")
        self._save_run_row()
        try:
            self.start_driver()
            self.sign_in()
            self.raise_if_stopped()
            listed = self.read_bid_list()

            start = filters.parse_iso(self.criteria.get("available_from", ""))
            end = filters.parse_iso(self.criteria.get("available_to", ""))
            if listed and (start or end):
                self.read_available_dates(listed)
                kept = [r for r in listed if filters.in_range(r["available_date"], start, end)]
            else:
                kept = listed
            logger.info("[run %s] %d of %d open bid(s) in the Available Date range", self.run_id, len(kept), len(listed))
            if kept:
                if start or end:
                    self.sign_in()  # reading the dates cleared the session's cookies
                self.read_details(kept)
            self.stop_driver()  # the rest is local work

            self.set_step("evaluating")
            passed = evaluation.apply(kept)
            self._records = kept
            count = len(kept)
            preview = [{k: v for k, v in r.items() if k != "raw"} for r in kept[:200]]  # the raw row is for the DB
            run_manager.update_run(self.run_id, bids_found=count, bids_processed=count, bids_passed=passed,
                                   bids_listed=len(listed), bids=preview)
            if not count:
                run_manager.update_run(self.run_id, no_results=True)

            run = run_manager.get_run(self.run_id) or {"run_id": self.run_id}
            db_ok = True
            try:
                run_manager.update_run(self.run_id, bids_stored_in_db=export.save_bids(run, kept))
            except Exception:  # noqa: BLE001 — DB issues shouldn't abort the run
                db_ok = False
                logger.exception("[run %s] DB save failed", self.run_id)
                run_manager.add_error(self.run_id, "db save failed (see logs)")
                run_manager.update_run(self.run_id, db_save_failed=True)

            self.set_step("generating_excel")
            if db_ok:
                run_manager.update_run(self.run_id, excel_exported=True)  # rebuilt from the DB on download
            else:
                name = sanitize_filename(f"COMMBUYS_({run.get('search') or 'all open bids'})", max_length=150)
                path = self.run_dir / f"{name}.xlsx"
                export.generate_excel_from_records(kept, path)
                run_manager.update_run(self.run_id, excel_path=str(path), excel_exported=True)

            self.set_step("packaging_results")
            archive_run(self.run_id)
            run_manager.update_run(self.run_id, status="completed", step="done")
            notify_scrape_completion(self.run_id, "commbuys", count)
        except StopRequested:
            self.deliver_partial()
        except Exception as exc:  # noqa: BLE001 — a failed run must be reported, not crash the worker
            logger.exception("[run %s] failed", self.run_id)
            self.screenshot("fatal")
            run_manager.add_error(self.run_id, str(exc)[:500])
            run_manager.update_run(self.run_id, status="failed", step="failed")
        finally:
            self.cleanup()
            run_manager.update_run(self.run_id, finished_at=datetime.now().isoformat())
            self._save_run_row()
            run_manager.remove_empty_folder(self.run_id)

    def _save_run_row(self) -> None:
        run = run_manager.get_run(self.run_id)
        if run:
            try:
                export.save_run(run)
            except Exception:  # noqa: BLE001
                logger.exception("[run %s] save_run failed", self.run_id)


def execute_run(run_id: str, criteria: dict[str, str]) -> None:
    CommbuysScraper(run_id, criteria).run()
