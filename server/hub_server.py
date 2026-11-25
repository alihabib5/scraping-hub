"""Entry point of the installed Windows app's server — the file Nuitka compiles.

Development keeps using `uvicorn main:app --port 9001 --reload` from server/.
This imports the app object directly (not "main:app" as a string) so the
compiler sees every module, and binds to 127.0.0.1 only: each PC talks to its
own server, and nothing else on the office network can reach it.

    scraping-hub-server.exe                start the server (the desktop app does this)
    scraping-hub-server.exe --self-check   can this build do everything a run needs?
    scraping-hub-server.exe --check-credentials FILE   does FILE open with this build's key?
"""

import logging
import multiprocessing
import os
import sys
from pathlib import Path

logger = logging.getLogger("hub_server")


def _apply_installed_layout() -> None:
    """The installed app's data folders, unless whoever started it set them.

    Program Files is read-only, so everything goes under ProgramData. The
    desktop app passes these explicitly; this makes the exe correct on its own
    too (e.g. IT running --self-check from a command prompt).
    """
    data = os.environ.setdefault(
        "SCRAPING_HUB_DATA_DIR",
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "Scraping Hub"),
    )
    for name, sub in (
        ("ARCHIVE_DIR", "archives"),
        ("DOWNLOAD_DIR", "documents"),
        ("WORK_DIR", "work"),
        ("NORTHDAKOTA_PROFILE_DIR", os.path.join("chrome_profiles", "northdakota")),
    ):
        os.environ.setdefault(name, os.path.join(data, sub))


def _load_credentials_file() -> str:
    """Put the portal logins from the encrypted credentials file into the environment.

    The file (made by installer/make_credentials.py, placed by the setup wizard)
    sits in the data dir; `_app_key` holds the key that opens it and exists only
    inside the compiled build. In development neither is there and nothing
    changes. Must run before the app is imported: settings are read at import
    time. A variable already set in the environment is left alone.

    Returns what happened, for the log and --self-check ("" in development).
    """
    data_dir = os.environ.get("SCRAPING_HUB_DATA_DIR", "")
    try:
        import _app_key
    except ImportError:
        return ""
    from app.core.credentials_file import FILE_NAME, load_and_lock, lock_leftovers

    path = Path(data_dir) / FILE_NAME
    if not data_dir or not path.is_file():
        status = f"No credentials file at {path} — portal logins will be empty"
        logger.warning(status)
        return status
    try:
        values, locked_now = load_and_lock(path, _app_key.KEY)
    except (OSError, ValueError) as exc:
        status = f"Could not open {path}: {exc}"
        logger.error(status)
        return status
    if locked_now:
        logger.info("credentials file locked to this PC")
    for note in lock_leftovers(path, _app_key.KEY):
        logger.info("credentials backup: %s", note)
    for name, value in values.items():
        os.environ.setdefault(name, value)
    status = f"Loaded {len(values)} settings from {path}"
    logger.info(status)
    return status


def _check_credentials(path: str) -> int:
    """Does the file at `path` open with this build's key? Changes nothing.

    The desktop app's "Update credentials" asks this before it replaces the
    installed file, so a wrong or damaged file is refused instead of leaving
    every portal without a login. Prints "OK - N settings" or "FAIL - why".
    """
    try:
        import _app_key
    except ImportError:
        print("FAIL - not a compiled build (no key)")
        return 1
    from app.core.credentials_file import open_bytes

    try:
        values = open_bytes(Path(path).read_bytes(), _app_key.KEY)
    except (OSError, ValueError) as exc:
        print(f"FAIL - {exc}")
        return 1
    print(f"OK - {len(values)} settings")
    return 0


# A 2012-era PC took longer than 90 s for its first headless Chrome (25 Nov). The driver now
# ships with the app, so this covers Chrome's own first start only.
BROWSER_CHECK_S = 180


def _within(seconds: float, fn):
    """fn()'s result, or TimeoutError after `seconds`. The worker is a daemon thread, so a hung one can't keep the process alive."""
    import threading

    box: dict = {}

    def work() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 — handed back to the caller
            box["error"] = exc

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise TimeoutError(f"did not finish within {seconds:.0f} s")
    if "error" in box:
        raise box["error"]
    return box["value"]


