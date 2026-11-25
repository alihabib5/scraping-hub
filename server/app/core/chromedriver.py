"""Which chromedriver the scrapers start Chrome with.

The installed app ships a chromedriver beside the engine
(<install>\\server\\chromedriver\\chromedriver.exe, with version.txt), fetched by
installer/stage.py for the Chrome Stable of the build day. Using it means a new
PC needs no download before its first run — on 25 Nov a slow office PC spent
the setup's whole Chrome check downloading one — and a network that blocks
Google's download server still works.

A chromedriver only drives the Chrome of its own major version, and Chrome
updates itself, so the bundled one is used only when the PC's Chrome (read from
the registry, where Chrome records its version) has the same major version, or
when that version cannot be read. Otherwise — and always in development — the
driver comes from webdriver-manager's download, as before.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

DIR_SETTING = "SCRAPING_HUB_CHROMEDRIVER_DIR"  # overrides where the bundled driver is looked for


def bundled_dir() -> Path:
    override = os.environ.get(DIR_SETTING)
    return Path(override) if override else Path(sys.argv[0]).resolve().parent / "chromedriver"


def installed_chrome_version() -> str | None:
    """The PC's Chrome version ("157.0.8103.80"), as Chrome writes it to the registry; None off Windows or if absent."""
    try:
        import winreg
    except ImportError:
        return None
    for hive, key in (
        (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\BLBeacon"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Google\Chrome\BLBeacon"),
    ):
        try:
            with winreg.OpenKey(hive, key) as k:
                version, _ = winreg.QueryValueEx(k, "version")
                if version:
                    return str(version)
        except OSError:
            continue
    return None


def _major(version: str | None) -> str | None:
    return version.split(".", 1)[0] if version else None


def bundled_driver(chrome_version: str | None = None) -> str | None:
    """The shipped chromedriver's path if it can drive this PC's Chrome, else None."""
    folder = bundled_dir()
    exe, stamp = folder / "chromedriver.exe", folder / "version.txt"
    if not exe.is_file():
        return None
    driver_version = stamp.read_text(encoding="utf-8").strip() if stamp.is_file() else None
    chrome = chrome_version if chrome_version is not None else installed_chrome_version()
    if chrome and driver_version and _major(chrome) != _major(driver_version):
        logger.info("bundled chromedriver %s does not match Chrome %s; downloading the matching one",
                    driver_version, chrome)
        return None
    return str(exe)
