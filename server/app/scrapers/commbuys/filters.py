"""COMMBUYS's one console filter — the Available Date range — and the run's summary.

The open-bids list has no filters worth mirroring and does not show a bid's
Available Date; that is read from each bid's public page and the range is applied
here, after the list is scraped. Both ends are inclusive and either may be blank.
"""

from __future__ import annotations

import re
from datetime import date, datetime

_AVAILABLE = re.compile(r"Available Date\s*:\s*(\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?\s*[AP]M)?)", re.I)


def parse_iso(iso: str) -> date | None:
    """'2026-11-01' (the console's date fields) -> a date; raises on anything else."""
    return date.fromisoformat(iso) if iso else None


def available_date(page_text: str) -> str:
    """'11/17/2026 02:41:39 PM' from a bid page's text, or '' when it has none."""
    match = _AVAILABLE.search(" ".join(page_text.replace("\xa0", " ").split()))
    return match.group(1) if match else ""


def as_date(value: str) -> date | None:
    """The day part of COMMBUYS's '11/17/2026 02:41:39 PM'."""
    try:
        return datetime.strptime(value.split()[0], "%m/%d/%Y").date() if value else None
    except ValueError:
        return None


def in_range(value: str, start: date | None, end: date | None) -> bool:
    day = as_date(value)
    if day is None:
        return False  # no readable date cannot be shown to be in the range
    return (start is None or day >= start) and (end is None or day <= end)


def summary(f: dict[str, str]) -> str:
    """The run's filters in one line; also names its Excel. Dates included, like SAM / SEPTA."""
    start, end = f.get("available_from"), f.get("available_to")
    if start and end:
        return f"available {start} to {end}"
    if start:
        return f"available from {start}"
    if end:
        return f"available until {end}"
    return "all open bids"
