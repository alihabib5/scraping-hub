"""COMMBUYS: the bid list read, the Available Date range, Pass / Reject, and the API.

    server/.venv/Scripts/python -m pytest server/tests/test_commbuys.py
"""

import os
import sys
from datetime import date

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main  # noqa: E402
from app.core import exports, run_manager  # noqa: E402
from app.scrapers.commbuys import evaluation, export, filters, router, scraper  # noqa: E402

# The open-bids list's real header (2026-11-18), Q & A / Quotes / Bid Holder included.
HEADER = ["Bid #", "Organization", "Alternate Id", "Buyer", "Description", "Purchase Method",
          "Bid Opening Date", "Bid Q & A", "Quotes", "Bid Holder"]
ROWS = [
    ["BD-27-1817-HA309-HA309-135486", "West Springfield Housing Authority", "", "Hugh Mackay",
     "Federal Pacific Panel Replacement and Asbestos work", "Open Market", "11/30/2026 02:00:00 PM", "View", "Create New", ""],
    ["", "a row without a bid number", "", "", "", "", "", "", "", ""],
]


def test_list_rows_are_read_by_header_and_link_the_public_page():
    records = scraper.rows_to_records(HEADER, ROWS)
    assert [r["bid_number"] for r in records] == ["BD-27-1817-HA309-HA309-135486"]
    r = records[0]
    assert r["organization"] == "West Springfield Housing Authority" and r["purchase_method"] == "Open Market"
    assert r["opening_date"] == "11/30/2026 02:00:00 PM"
    # The public page, never the list's own link (bidAck.sda acts on the vendor account).
    assert r["detail_url"] == ("https://www.commbuys.com/bso/external/bidDetail.sdo"
                               "?docId=BD-27-1817-HA309-HA309-135486&external=true&parentUrl=close")
    assert "bidAck" not in r["detail_url"]


def test_a_list_without_its_columns_is_refused():
    with pytest.raises(ValueError, match="missing columns"):
        scraper.rows_to_records(["Something"], [["x"]])


def test_the_pager_counter_is_read():
    assert scraper.counter_range("1-25 of 593") == (1, 25, 593)
    assert scraper.counter_range("576-593 of 593") == (576, 593, 593)
    assert scraper.counter_range("0-0 of 0") == (0, 0, 0)
    assert scraper.counter_range(None) is None


def test_the_available_date_is_read_from_a_bid_page():
    # As the bid page's text arrives: spaced out, with a no-break space.
    page = "Bid Opening Date: 11/30/2026 02:00:00 PM Available Date\n      :\xa011/17/2026 02:41:39 PM Info Contact: x"
    assert filters.available_date(page) == "11/17/2026 02:41:39 PM"
    assert filters.available_date("status 202") == ""


def test_the_range_is_inclusive_and_open_ended():
    start, end = date(2026, 11, 15), date(2026, 11, 18)
    assert filters.in_range("11/15/2026 12:00:01 AM", start, end)
    assert filters.in_range("11/18/2026 11:59:00 PM", start, end)
    assert not filters.in_range("11/14/2026 11:59:00 PM", start, end)
    assert filters.in_range("01/01/2030", start, None) and filters.in_range("01/01/2000", None, end)
    assert not filters.in_range("", start, end)  # no date cannot be shown to be in range


def test_the_summary_names_the_range():
    assert filters.summary({}) == "all open bids"
    assert filters.summary({"available_from": "2026-11-15", "available_to": "2026-11-18"}) == "available 2026-11-15 to 2026-11-18"
    assert filters.summary({"available_from": "2026-11-15"}) == "available from 2026-11-15"
    assert filters.summary({"available_to": "2026-11-18"}) == "available until 2026-11-18"


def test_every_bid_is_pass_reject_or_manual_review(monkeypatch):
    verdicts = iter([{"decision": "PURSUE", "reason": "hardware"}, {"decision": "REJECT", "reason": "service"},
                     {"decision": "MANUAL_REVIEW", "reason": "unlisted service"}])
    monkeypatch.setattr(evaluation, "evaluate_bid", lambda *a, **k: next(verdicts))
    records = [{"bid_number": "1", "description": "Trucks"}, {"bid_number": "2", "description": "Janitorial"},
               {"bid_number": "3", "description": "Census"}]
    assert evaluation.apply(records) == 1
    assert [r["decision"] for r in records] == ["PASS", "REJECT", "MANUAL REVIEW"]
    assert records[2]["decision_reason"] == "unlisted service"


