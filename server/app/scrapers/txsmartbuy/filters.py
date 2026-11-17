"""The ESBD Solicitations filters, mirrored for the console, and the run's search summary.

ESBD: https://www.txsmartbuy.gov/esbd. Status and Date Range values are the
portal's own <option> values. The agency list is ESBD's dropdown, refreshed from
the live page on every run (it changes as members join); `agencies.json` beside
this file is the copy shipped for before the first run.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path

from app.config import SERVER_ROOT

logger = logging.getLogger(__name__)

STATUSES: dict[str, str] = {
    "": "Select All", "1": "Posted", "2": "Awarded", "11": "No Award", "5": "Closed", "3": "Posting Cancelled",
}
DATE_RANGES: dict[str, str] = {
    "custom": "Custom", "thisWeek": "This Week", "thisMonth": "This Month", "thisFiscalYear": "This Fiscal Year",
    "lastWeek": "Last Week", "lastMonth": "Last Month", "lastFiscalYear": "Last Fiscal Year",
}

BUNDLED_AGENCIES = Path(__file__).with_name("agencies.json")
# The installed Windows app keeps what it writes under SCRAPING_HUB_DATA_DIR; read
# straight from the environment (as the SAM engine does), not via app.config.
_DATA_DIR = os.environ.get("SCRAPING_HUB_DATA_DIR", "")
AGENCY_CACHE = (Path(_DATA_DIR) if _DATA_DIR else SERVER_ROOT / "data") / "txsmartbuy_agencies.json"


def agencies() -> list[str]:
    """ESBD's agency names: the copy the last run saw, else the shipped one."""
    for path in (AGENCY_CACHE, BUNDLED_AGENCIES):
        try:
            names = json.loads(path.read_text(encoding="utf-8"))
            if names:
                return names
        except (OSError, ValueError):
            continue
    return []


def save_agencies(names: list[str]) -> None:
    if not names:
        return
    try:
        AGENCY_CACHE.parent.mkdir(parents=True, exist_ok=True)
        AGENCY_CACHE.write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")
    except OSError:
        logger.warning("could not save the ESBD agency list to %s", AGENCY_CACHE)


def portal_date(iso: str) -> str:
    """'2026-11-01' (the console's date fields) -> '11/01/2026' (what ESBD expects)."""
    return date.fromisoformat(iso).strftime("%m/%d/%Y") if iso else ""


def summary(f: dict[str, str]) -> str:
    """The run's filters in one line; also names its Excel. Dates included, like SAM / SEPTA."""
    parts = [
        f"agency={f['agency']}" if f.get("agency") else "",
        f"agency no.={f['agency_number']}" if f.get("agency_number") else "",
        f"status={STATUSES[f['status']]}" if f.get("status") else "",
        f"codes={f['class_item_codes']}" if f.get("class_item_codes") else "",
        f"keyword={f['keyword']}" if f.get("keyword") else "",
        f"id={f['solicitation_id']}" if f.get("solicitation_id") else "",
    ]
    if f.get("date_range", "custom") != "custom":
        parts.append(DATE_RANGES[f["date_range"]].lower())
    elif f.get("start_date") and f.get("end_date"):
        parts.append(f"{f['start_date']} to {f['end_date']}")
    elif f.get("start_date"):
        parts.append(f"from {f['start_date']}")
    elif f.get("end_date"):
        parts.append(f"until {f['end_date']}")
    return ", ".join(p for p in parts if p) or "all solicitations"
