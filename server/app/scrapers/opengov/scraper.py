"""Selenium automation for OpenGov Procurement (procurement.opengov.com).

Flow, per run:

    /login -> "Vendor Login" -> email -> Continue -> password -> submit
    top nav "Network"          -> Current Opportunities table
    every page of the table    -> Project Title, Organization, State, Status,
                                  Release Date, Due Date
    rows -> database -> one .xlsx (no detail pages are opened: they trigger a CAPTCHA)

The deliverable is a bare spreadsheet (`opengov` is in `exports.EXCEL_ONLY_PORTALS`);
nothing is downloaded.

Selector policy: OpenGov's class names are build hashes (`_3r8N_1U5V…`) that change
between deploys, so nothing here keys off one. The login uses the stable `data-qa`
hooks, the nav uses `data-test`/`id`, the list table is located by its *header
text* and read column-by-column from those headers.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from typing import Any

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC

from app.config import settings
from app.core import partials, run_manager
from app.core.base_scraper import BaseScraper, StopRequested
from app.core.exports import archive_run
from app.core.filenames import sanitize_filename
from app.scrapers.myflorida.dates import PostingDateRange
from app.scrapers.opengov import evaluation, export
from app.services.notifier import notify_scrape_completion

logger = logging.getLogger(__name__)

# -- sign in -------------------------------------------------------------------
VENDOR_LOGIN_BUTTON = "button[data-qa='login-showVendorForm']"
EMAIL_INPUT = "[data-qa='login-email'], #login-email"
CONTINUE_BUTTON = "[data-qa='login-continue']"
PASSWORD_INPUT = "input[type='password']"
LOGIN_TIMEOUT = 90

# -- navigation ----------------------------------------------------------------
# The top-nav item. Present only once the session is real, so it doubles as the
# "we are logged in" check.
NETWORK_LINK = "li#network a, li[data-test='level_one_item_network_link'] a"
TABLE_TIMEOUT = 60
SETTLE_SECONDS = 1.0
MAX_PAGES = 200
PAGE_TURN_TIMEOUT = 30
LIVE_PREVIEW_CEILING = 1000

# ReactTable's own pager.
NEXT_BUTTON_CSS = ".-pagination .-next button.-btn"
PAGE_INPUT_CSS = ".-pagination .-pageJump input"
TOTAL_PAGES_CSS = ".-pagination .-totalPages"
PAGE_SIZE_CSS = "select[aria-label='rows per page']"
PAGE_SIZE = "20"  # the largest the table offers: fewest pages to walk
LOADING_CSS = ".ReactTable .-loading.-active"

# Passive tap on the page's own data feed. The list response carries each
# project's `id` and `government.code` (the agency slug used in bid URLs); the
# table shows neither, so they are recorded as the responses arrive. Nothing is
# requested here, and no bid page is opened.
_TAP_JS = r"""
if (window.__govTap) return true;
window.__govTap = true; window.__govCodes = window.__govCodes || {};
const take = text => { try {
  for (const p of (JSON.parse(text).projects || []))
    if (p && p.id != null && p.government && p.government.code) window.__govCodes[p.id] = p.government.code;
} catch (e) {} };
const isList = u => /project\/search/.test(u || '');
const of = window.fetch;
window.fetch = function() { const p = of.apply(this, arguments);
  p.then(r => { if (isList(r.url)) r.clone().text().then(take).catch(() => {}); }).catch(() => {}); return p; };
const oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open = function(m, u) { this.__u = u; return oo.apply(this, arguments); };
XMLHttpRequest.prototype.send = function() {
  this.addEventListener('load', () => { if (isList(this.__u)) take(this.responseText); });
  return os.apply(this, arguments); };
