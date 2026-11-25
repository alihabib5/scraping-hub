"""The installer's bundled chromedriver, and when the scrapers use it.

    server/.venv/Scripts/python -m pytest server/tests/test_chromedriver.py
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import base_scraper, chromedriver  # noqa: E402


@pytest.fixture
def shipped(tmp_path, monkeypatch):
    """A bundled driver for Chrome 158, where the installed app keeps it."""
    folder = tmp_path / "chromedriver"
    folder.mkdir()
    (folder / "chromedriver.exe").write_bytes(b"MZ")
    (folder / "version.txt").write_text("158.0.8127.88", encoding="utf-8")
    monkeypatch.setenv(chromedriver.DIR_SETTING, str(folder))
    return folder


def test_the_bundled_driver_is_used_for_the_same_chrome_major(shipped):
    assert chromedriver.bundled_driver("158.0.8127.120") == str(shipped / "chromedriver.exe")


def test_a_chrome_that_updated_past_it_gets_the_download_instead(shipped):
    # Chrome updates itself; a 158 driver cannot drive Chrome 159.
    assert chromedriver.bundled_driver("159.0.8200.1") is None


def test_an_unreadable_chrome_version_still_uses_the_bundled_driver(shipped, monkeypatch):
    monkeypatch.setattr(chromedriver, "installed_chrome_version", lambda: None)
    assert chromedriver.bundled_driver() == str(shipped / "chromedriver.exe")


def test_no_bundled_driver_in_development(tmp_path, monkeypatch):
    monkeypatch.setenv(chromedriver.DIR_SETTING, str(tmp_path / "nothing-here"))
    assert chromedriver.bundled_driver("158.0.1.1") is None


def test_the_scrapers_take_the_bundled_driver_without_downloading(shipped, monkeypatch):
    monkeypatch.setattr(chromedriver, "installed_chrome_version", lambda: "158.0.8127.120")

    def no_download():
        raise AssertionError("webdriver-manager was asked to download a driver")

    monkeypatch.setattr(base_scraper, "ChromeDriverManager", no_download)
    assert base_scraper._resolve_chromedriver() == str(shipped / "chromedriver.exe")


def test_a_mismatched_bundled_driver_falls_back_to_the_download(shipped, monkeypatch):
    monkeypatch.setattr(chromedriver, "installed_chrome_version", lambda: "159.0.8200.1")
    monkeypatch.setattr(base_scraper, "_clear_stale_wdm_locks", lambda max_age=300: None)

    class FakeManager:
        def install(self):
            return r"C:\Users\x\.wdm\drivers\chromedriver\159\chromedriver.exe"

    monkeypatch.setattr(base_scraper, "ChromeDriverManager", FakeManager)
    assert base_scraper._resolve_chromedriver().endswith(r"159\chromedriver.exe")
