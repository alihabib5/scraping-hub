"""Selenium automation for OpenGov Procurement (procurement.opengov.com).

Flow, per run:

    /login -> "Vendor Login" -> email -> Continue -> password -> submit
    top nav "Opportunities"    -> Current Solicitations table (AG Grid)
    page size 100, Next Page   -> Project Title, Project ID, Agency, State,
                                  Released, Due / Time Left, Bid URL
    rows -> database -> one .xlsx (no detail pages are opened: they trigger a CAPTCHA)

The deliverable is a bare spreadsheet (`opengov` is in `exports.EXCEL_ONLY_PORTALS`);
nothing is downloaded.

Selector policy: OpenGov's class names are build hashes (`_3r8N_1U5V…`) that change
between deploys, so nothing here keys off one. The login uses the stable `data-qa`
hooks, the nav link is found by its text, the grid is read column-by-column from its
header text.
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
# The top-nav "Opportunities" label. Present only once the session is real, so it
# doubles as the "we are logged in" check. It is a <span>; the click goes to its
# nearest link/button ancestor.
OPPORTUNITIES_XPATH = (
    "//span[normalize-space(.)='Opportunities' and contains(@class,'MuiTypography')]"
)
TABLE_TIMEOUT = 60
SETTLE_SECONDS = 1.0
MAX_PAGES = 200
PAGE_TURN_TIMEOUT = 30
LIVE_PREVIEW_CEILING = 1000

# The Current Solicitations grid (AG Grid) and its pager.
GRID_CSS = "[data-testid='opportunity-directory-grid']"
LOADING_CSS = ".ag-overlay-loading-center, .ag-overlay-loading-wrapper"
PAGE_SIZE = "100"
# Page-size control: a native <select> or a MUI/AG combobox, found by label.
PAGE_SIZE_XPATH = (
    "//*[self::select or @role='combobox' or @role='button']"
    "[contains(translate(@aria-label,'PAGESIZRWO','pagesizrwo'),'page size')"
    " or contains(translate(@aria-label,'PAGESIZRWO','pagesizrwo'),'rows per page')"
    " or contains(translate(@aria-labelledby,'PAGESIZRWO','pagesizrwo'),'page-size')]"
)
PAGE_SIZE_FALLBACK_CSS = (
    ".ag-paging-page-size .ag-picker-field-wrapper, .ag-paging-page-size select, "
    "[data-testid*='page-size' i], [data-testid*='pageSize' i]"
)
NEXT_BUTTON_CSS = (
    "button[aria-label='Next Page'], button[aria-label='Next page'], "
    "button[aria-label='Go to next page'], [data-testid*='next' i][role='button'], "
    ".ag-paging-button[ref='btNext'], .ag-paging-button[aria-label='Next Page']"
)
OPTION_CSS = "[role='option'], li[role='option'], .ag-list-item, option"

# Reads the rows currently rendered by the grid, keyed by the column header text.
# AG Grid virtualises rows, so the caller scrolls and merges by row-index. Cells
# of pinned and scrolling column groups share a row-index and are joined here.
_READ_GRID_JS = r"""
const norm = s => (s || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
const ORIGIN = location.origin;
const absolute = u => u.startsWith('http') ? u : ORIGIN + (u.startsWith('/') ? '' : '/') + u;
const grid = document.querySelector("[data-testid='opportunity-directory-grid']") || document;
const headers = {};
grid.querySelectorAll('.ag-header-cell[col-id]').forEach(h => {
  const t = norm((h.querySelector('.ag-header-cell-text') || h).innerText);
  if (t) headers[h.getAttribute('col-id')] = t;
});
if (!Object.keys(headers).length) return null;
// Cell text without status chips ("Open") and other badges.
const cellText = c => {
  const k = c.cloneNode(true);
  k.querySelectorAll('.MuiChip-root, [data-testid="status-chip-container"]').forEach(e => e.remove());
  return norm(k.innerText);
};
const OPP_RE = /\/opportunities\/(\d+)/;
// 1) a real link; 2) the row's data object (React props); 3) a numeric row-id.
function findId(r) {
  for (const el of r.querySelectorAll('a[href], [data-href]')) {
    const m = (el.getAttribute('href') || el.getAttribute('data-href') || '').match(OPP_RE);
    if (m) return m[1];
  }
  const fk = Object.keys(r).find(k => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
  let f = fk ? r[fk] : null;
  for (let i = 0; f && i < 40; i++, f = f.return) {
    const p = f.memoizedProps || {};
    const cands = [p.data, p.original, p.rowData, p.node && p.node.data,
                   p.rowNode && p.rowNode.data, p.rowCtrl && p.rowCtrl.rowNode && p.rowCtrl.rowNode.data,
                   p.params && p.params.data];
    for (const d of cands) {
      if (d && typeof d === 'object') {
        const v = d.opportunityId ?? d.projectId ?? d.id;
        if (v != null && /^\d+$/.test(String(v))) return String(v);
      }
    }
  }
  const rid = r.getAttribute('row-id');
  if (rid && /^\d+$/.test(rid)) return rid;
  return null;
}
const rows = {};
grid.querySelectorAll('.ag-row[row-index]').forEach(r => {
  const idx = r.getAttribute('row-index');
  const rec = rows[idx] || (rows[idx] = {index: +idx, cells: {}, link: null, html: null, status: null});
  if (!rec.status) {
    const chip = r.querySelector('[data-testid="status-chip-container"] .MuiChip-label, .MuiChip-label');
    if (chip) rec.status = norm(chip.innerText);
  }
  r.querySelectorAll('[col-id]').forEach(c => {
    const h = headers[c.getAttribute('col-id')];
    if (h && !rec.cells[h]) rec.cells[h] = cellText(c);
  });
  if (!rec.link) { const id = findId(r); if (id) rec.link = ORIGIN + '/opportunities/' + id; }
  if (!rec.html && +idx === 0) rec.html = r.outerHTML.slice(0, 6000);
  rec.headers = Object.values(headers);
});
return Object.values(rows).filter(r => Object.values(r.cells).some(v => v));
"""

# Scrolls the grid's body (vertical) by `step` px; returns [scrollTop, maxScroll].
_SCROLL_GRID_JS = r"""
const grid = document.querySelector("[data-testid='opportunity-directory-grid']") || document;
const vp = grid.querySelector('.ag-body-viewport');
if (!vp) return [0, 0];
if (arguments[0] === 0) vp.scrollTop = 0; else vp.scrollTop += arguments[0];
return [vp.scrollTop, vp.scrollHeight - vp.clientHeight];
"""


_DUE_SPLIT = re.compile(r"^\s*([A-Za-z]{3,9}\.?\s+\d{1,2},\s*\d{4})\s*(.*)$")


def split_due(raw: str | None) -> tuple[str | None, str | None]:
    """"Dec 7, 202613 days" -> ("Dec 7, 2026", "13 days"). The date and the
    time-left share one cell; if the text doesn't fit that shape it is kept
    whole as the due date."""
    text = (raw or "").strip()
    m = _DUE_SPLIT.match(text)
    if not m:
        return (text or None), None
    return m.group(1).strip(), (m.group(2).strip() or None)


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
    h = header.lower().strip()
    if "project id" in h or h in ("id", "project #", "project no", "project number"):
        return "project_id"
    if "organization" in h or "agency" in h:
        return "organization"
    if h == "state" or h.startswith("state "):
        return "state"
    if "status" in h:
        return "status"
    if "release" in h or "posted" in h or "publish" in h:
        return "release_date"
    if "due" in h or "close" in h or "time left" in h:
        return "due_date"
    if "title" in h or h in ("project", "project name", "name"):
        return "project_title"
    return None


class OpenGovScraper(BaseScraper):
    """One run: sign in, read every current solicitation, and package the sheet."""

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
                lambda d: d.find_elements(By.XPATH, OPPORTUNITIES_XPATH)
            )
        except TimeoutException:
            self.screenshot("login_failed")
            raise OpenGovLoginError(
                "OpenGov login did not complete — the dashboard's Opportunities menu never "
                "appeared. Check OPENGOV_EMAIL / OPENGOV_PASSWORD in server/.env."
            )
        logger.info("[run %s] login successful; landed on %s", self.run_id, self.driver.current_url)

    # -- the opportunities table ---------------------------------------------------

    def open_opportunities(self) -> None:
        self.set_step("opening_opportunities")
        label = self.wait(30).until(
            EC.presence_of_element_located((By.XPATH, OPPORTUNITIES_XPATH))
        )
        target = self.driver.execute_script(
            "return arguments[0].closest('a, button, [role=button], li') || arguments[0];", label
        )
        self._safe_click(target)

    def _read_table(self) -> list[dict[str, Any]] | None:
        return self._read_grid()

    def _read_grid(self) -> list[dict[str, Any]] | None:
        """Every row of the current page. The grid only renders the rows in view,
        so scroll it top to bottom and merge by row-index."""
        merged: dict[int, dict[str, Any]] = {}
        header_seen = False
        self.driver.execute_script(_SCROLL_GRID_JS, 0)
        time.sleep(0.4)
        for _ in range(400):
            rows = self.driver.execute_script(_READ_GRID_JS)
            if rows is not None:
                header_seen = True
                for r in rows:
                    cur = merged.setdefault(r["index"], r)
                    if not cur.get("link") and r.get("link"):
                        cur["link"] = r["link"]
                    if not cur.get("status") and r.get("status"):
                        cur["status"] = r["status"]
                    if not cur.get("html") and r.get("html"):
                        cur["html"] = r["html"]
            top, limit = self.driver.execute_script(_SCROLL_GRID_JS, 400)
            time.sleep(0.25)
            if top >= limit:
                rows = self.driver.execute_script(_READ_GRID_JS) or []
                for r in rows:
                    cur = merged.setdefault(r["index"], r)
                    if not cur.get("link") and r.get("link"):
                        cur["link"] = r["link"]
                break
        if not header_seen:
            return None
        return [merged[i] for i in sorted(merged)]

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
                "OpenGov: the Current Solicitations table never appeared "
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
        if record.get("due_date"):
            record["due_date"], record["days_remaining"] = split_due(record["due_date"])
        if not record.get("status") and row.get("status"):
            record["status"] = row["status"]  # the green Open/Closed chip
        return record

    # -- list state (AG Grid) ----------------------------------------------------------

    def _await_idle(self) -> None:
        """Wait out the grid's loading overlay."""
        try:
            self.wait(TABLE_TIMEOUT).until(
                lambda d: not any(e.is_displayed() for e in d.find_elements(By.CSS_SELECTOR, LOADING_CSS))
            )
        except TimeoutException:
            pass

    def _first_row_signature(self) -> str:
        self.driver.execute_script(_SCROLL_GRID_JS, 0)
        rows = self.driver.execute_script(_READ_GRID_JS) or []
        rows = sorted(rows, key=lambda r: r["index"])
        return "|".join(rows[0]["cells"].values()) if rows else ""

    def _set_page_size(self) -> None:
        """Show 100 rows per page. Changing it resets the grid to page 1."""
        from selenium.webdriver.support.ui import Select

        els = self.driver.find_elements(By.XPATH, PAGE_SIZE_XPATH) or \
            self.driver.find_elements(By.CSS_SELECTOR, PAGE_SIZE_FALLBACK_CSS)
        els = [e for e in els if e.is_displayed()]
        if not els:
            logger.warning("[run %s] page-size control not found; using the default size", self.run_id)
            self._dump_page("no_page_size")
            return
        control = els[-1]
        self.scroll_into_view(control)
        if control.tag_name.lower() == "select":
            select = Select(control)
            if select.first_selected_option.get_attribute("value") != PAGE_SIZE:
                select.select_by_value(PAGE_SIZE)
        else:
            if PAGE_SIZE in (control.text or ""):
                return
            self._safe_click(control)
            try:
                option = self.wait(10).until(lambda d: next(
                    (o for o in d.find_elements(By.CSS_SELECTOR, OPTION_CSS)
                     if o.is_displayed() and o.text.strip() == PAGE_SIZE), None))
            except TimeoutException:
                logger.warning("[run %s] no %s option in the page-size list", self.run_id, PAGE_SIZE)
                self._dump_page("no_page_size_option")
                return
            self._safe_click(option)
        self._await_idle()
        time.sleep(SETTLE_SECONDS)

    def _next_enabled(self):
        for el in self.driver.find_elements(By.CSS_SELECTOR, NEXT_BUTTON_CSS):
            if not el.is_displayed():
                continue
            disabled = el.get_attribute("disabled") is not None or \
                el.get_attribute("aria-disabled") == "true" or \
                "ag-disabled" in (el.get_attribute("class") or "")
            if not disabled:
                return el
        return None

    # -- walking the list ------------------------------------------------------------

    def scrape_all_pages(self) -> None:
        self._await_table()
        self._set_page_size()
        total = "?"

        for page in range(1, MAX_PAGES + 1):
            self.raise_if_stopped()
            rows = self._read_table() or []
            if page == 1 and rows:
                logger.info("[run %s] grid columns: %s", self.run_id, rows[0].get("headers"))
            logger.info("[run %s] page %d/%s: %d row(s)", self.run_id, page, total, len(rows))
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
                    step=f"page {page}, row {index + 1}/{len(rows)}: "
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
            before = self._first_row_signature()
            self.scroll_into_view(nxt)
            self._safe_click(nxt)
            try:
                self.wait(PAGE_TURN_TIMEOUT).until(lambda d: self._first_row_signature() != before)
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
            self.open_opportunities()
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
