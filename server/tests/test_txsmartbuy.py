"""Texas SmartBuy ESBD: the CSV export read, the filter summary, and the API.

    server/.venv/bin/python -m pytest server/tests/test_txsmartbuy.py
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main  # noqa: E402
from app.core import exports, run_manager  # noqa: E402
from app.scrapers.txsmartbuy import export, filters, router  # noqa: E402

# The real header ESBD's "Export to CSV" writes (2026-11-17), columns shuffled
# here on purpose: rows are read by header name, not position.
CSV = (
    "Solicitation ID,Name,Due Date,Due Time,Agency/Texas SmartBuy Member Number,Status,"
    "Posting Date,Created,Last Modified,NIGP Codes\n"
    "6513-10-001_1226,\"LOCAL LET MAINTENANCE CONTRACT, ECTOR CO, PAINT AND BEADS\",12/8/2026,10:00 AM,601,Posted,"
    "11/16/2026,11/16/2026 2:01 pm,11/16/2026 2:01 pm,91371-Maintenance And Repair\n"
    ",row without an id,,,,,,,,\n"
    "RFQ 26/03,Aviation consultants,12/29/2026,2:00 PM,601,Posted,11/16/2026,x,y,92508-Airports\n"
)


def test_the_export_is_read_by_column_name(tmp_path):
    path = tmp_path / "ESBD Solicitations Export.csv"
    path.write_text("﻿" + CSV, encoding="utf-8")  # ESBD may send a BOM
    records = export.read_csv(path)
    assert [r["solicitation_id"] for r in records] == ["6513-10-001_1226", "RFQ 26/03"]
    first = records[0]
    assert first["name"] == "LOCAL LET MAINTENANCE CONTRACT, ECTOR CO, PAINT AND BEADS"
    assert first["agency_number"] == "601" and first["nigp_codes"] == "91371-Maintenance And Repair"
    assert first["detail_url"] == "https://www.txsmartbuy.gov/esbd/6513-10-001_1226"
    assert records[1]["detail_url"] == "https://www.txsmartbuy.gov/esbd/RFQ%2026/03"


def test_an_export_with_unexpected_columns_is_refused(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("Name,Something Else\nA,B\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        export.read_csv(path)


def test_the_excel_has_the_csv_columns_plus_the_link(tmp_path):
    path = tmp_path / "e.csv"
    path.write_text(CSV, encoding="utf-8")
    out = tmp_path / "out.xlsx"
    assert export.generate_excel_from_records(export.read_csv(path), out) == 2
    header = [c.value for c in next(load_workbook(out).active.iter_rows(max_row=1))]
    assert header == ["Name", "Solicitation ID", "Due Date", "Due Time", "Agency/Texas SmartBuy Member Number",
                      "Status", "Posting Date", "Created", "Last Modified", "NIGP Codes", "Bid Link"]


def test_the_summary_names_filters_and_dates():
    assert filters.summary({}) == "all solicitations"
    assert filters.summary({"keyword": "trailer", "status": "1", "date_range": "thisWeek"}) == "status=Posted, keyword=trailer, this week"
    assert filters.summary({"agency_number": "601", "date_range": "custom", "start_date": "2026-11-01", "end_date": "2026-11-16"}) \
        == "agency no.=601, 2026-11-01 to 2026-11-16"
    assert filters.portal_date("2026-11-01") == "11/01/2026"


def test_the_filters_endpoint_mirrors_the_portal():
    body = TestClient(main.app).get("/txsmartbuy/filters").json()
    assert len(body["agencies"]) > 300  # ESBD lists ~413 members
    assert [s["label"] for s in body["statuses"]] == ["Select All", "Posted", "Awarded", "No Award", "Closed", "Posting Cancelled"]
    assert body["date_ranges"][0] == {"value": "custom", "label": "Custom"}


@pytest.mark.parametrize("bad", [{"status": "99"}, {"date_range": "someday"}, {"start_date": "11/01/2026"},
                                 {"start_date": "2026-11-20", "end_date": "2026-11-01"}])
def test_bad_filters_are_refused_before_a_run_exists(monkeypatch, bad):
    monkeypatch.setattr(router.jobs, "submit", lambda *a, **k: pytest.fail("a run was started"))
    assert TestClient(main.app).post("/txsmartbuy/scrape", json=bad).status_code == 422


def test_starting_a_run_hands_the_filters_to_the_scraper(monkeypatch, tmp_path):
    submitted = {}
    monkeypatch.setattr(router.jobs, "submit", lambda run_id, fn, *args: submitted.update(run_id=run_id, args=args))
    monkeypatch.setattr(router.run_manager, "make_run_folder", lambda name: tmp_path / name)
    body = TestClient(main.app).post("/txsmartbuy/scrape", json={"keyword": " trailer ", "status": "1", "date_range": "thisMonth"}).json()
    assert body["search"] == "status=Posted, keyword=trailer, this month"
    criteria = submitted["args"][1]
    assert criteria["keyword"] == "trailer" and criteria["status"] == "1" and criteria["date_range"] == "thisMonth"
    run = run_manager.get_run(body["run_id"])
    assert run["scraper"] == "txsmartbuy" and run["criteria"] == criteria


def test_the_download_is_a_dated_excel():
    run = {"run_id": "r1", "scraper": "txsmartbuy", "search": "status=Posted, 2026-11-01 to 2026-11-16"}
    assert exports.is_excel_only(run)
    assert exports.excel_name(run) == "TxSmartBuy_(status=Posted, 2026-11-01 to 2026-11-16).xlsx"


def test_an_open_ended_date_range_reads_plainly():
    assert filters.summary({"status": "1", "date_range": "custom", "start_date": "2026-11-16"}) == "status=Posted, from 2026-11-16"
    assert filters.summary({"date_range": "custom", "end_date": "2026-11-30"}) == "until 2026-11-30"


def test_an_excel_download_with_a_non_latin_name_does_not_crash(monkeypatch):
    # The 500 seen on 17 Nov: "… " in a run's name could not go into an HTTP header.
    from app.core import download_router

    monkeypatch.setattr(download_router.exports, "excel_bytes", lambda run: (b"xlsx", "TxSmartBuy_(2026-11-16 to …, Zürich).xlsx"))
    response = download_router._excel_response({"run_id": "r1"})
    header = response.headers["content-disposition"]
    assert "filename*=UTF-8''TxSmartBuy_%282026-11-16%20to%20%E2%80%A6%2C%20Z%C3%BCrich%29.xlsx" in header
    assert header.startswith('attachment; filename="TxSmartBuy_(2026-11-16 to ?, Z?rich).xlsx"')