def test_a_bid_the_matrix_cannot_judge_goes_to_manual_review(monkeypatch):
    monkeypatch.setattr(evaluation, "evaluate_bid", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    decision, reason = evaluation.decide({"bid_number": "1", "description": "x"})
    assert decision == "MANUAL REVIEW" and "RuntimeError" in reason


def test_the_excel_is_one_sheet_with_every_verdict(tmp_path):
    base = scraper.rows_to_records(HEADER, ROWS)[0]
    records = [dict(base, decision="PASS", decision_reason="ok"),
               dict(base, bid_number="BD-2", decision="REJECT", decision_reason="no"),
               dict(base, bid_number="BD-3", decision="MANUAL REVIEW", decision_reason="?")]
    out = tmp_path / "c.xlsx"
    assert export.generate_excel_from_records(records, out) == 3
    book = load_workbook(out)
    assert book.sheetnames == ["COMMBUYS Bids"]
    sheet = book.active
    assert [c.value for c in sheet[1]] == ["Bid #", "Organization", "Alternate Id", "Buyer", "Description",
                                           "Purchase Method", "Bid Opening Date", "Available Date", "Bid Link",
                                           "Decision", "Reason"]
    assert [row[9] for row in sheet.iter_rows(min_row=2, values_only=True)] == ["PASS", "REJECT", "MANUAL REVIEW"]
    fills = [sheet.cell(row=r, column=1).fill.fgColor.rgb for r in (2, 3, 4)]
    assert len(set(fills)) == 3  # pass plain, reject red, review yellow


@pytest.mark.parametrize("bad", [{"available_from": "11/15/2026"},
                                 {"available_from": "2026-11-18", "available_to": "2026-11-15"}])
def test_bad_dates_are_refused_before_a_run_exists(monkeypatch, bad):
    monkeypatch.setattr(router.settings, "commbuys_username", "u")
    monkeypatch.setattr(router.settings, "commbuys_password", "p")
    monkeypatch.setattr(router.jobs, "submit", lambda *a, **k: pytest.fail("a run was started"))
    assert TestClient(main.app).post("/commbuys/scrape", json=bad).status_code == 422


def test_a_run_needs_the_credentials(monkeypatch):
    monkeypatch.setattr(router.settings, "commbuys_username", "")
    monkeypatch.setattr(router.jobs, "submit", lambda *a, **k: pytest.fail("a run was started"))
    response = TestClient(main.app).post("/commbuys/scrape", json={})
    assert response.status_code == 400 and "COMMBUYS_USERNAME" in response.json()["detail"]


def test_starting_a_run_hands_the_range_to_the_scraper(monkeypatch, tmp_path):
    monkeypatch.setattr(router.settings, "commbuys_username", "u")
    monkeypatch.setattr(router.settings, "commbuys_password", "p")
    submitted = {}
    monkeypatch.setattr(router.jobs, "submit", lambda run_id, fn, *args: submitted.update(args=args))
    monkeypatch.setattr(router.run_manager, "make_run_folder", lambda name: tmp_path / name)
    body = TestClient(main.app).post("/commbuys/scrape", json={"available_from": " 2026-11-15 ", "available_to": "2026-11-18"}).json()
    assert body["search"] == "available 2026-11-15 to 2026-11-18"
    assert submitted["args"][1] == {"available_from": "2026-11-15", "available_to": "2026-11-18"}
    assert run_manager.get_run(body["run_id"])["scraper"] == "commbuys"


def test_the_download_is_a_dated_excel():
    run = {"run_id": "r1", "scraper": "commbuys", "search": "available 2026-11-15 to 2026-11-18"}
    assert exports.is_excel_only(run)
    assert exports.excel_name(run) == "COMMBUYS_(available 2026-11-15 to 2026-11-18).xlsx"