return true;
"""

# Finds the opportunities table by its header text (not by class), and returns one
# {header -> cell text} map per body row.
_READ_TABLE_JS = r"""
const norm = s => (s || '').replace(/ /g, ' ').replace(/\s+/g, ' ').trim();
const tables = [...document.querySelectorAll('table, [role=table], [role=grid]')];
for (const t of tables) {
  const hs = [...t.querySelectorAll('thead th, [role=columnheader]')];
  const headers = hs.map(h => norm(h.innerText));
  if (!(headers.some(h => /due/i.test(h)) && headers.some(h => /status/i.test(h)))) continue;
  const out = [];
  const ORIGIN = 'https://procurement.opengov.com';
  const URL_RE = /\/portal\/[^\/\s"']+\/projects\/\d+/;
  const absolute = u => u.startsWith('http') ? u : ORIGIN + (u.startsWith('/') ? '' : '/') + u;
  // A real href / data attribute first; otherwise the project id from the row's
  // React props joined with the agency slug the data feed supplied.
  function findLink(row) {
    for (const el of row.querySelectorAll('a, [data-href], [data-url], [data-link]')) {
      for (const v of [el.getAttribute('href'), el.getAttribute('data-href'), el.getAttribute('data-url'), el.getAttribute('data-link')]) {
        const m = v && v.match(URL_RE); if (m) return absolute(m[0]);
      }
    }
    // The table drops the agency slug, but the data feed the page itself loaded
    // has it (government.code). _TAP_JS recorded id -> slug as pages came in.
    const start = row.querySelector('a') || row;
    const fk = Object.keys(start).find(k => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
    let fiber = fk ? start[fk] : null;
    for (let i = 0; fiber && i < 30; i++, fiber = fiber.return) {
      const orig = fiber.memoizedProps && fiber.memoizedProps.original;
      if (orig && orig.id != null) {
        const code = (window.__govCodes || {})[orig.id];
        return code ? ORIGIN + '/portal/' + code + '/projects/' + orig.id : null;
      }
    }
    return null;
  }
  for (const row of t.querySelectorAll('tbody tr, [role=row]')) {
    const cells = [...row.querySelectorAll(':scope > td, :scope > [role=cell], :scope > [role=gridcell]')];
    if (!cells.length) continue;
    const offset = Math.max(0, cells.length - headers.length);
    const rec = {};
    headers.forEach((h, i) => { const c = cells[i + offset]; if (c && h) rec[h] = norm(c.innerText); });
    out.push({cells: rec, link: findLink(row), html: out.length ? null : row.outerHTML.slice(0, 6000)});
  }
  return out;
}
return null;
"""


_ROW_DATE_FORMATS = ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y")


def parse_row_date(raw: str | None) -> date | None:
    """A table cell's date ("11/17/2026", "12/7/2026"), or None if unreadable."""
    text = (raw or "").strip()
    for fmt in _ROW_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def release_verdict(raw: str | None, window: PostingDateRange) -> str:
    """Where a row's Release Date falls against the range: "in", "before",
    "after" or "unreadable". Both ends are inclusive and compared as calendar
    days. Only a row provably inside the range is kept, so an unreadable date is
    skipped (and counted) rather than waved through."""
    released = parse_row_date(raw)
    if released is None:
        return "unreadable"
    if window.start and released < window.start:
        return "before"
    if window.end and released > window.end:
        return "after"
    return "in"


def describe_window(window: PostingDateRange) -> str:
    """The range in words, for the run summary."""
    if window.start and window.end:
        return f"released {window.start.isoformat()} to {window.end.isoformat()}"
    if window.start:
        return f"released on or after {window.start.isoformat()}"
    if window.end:
        return f"released on or before {window.end.isoformat()}"
    return ""


class OpenGovLoginError(Exception):
    """Sign-in did not complete. Carries a message worth showing an operator."""


def _field_for_header(header: str) -> str | None:
    h = header.lower()
    if "organization" in h or "agency" in h:
        return "organization"
    if "state" in h:
        return "state"
    if "status" in h:
        return "status"
    if "release" in h or "posted" in h or "publish" in h:
        return "release_date"
    if "due" in h or "close" in h:
        return "due_date"
    if "title" in h or h.strip() in ("project", "project name", "name"):
        return "project_title"
    return None


class OpenGovScraper(BaseScraper):
    """One run: sign in, read every current opportunity, and package the sheet."""

    def __init__(self, run_id: str, date_range: PostingDateRange | None = None):
        super().__init__(run_id)
        self.date_range = date_range or PostingDateRange()
        self._skipped_outside_range = 0
        self._link_dumped = False
        self._skipped_no_release_date = 0
        self._records: list[dict[str, Any]] = []

    # -- helpers -----------------------------------------------------------------

    def _safe_click(self, element) -> None:
        try:
            element.click()
        except WebDriverException:
            self.driver.execute_script("arguments[0].click();", element)

    # -- sign in -----------------------------------------------------------------

    def login(self) -> None:
        self.set_step("logging_in")
        if not settings.opengov_email or not settings.opengov_password:
            raise OpenGovLoginError(
                "OPENGOV_EMAIL / OPENGOV_PASSWORD are not set in server/.env — "
                "OpenGov needs a vendor account to list opportunities."
            )

        self.navigate(settings.opengov_login_url)
        try:
            button = self.wait(30).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, VENDOR_LOGIN_BUTTON))
            )
        except TimeoutException:
            self.screenshot("login_no_vendor_button")
            raise OpenGovLoginError("OpenGov login: the Vendor Login button never appeared.")
        self._safe_click(button)

        email = self.wait(30).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, EMAIL_INPUT))
        )
        email.clear()
        email.send_keys(settings.opengov_email)
        self._safe_click(self.driver.find_element(By.CSS_SELECTOR, CONTINUE_BUTTON))

        try:
            password = self.wait(30).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, PASSWORD_INPUT))
            )
        except TimeoutException:
            self.screenshot("login_no_password")
            raise OpenGovLoginError(
                "OpenGov login: the password step never appeared after Continue."
            )
        password.clear()
        password.send_keys(settings.opengov_password)
        password.send_keys(Keys.RETURN)

        try:
            self.wait(LOGIN_TIMEOUT).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, NETWORK_LINK)
            )
        except TimeoutException:
            self.screenshot("login_failed")
            raise OpenGovLoginError(
                "OpenGov login did not complete — the dashboard's Network menu never "
                "appeared. Check OPENGOV_EMAIL / OPENGOV_PASSWORD in server/.env."
            )
        logger.info("[run %s] login successful; landed on %s", self.run_id, self.driver.current_url)

    # -- the opportunities table ---------------------------------------------------

    def open_network(self) -> None:
        self.set_step("opening_network")
        self.driver.execute_script(_TAP_JS)  # before the list loads, so its feed is seen
        link = self.wait(30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, NETWORK_LINK))
        )
        self._safe_click(link)

    def _read_table(self) -> list[dict[str, Any]] | None:
        return self.driver.execute_script(_READ_TABLE_JS)

    def _await_table(self) -> list[dict[str, Any]]:
        self.set_step("waiting_for_table")
        rows: list[dict[str, Any]] | None = None

        def ready(_driver) -> bool:
            nonlocal rows
            rows = self._read_table()
            return bool(rows)

        try:
            self.wait(TABLE_TIMEOUT).until(ready)
        except TimeoutException:
            self.screenshot("no_table")
            self._dump_page("no_table")
            if rows is not None:  # table found, no rows: a genuine empty list
                return []
            raise OpenGovLoginError(
                "OpenGov: the Current Opportunities table never appeared "
                "(a page dump was saved to the run folder)."
            )
        return rows or []

    def _dump_page(self, name: str) -> None:
        try:
            path = self.run_dir / f"page_{sanitize_filename(name)}.html"
            path.write_text(self.driver.page_source, encoding="utf-8")
        except Exception:  # noqa: BLE001 — diagnostics must never break the run
            pass

    @staticmethod
    def _record_from_row(row: dict[str, Any]) -> dict[str, Any]:
        record: dict[str, Any] = {}
        for header, value in (row.get("cells") or {}).items():
            field = _field_for_header(header)
            if field and not record.get(field):
                record[field] = value
        return record

    # -- list state (ReactTable) -----------------------------------------------------

    def _await_idle(self) -> None:
        """Wait out the table's "Loading..." overlay."""
        try:
            self.wait(TABLE_TIMEOUT).until(
                lambda d: not d.find_elements(By.CSS_SELECTOR, LOADING_CSS)
            )
        except TimeoutException:
            pass

    def _current_page(self) -> int:
        els = self.driver.find_elements(By.CSS_SELECTOR, PAGE_INPUT_CSS)
        try:
            return int(els[0].get_attribute("value")) if els else 1
        except (TypeError, ValueError):
            return 1

    def _total_pages(self) -> int:
        els = self.driver.find_elements(By.CSS_SELECTOR, TOTAL_PAGES_CSS)
        try:
            return int(els[0].text.strip()) if els else 1
        except ValueError:
            return 1

    def _set_page_size(self) -> None:
        """Show 20 rows per page. Changing it resets the table to page 1."""
        from selenium.webdriver.support.ui import Select

        els = self.driver.find_elements(By.CSS_SELECTOR, PAGE_SIZE_CSS)
        if not els:
            return
        select = Select(els[0])
        if select.first_selected_option.get_attribute("value") != PAGE_SIZE:
            select.select_by_value(PAGE_SIZE)
            self._await_idle()
            time.sleep(SETTLE_SECONDS)

    def _go_to_page(self, page: int) -> None:
        if self._current_page() == page:
            return
        box = self.driver.find_element(By.CSS_SELECTOR, PAGE_INPUT_CSS)
        box.click()
        box.send_keys(Keys.CONTROL, "a")
        box.send_keys(str(page), Keys.RETURN)
        self.wait(PAGE_TURN_TIMEOUT).until(lambda d: self._current_page() == page)
        self._await_idle()
        time.sleep(SETTLE_SECONDS)

    def _next_enabled(self):
        for el in self.driver.find_elements(By.CSS_SELECTOR, NEXT_BUTTON_CSS):
            if el.is_displayed() and el.get_attribute("disabled") is None:
                return el
        return None

    # -- walking the list ------------------------------------------------------------

    def scrape_all_pages(self) -> None:
        self._await_table()
        self._set_page_size()
        total = self._total_pages()
        logger.info("[run %s] %d page(s) at %s rows each", self.run_id, total, PAGE_SIZE)

        for page in range(1, MAX_PAGES + 1):
            self.raise_if_stopped()
            rows = self._read_table() or []
            logger.info("[run %s] page %d/%d: %d row(s)", self.run_id, page, total, len(rows))
            for index, row in enumerate(rows):
                self.raise_if_stopped()
                record = self._record_from_row(row)
                record["detail_url"] = row.get("link") or None
                if not record["detail_url"] and not self._link_dumped:
                    self._link_dumped = True
                    logger.warning("[run %s] no bid link found on a row; saved the row HTML", self.run_id)
                    try:
                        (self.run_dir / "opengov_row.html").write_text(
                            row.get("html") or "", encoding="utf-8")
                    except Exception:  # noqa: BLE001
                        pass
                if self.date_range.is_set:
                    verdict = release_verdict(record.get("release_date"), self.date_range)
                    if verdict != "in":
                        if verdict == "unreadable":
                            self._skipped_no_release_date += 1
                        else:
                            self._skipped_outside_range += 1
                        continue
                run_manager.update_run(
                    self.run_id,
                    step=f"page {page}/{total}, row {index + 1}/{len(rows)}: "
                         f"{record.get('project_title') or ''}"[:120],
                )
                record.update(evaluation.evaluate(record))
                record["flag_status"], record["flag_reason"] = evaluation.niche_flag(record)
                self._records.append(record)
                run_manager.update_run(self.run_id, bids_processed=len(self._records))
                self._mirror_one(record)

            nxt = self._next_enabled()
            if nxt is None:
                break
            self.scroll_into_view(nxt)
            self._safe_click(nxt)
            try:
                self.wait(PAGE_TURN_TIMEOUT).until(lambda d: self._current_page() == page + 1)
            except TimeoutException:
                logger.warning("[run %s] Next did not advance past page %d", self.run_id, page)
                break
            self._await_idle()
            time.sleep(SETTLE_SECONDS)

    # -- orchestration -------------------------------------------------------------

    def _mirror_one(self, record: dict[str, Any]) -> None:
        if len(self._records) > LIVE_PREVIEW_CEILING:
            return
        run_manager.add_bid_result(self.run_id, {
            "title": record.get("project_title"),
            "organization": record.get("organization"),
            "state": record.get("state"),
            "status": record.get("status"),
            "release_date": record.get("release_date"),
            "due_date": record.get("due_date"),
            "detail_url": record.get("detail_url"),
            "decision": record.get("decision"),
            "reason": record.get("reason"),
            "niche_flag": record.get("flag_status") or None,
            "niche_flag_reason": record.get("flag_reason") or None,
        })

    def flush_partial(self) -> int:
        return partials.flush_records(
            self,
            self._records,
            save_bids=export.save_bids,
            write_sheet=export.generate_excel_from_records,
            sheet_name="OpenGov_Bids",
        )

    def run(self) -> None:
        run_manager.update_run(self.run_id, status="running")
        self._save_run_row()
        try:
            self.start_driver()
            self.login()
            self.open_network()
            self.scrape_all_pages()
            if self.date_range.is_set:
                run_manager.update_run(
                    self.run_id,
                    bids_skipped_outside_date_range=self._skipped_outside_range,
                    bids_skipped_no_publish_date=self._skipped_no_release_date,
                )
                logger.info(
                    "[run %s] release-date range (%s): kept %d, skipped %d outside it, "
                    "%d with no readable date",
                    self.run_id, describe_window(self.date_range), len(self._records),
                    self._skipped_outside_range, self._skipped_no_release_date,
                )
            if not self._records:
                message = (
                    f"no current opportunity was {describe_window(self.date_range)}"
                    if self.date_range.is_set
                    else "the portal listed no current opportunities"
                )
                run_manager.add_warning(self.run_id, message)
                run_manager.update_run(self.run_id, no_results=True)

            run_manager.update_run(
                self.run_id, bids_found=len(self._records), bids_processed=len(self._records)
            )

            self.set_step("storing_in_db")
            run = run_manager.get_run(self.run_id) or {"run_id": self.run_id}
            db_ok = True
            try:
                stored = export.save_bids(run, self._records)
                run_manager.update_run(self.run_id, bids_stored_in_db=stored)
            except Exception:  # noqa: BLE001 — DB issues shouldn't abort the run
                db_ok = False
                logger.exception("[run %s] DB save failed", self.run_id)
                run_manager.add_error(self.run_id, "db save failed (see logs)")

            self.set_step("generating_excel")
            if db_ok:
                # The sheet is rebuilt from the DB when packaged / downloaded.
                run_manager.update_run(self.run_id, excel_exported=True)
            else:
                # Tells packaging to ship this sheet rather than regenerate an
                # empty one from a DB that never got the rows.
                path = self.run_dir / "OpenGov_Bids.xlsx"
                try:
                    export.generate_excel_from_records(self._records, path)
                    run_manager.update_run(
                        self.run_id, excel_path=str(path), excel_exported=True, db_save_failed=True
                    )
                except Exception:  # noqa: BLE001 — never fail the run over the Excel
                    logger.exception("[run %s] Excel generation failed", self.run_id)
                    run_manager.add_error(self.run_id, "excel generation failed (see logs)")

            self.set_step("packaging_results")
            archive_run(self.run_id)

            run_manager.update_run(self.run_id, status="completed", step="done")
            notify_scrape_completion(self.run_id, "opengov", len(self._records))
        except StopRequested:
            # Stop was pressed: keep what was gathered. See BaseScraper.deliver_partial.
            self.deliver_partial()
        except Exception as exc:  # noqa: BLE001 — a failed run is reported, not crashed
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
        if not run:
            return
        try:
            export.save_run(run)
        except Exception:  # noqa: BLE001
            logger.exception("[run %s] save_run failed", self.run_id)


def execute_run(run_id: str, date_range: PostingDateRange | None = None) -> None:
    OpenGovScraper(run_id, date_range).run()
