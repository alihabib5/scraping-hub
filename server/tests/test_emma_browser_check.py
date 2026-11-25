"""EMMA's browser check ("I'm not a robot") must never let an unread bid pass.

Run a641c5f0b961 (18 Nov): EMMA answered 11 bid pages with its browser check,
the scraper read 0 fields and 0 documents from each, screened them on their
titles alone, and all 11 "passed". These tests stub the browser out.

    server/.venv/Scripts/python -m pytest server/tests/test_emma_browser_check.py
"""

import os
import sys
import time

import pytest
from selenium.common.exceptions import TimeoutException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import run_manager  # noqa: E402
from app.scrapers.emma import scraper as emma  # noqa: E402
from app.scrapers.emma.scraper import NOT_READ, BidPageNotRead, EmmaScraper  # noqa: E402


@pytest.fixture(autouse=True)
def _no_db_persistence(monkeypatch):
    """Runs created here must not land in the real run_state table."""
    monkeypatch.setattr(run_manager, "_persist", lambda run: None)


@pytest.fixture
def scraper(tmp_path, monkeypatch):
    run = run_manager.create_run("emma", tmp_path, {"search": "test"})
    s = EmmaScraper(run["run_id"])
    monkeypatch.setattr(s, "_restart_browser", lambda: True)
    return s


def _bid(emma_id, title="Laboratory Equipment"):
    return {
        "emma_id": emma_id,
        "bpm_code": f"BPM{emma_id}",
        "title": title,
        "detail_url": f"https://emma.example/{emma_id}",
        "documents": [],
    }


def _reader(blocked: dict[str, int]):
    """A page reader that hits the browser check `blocked[id]` times first."""
    opened: list[str] = []

    def read(url, rec):
        opened.append(rec["emma_id"])
        if blocked.get(rec["emma_id"], 0) > 0:
            blocked[rec["emma_id"]] -= 1
            raise BidPageNotRead("EMMA showed its browser check instead of the bid")
        rec["detail"] = {"Title": rec["title"]}
        return []

    return read, opened


def test_a_bid_behind_the_check_is_not_read_and_does_not_pass(scraper, monkeypatch):
    scraper._records = [_bid("1"), _bid("2")]
    read, _ = _reader({"2": 2})  # blocked, and still blocked in the fresh browser
    monkeypatch.setattr(scraper, "_download_solicitation_docs", read)
    scraper.download_all_documents()

    state = run_manager.get_run(scraper.run_id)
    assert [r["emma_id"] for r in scraper._records] == ["1"]
    assert state["bids_not_read"] == 1
    assert any("BPM2" in w and "could not be read" in w for w in state["warnings"])


def test_a_fresh_browser_that_gets_past_the_check_reads_the_bid(scraper, monkeypatch):
    scraper._records = [_bid("1")]
    read, opened = _reader({"1": 1})
    monkeypatch.setattr(scraper, "_download_solicitation_docs", read)
    scraper.download_all_documents()

    assert opened == ["1", "1"]
    assert [r["emma_id"] for r in scraper._records] == ["1"]
    assert run_manager.get_run(scraper.run_id)["bids_not_read"] == 0


def test_the_run_stops_opening_pages_when_emma_keeps_blocking(scraper, monkeypatch):
    scraper._records = [_bid(str(i)) for i in range(1, 7)]
    scraper._records.append(_bid("7", "Building Construction"))  # its title rejects it
    read, opened = _reader({str(i): 9 for i in range(1, 8)})
    monkeypatch.setattr(scraper, "_download_solicitation_docs", read)
    scraper.download_all_documents()

    state = run_manager.get_run(scraper.run_id)
    assert sorted(set(opened)) == ["1", "2", "3"], "stops after three unread in a row"
    assert scraper._records == []
    assert state["bids_not_read"] == 6
    assert state["bids_rejected_by_keyword"] == 1
    assert any("kept blocking" in e for e in state["errors"])


def test_a_page_with_none_of_the_bids_fields_counts_as_unread(scraper, monkeypatch):
    monkeypatch.setattr(emma, "DETAIL_FIELDS_WAIT", 0)
    monkeypatch.setattr(emma.time, "sleep", lambda s: None)
    monkeypatch.setattr(scraper, "navigate", lambda url: None)
    monkeypatch.setattr(scraper, "_wait_past_browser_check", lambda timeout=0: True)
    monkeypatch.setattr(scraper, "_extract_detail_fields", lambda: {})
    with pytest.raises(BidPageNotRead):
        scraper._download_solicitation_docs("https://emma.example/1", _bid("1"))


def test_the_check_that_never_clears_counts_as_unread(scraper, monkeypatch):
    monkeypatch.setattr(emma.time, "sleep", lambda s: None)
    monkeypatch.setattr(scraper, "navigate", lambda url: None)
    monkeypatch.setattr(scraper, "_wait_past_browser_check", lambda timeout=0: False)
    with pytest.raises(BidPageNotRead, match="browser check"):
        scraper._download_solicitation_docs("https://emma.example/1", _bid("1"))


def test_a_check_that_clears_by_itself_lets_the_run_carry_on(scraper, monkeypatch):
    showing = iter([True, True, False])
    monkeypatch.setattr(scraper, "_browser_check_showing", lambda: next(showing))
    monkeypatch.setattr(scraper, "screenshot", lambda name: None)
    monkeypatch.setattr(scraper, "_dump_page", lambda name: None)
    monkeypatch.setattr(emma.time, "sleep", lambda s: None)
    assert scraper._wait_past_browser_check(timeout=60) is True
    assert any("browser check" in w for w in run_manager.get_run(scraper.run_id)["warnings"])


def test_a_stalled_download_gives_up_early(scraper):
    (scraper.download_dir / "Attachment D.pdf.crdownload").write_bytes(b"x" * 442)
    started = time.monotonic()
    with pytest.raises(TimeoutException, match="stalled"):
        scraper.wait_for_download(timeout=30, stall_after=1)
    assert time.monotonic() - started < 10


def test_a_stuck_half_file_from_before_is_not_waited_on(scraper):
    stuck = scraper.download_dir / "old.pdf.crdownload"
    stuck.write_bytes(b"x")
    before = {stuck}
    (scraper.download_dir / "Attachment D.pdf").write_bytes(b"%PDF")
    assert scraper.wait_for_download(timeout=5, ignore=before).name == "Attachment D.pdf"
