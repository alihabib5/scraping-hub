"""Download names: Philadelphia and Unison carry the run's day, like SAM / SEPTA carry their dates.

    server/.venv/bin/python -m pytest server/tests/test_export_names.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.exports import excel_name  # noqa: E402

DAY = "2026-11-13T22:14:05.123456"


def test_philadelphia_and_unison_names_carry_the_run_day():
    assert excel_name({"run_id": "a", "scraper": "philadelphia", "started_at": DAY}) == "Philadelphia_(all open bids, 2026-11-13).xlsx"
    assert excel_name({"run_id": "b", "scraper": "unison", "started_at": DAY}) == "Unison_(all requests, 2026-11-13).xlsx"
    assert excel_name({"run_id": "c", "scraper": "philadelphia", "search": "IT services", "started_at": DAY}) == "Philadelphia_(IT services, 2026-11-13).xlsx"


def test_other_portals_are_unchanged():
    assert excel_name({"run_id": "d", "scraper": "septa", "search": "open quotes opening from 2026-11-13", "started_at": DAY}) == "Septa_(open quotes opening from 2026-11-13).xlsx"
    assert excel_name({"run_id": "e", "scraper": "philadelphia"}) == "Philadelphia_(all open bids).xlsx"  # no start time recorded
