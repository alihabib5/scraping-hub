"""BaseScraper.navigate: a slow page load is retried, not a failed run.

    server/.venv/Scripts/python -m pytest server/tests/test_navigate_retry.py
"""

import os
import sys

import pytest
from selenium.common.exceptions import TimeoutException, WebDriverException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import base_scraper  # noqa: E402
from app.core.base_scraper import BaseScraper  # noqa: E402

# What EMMA's run 1648b6d1a5cc died of on 17 Nov: the sign-in page took longer than
# the 60 s page-load limit once, and the next run 25 minutes later went through.
RENDERER = "timeout: Timed out receiving message from renderer: 57.988\n  (Session info: chrome=157.0.8103.79)"


class FlakyDriver:
    def __init__(self, failures):
        self.failures = list(failures)
        self.loads = 0

    def get(self, url):
        self.loads += 1
        if self.failures:
            raise self.failures.pop(0)


def _scraper(driver, monkeypatch):
    monkeypatch.setattr(base_scraper.time, "sleep", lambda s: None)
    scraper = BaseScraper.__new__(BaseScraper)
    scraper.run_id, scraper.driver = "t", driver
    scraper.raise_if_stopped = lambda: None
    return scraper


def test_a_renderer_timeout_is_retried(monkeypatch):
    driver = FlakyDriver([TimeoutException(RENDERER)])
    _scraper(driver, monkeypatch).navigate("https://emma.maryland.gov/")
    assert driver.loads == 2


def test_a_page_that_never_loads_still_fails_with_the_host(monkeypatch):
    driver = FlakyDriver([TimeoutException(RENDERER)] * base_scraper.NAVIGATE_ATTEMPTS)
    with pytest.raises(WebDriverException, match="emma.maryland.gov"):
        _scraper(driver, monkeypatch).navigate("https://emma.maryland.gov/")
    assert driver.loads == base_scraper.NAVIGATE_ATTEMPTS


def test_a_real_navigation_error_is_not_retried(monkeypatch):
    driver = FlakyDriver([WebDriverException("invalid argument: 'url' must be a string")])
    with pytest.raises(WebDriverException, match="invalid argument"):
        _scraper(driver, monkeypatch).navigate("https://emma.maryland.gov/")
    assert driver.loads == 1


def test_the_driver_pool_warning_is_dropped_but_a_website_one_is_kept(caplog):
    # The warning seen on 18 Nov while the Live Preview modal was open.
    pool_log = base_scraper.logging.getLogger("urllib3.connectionpool")
    with caplog.at_level("WARNING", logger="urllib3.connectionpool"):
        pool_log.warning("Connection pool is full, discarding connection: %s. Connection pool size: %s", "localhost", 1)
        pool_log.warning("Connection pool is full, discarding connection: %s. Connection pool size: %s", "emma.maryland.gov", 1)
    assert [r.getMessage() for r in caplog.records] == [
        "Connection pool is full, discarding connection: emma.maryland.gov. Connection pool size: 1"]
