"""Selenium automation for Texas SmartBuy's ESBD (Electronic State Business Daily).

Flow: open https://www.txsmartbuy.gov/esbd (Solicitations tab) -> fill the
filters the console sent (agency name / number, status, class/item codes,
keyword, solicitation ID, date range or custom dates) -> Search -> Export to
CSV -> read the CSV ESBD downloads -> store the rows in the DB, from which the
Excel is built on demand. No login. The page is a single-page app: filters land
in the URL once Search runs, and the export follows the current search.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

from app.config import settings
from app.core import partials, run_manager
from app.core.base_scraper import BaseScraper, StopRequested
from app.core.exports import archive_run
from app.core.filenames import sanitize_filename
from app.scrapers.txsmartbuy import export, filters
from app.services.notifier import notify_scrape_completion

logger = logging.getLogger(__name__)

EXPORT_TIMEOUT = 600  # seconds; a 20,000-row export is much slower than the usual few seconds

# True once the Status dropdown has been visible, and not replaced, for 1.5 s.
_FORM_SETTLED = """
const s = document.querySelector('select[name=status]');
if (!s || !s.offsetParent) return false;
if (!s.__hubSeen) { s.__hubSeen = Date.now(); return false; }
return Date.now() - s.__hubSeen > 1500;
"""


def _visible_button(driver, text: str):
    """The page's own button (the header has a second 'Search' for products)."""
    buttons = [b for b in driver.find_elements(By.XPATH, f"//button[normalize-space()='{text}']") if b.is_displayed()]
    if not buttons:
        raise RuntimeError(f"ESBD page has no '{text}' button")
    return buttons[-1]


def _retry_stale(action, attempts: int = 3):
    """Run `action` (which looks its element up afresh), again if ESBD re-rendered it meanwhile."""
    for attempt in range(attempts):
        try:
            return action()
        except StaleElementReferenceException:
            if attempt == attempts - 1:
                raise


class TxSmartBuyScraper(BaseScraper):
    def __init__(self, run_id: str, criteria: dict[str, str]):
        super().__init__(run_id)
        self.criteria = criteria
        self._records: list[dict[str, Any]] = []

    # -- the flow -----------------------------------------------------------

    def open_esbd(self) -> None:
        self.set_step("opening_esbd")
        self.navigate(settings.txsmartbuy_esbd_url)
        # ESBD keeps the page hidden until its app has started, then re-renders the
        # form once more; touching it before that fails as "not interactable" or
        # "stale". Ready = the same Status dropdown has been drawn for 1.5 s.
        self.wait(90).until(lambda d: d.execute_script(_FORM_SETTLED))
        # Read the agency list in one script call so a re-render can't leave a
        # half-read list (or a stale element) behind.
        names = self.wait(60).until(lambda d: d.execute_script(
            "const s = document.querySelector('select[name=agency]');"
            "const n = s ? [...s.options].map(o => o.text.trim()).filter(Boolean) : [];"
            "return n.length > 10 ? n : null;"
        ))
        filters.save_agencies(names)  # keeps the console's agency dropdown in step with the portal's

    def apply_filters(self) -> None:
        self.set_step("applying_filters")
        c, d = self.criteria, self.driver
        select = lambda name: Select(d.find_element(By.NAME, name))  # noqa: E731
        typed = lambda name: d.find_element(By.NAME, name)  # noqa: E731
        if c.get("agency"):
            try:
                _retry_stale(lambda: select("agency").select_by_visible_text(c["agency"]))
            except StaleElementReferenceException:
                raise
            except Exception as exc:  # noqa: BLE001 — say which value, not a Selenium trace
                raise RuntimeError(f"ESBD no longer lists the agency {c['agency']!r}") from exc
        for name, key in (("agencyNumber", "agency_number"), ("nigp", "class_item_codes"),
                          ("keyword", "keyword"), ("solicitationId", "solicitation_id")):
            if c.get(key):
                _retry_stale(lambda name=name, key=key: typed(name).send_keys(c[key]))
        if c.get("status"):
            _retry_stale(lambda: select("status").select_by_value(c["status"]))
        if c.get("date_range", "custom") != "custom":
            _retry_stale(lambda: select("dateRange").select_by_value(c["date_range"]))  # fills its own dates
        else:
            for name, key in (("startDate", "start_date"), ("endDate", "end_date")):
                if c.get(key):
                    _retry_stale(lambda name=name, key=key: typed(name).send_keys(filters.portal_date(c[key])))

    def search_and_export(self) -> Path:
        self.set_step("searching")
        _visible_button(self.driver, "Search").click()
        self.wait(60).until(lambda drv: "page=" in drv.current_url)  # Search writes the filters into the URL
        self.raise_if_stopped()

        self.set_step("exporting_csv")
        before = set(self.download_dir.iterdir())
        _visible_button(self.driver, "Export to CSV").click()
        return self.wait_for_download(timeout=EXPORT_TIMEOUT, ignore=before)

    def flush_partial(self) -> int:
        run = run_manager.get_run(self.run_id) or {}
        return partials.flush_records(
            self,
            self._records,
            save_bids=export.save_bids,
            write_sheet=export.generate_excel_from_records,
            sheet_name=f"TxSmartBuy_({(run.get('search') or 'all solicitations').strip()})",
        )

    def run(self) -> None:
        run_manager.update_run(self.run_id, status="running")
        self._save_run_row()
        try:
            self.start_driver()
            self.open_esbd()
            self.apply_filters()
            csv_path = self.search_and_export()

            self.set_step("reading_csv")
            self._records = export.read_csv(csv_path)
            count = len(self._records)
            preview = [{k: v for k, v in r.items() if k != "raw"} for r in self._records[:200]]  # the raw row is for the DB
            run_manager.update_run(self.run_id, bids_found=count, bids_processed=count, bids=preview)
            if not count:
                run_manager.update_run(self.run_id, no_results=True)
            elif count >= export.CSV_LIMIT:
                run_manager.add_warning(
                    self.run_id,
                    f"ESBD exports at most {export.CSV_LIMIT:,} results, so this search may be cut off. Narrow the filters.",
                )

            run = run_manager.get_run(self.run_id) or {"run_id": self.run_id}
            db_ok = True
            try:
                run_manager.update_run(self.run_id, bids_stored_in_db=export.save_bids(run, self._records))
            except Exception:  # noqa: BLE001 — DB issues shouldn't abort the run
                db_ok = False
                logger.exception("[run %s] DB save failed", self.run_id)
                run_manager.add_error(self.run_id, "db save failed (see logs)")
                run_manager.update_run(self.run_id, db_save_failed=True)

            self.set_step("generating_excel")
            if db_ok:
                run_manager.update_run(self.run_id, excel_exported=True)  # rebuilt from the DB on download
            else:
                name = sanitize_filename(f"TxSmartBuy_({run.get('search') or 'all solicitations'})", max_length=150)
                path = self.run_dir / f"{name}.xlsx"
                export.generate_excel_from_records(self._records, path)
                run_manager.update_run(self.run_id, excel_path=str(path), excel_exported=True)

            self.set_step("packaging_results")
            archive_run(self.run_id)
            run_manager.update_run(self.run_id, status="completed", step="done")
            notify_scrape_completion(self.run_id, "txsmartbuy", count)
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
    TxSmartBuyScraper(run_id, criteria).run()