def _self_check(credentials_status: str) -> int:
    """Import what the scrapers only load mid-run, so a gap shows here, not as a failed scrape.

    One line per check; exit code 0 means everything passed.
    """
    import io

    def pdf() -> str:
        import fitz

        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "self-check")
        assert "self-check" in fitz.open("pdf", doc.tobytes())[0].get_text()
        return f"PyMuPDF {fitz.VersionBind}"

    def word() -> str:
        from docx import Document

        buf = io.BytesIO()
        Document().save(buf)
        Document(io.BytesIO(buf.getvalue()))
        return ""

    def every_module() -> str:
        # Each scraper's engine is imported only when a run starts; load them all
        # now so a module missing from the build shows here, not mid-run.
        import importlib
        import pkgutil

        import app

        names = [m.name for m in pkgutil.walk_packages(app.__path__, "app.")]
        if not names:
            raise RuntimeError("could not list the app's modules")
        for name in names:
            importlib.import_module(name)
        return f"{len(names)} modules"

    def browser() -> str:
        # The scrapers' own driver resolution, then a real headless Chrome: proves
        # the selenium modules, chromedriver download and Chrome itself.
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service

        from app.core.base_scraper import _resolve_chromedriver

        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        driver = webdriver.Chrome(service=Service(_resolve_chromedriver()), options=options)
        try:
            driver.get("about:blank")
            return f"Chrome {driver.capabilities.get('browserVersion', '?')}"
        finally:
            driver.quit()

    def credentials() -> str:
        if not credentials_status.startswith("Loaded"):
            raise RuntimeError(credentials_status or "not a compiled build (no key)")
        return credentials_status

    import platform

    # Under Windows-on-ARM's x64 emulation, machine() still says AMD64; the
    # real chip shows in PROCESSOR_ARCHITEW6432.
    real_cpu = os.environ.get("PROCESSOR_ARCHITEW6432") or platform.machine()
    print(f"Scraping Hub engine self-check: {real_cpu} CPU, Windows {platform.version()}, "
          f"{platform.processor() or 'unknown processor'}", flush=True)
    checks = [
        ("server app", lambda: __import__("main") and ""),
        ("every scraper module", every_module),
        ("PDF reading", pdf),
        ("Word reading", word),
        ("Excel .xlsx", lambda: __import__("openpyxl") and ""),
        ("Excel .xls", lambda: __import__("xlrd") and ""),
        ("date parsing", lambda: __import__("dateutil.parser") and ""),
        ("email upload (boto3)", lambda: __import__("boto3") and ""),
        ("credentials file", credentials),
        # Last, and time-limited: a Chrome that never answers (first-run prompt,
        # blocked chromedriver download) must not leave the setup wizard waiting forever.
        ("Chrome (headless)", lambda: _within(BROWSER_CHECK_S, browser)),
    ]
    failed = 0
    for name, fn in checks:
        try:
            detail = fn()
            print(f"OK    {name}{f' - {detail}' if detail else ''}", flush=True)
        except TimeoutError as exc:
            # Slow, not broken: the check never failed, it ran out of time. The app checks Chrome
            # again at start-up, so a slow first start must not tell the person the install failed.
            print(f"WARN  {name} - {exc}; a slow first start, so the first run may take longer", flush=True)
        except Exception as exc:  # noqa: BLE001 — report every gap, not just the first
            failed += 1
            print(f"FAIL  {name} - {type(exc).__name__}: {exc}", flush=True)
    print("Self-check passed" if not failed else f"Self-check FAILED: {failed} problem(s)", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if "--check-credentials" in sys.argv:
        at = sys.argv.index("--check-credentials") + 1
        sys.exit(_check_credentials(sys.argv[at] if at < len(sys.argv) else ""))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if "__compiled__" in globals():  # set by Nuitka: this is the installed exe
        _apply_installed_layout()
    status = _load_credentials_file()
    if "--self-check" in sys.argv:
        sys.exit(_self_check(status))

    import uvicorn

    from main import app

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("SCRAPING_HUB_PORT", "9001")))
