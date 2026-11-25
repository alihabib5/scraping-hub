r"""Gather everything the setup wizard installs into installer\build\stage.

    server\.venv\Scripts\python.exe installer\stage.py

Run after build_server.py (compiled server), the console's static export
(client: SCRAPING_HUB_DESKTOP=1 npm run build) and the desktop package
(desktop: npm run package). The stage mirrors C:\Program Files\Scraping Hub:

    Scraping Hub.exe + Electron files   the window
    server\      compiled API            console\   static console
    server\chromedriver\   chromedriver.exe + version.txt for today's Chrome Stable
    pgsql\       PostgreSQL (bin, lib, share only)
    tools\       setup-database.ps1, remove-database.ps1, vcredist_x64.exe

Refuses to stage anything that is source code or a credential.
"""

import io
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "installer" / "build"
STAGE = BUILD / "stage"
PG = Path(r"C:\Program Files\PostgreSQL\18")

PARTS = {
    # stage path: source
    ".": BUILD / "desktop" / "Scraping Hub-win32-x64",
    "server": BUILD / "hub_server.dist",
    "console": ROOT / "client" / "out-desktop",
    "pgsql/bin": PG / "bin",
    "pgsql/lib": PG / "lib",
    "pgsql/share": PG / "share",
}
FILES = {
    "pgsql/server_license.txt": PG / "server_license.txt",
    "tools/vcredist_x64.exe": PG / "installer" / "vcredist_x64.exe",
    "tools/setup-database.ps1": ROOT / "installer" / "setup-database.ps1",
    "tools/remove-database.ps1": ROOT / "installer" / "remove-database.ps1",
}
# Never shipped: source, settings with secrets, the build key, Next's build cache.
FORBIDDEN_SUFFIXES = {".py", ".pyc", ".env", ".key", ".shc", ".ts", ".tsx", ".map"}
CONSOLE_SKIP = {"cache", "server", "types", "diagnostics", "trace", "build"}
# Not shipped, to cut install time (every file costs a write and an antivirus scan):
# PostgreSQL's translated messages (632 files) and Electron's non-English UI text.
SKIP_DIRS = {"pgsql/share": {"locale"}}
KEEP_LOCALES = {"en-US.pak", "en-GB.pak"}


# Google's official list of current Chrome versions with their chromedriver downloads.
CHROME_FOR_TESTING = "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"


def fetch_chromedriver(dest: Path) -> str:
    """Put the chromedriver for today's Chrome Stable in `dest` (chromedriver.exe +
    version.txt), so a new PC never downloads one before its first run; the
    engine uses it while the PC's Chrome has the same major version
    (server/app/core/chromedriver.py). Returns the version."""
    with urllib.request.urlopen(CHROME_FOR_TESTING, timeout=60) as r:
        stable = json.load(r)["channels"]["Stable"]
    url = next(d["url"] for d in stable["downloads"]["chromedriver"] if d["platform"] == "win64")
    with urllib.request.urlopen(url, timeout=300) as r:
        archive = zipfile.ZipFile(io.BytesIO(r.read()))
    member = next(n for n in archive.namelist() if n.endswith("/chromedriver.exe"))
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "chromedriver.exe").write_bytes(archive.read(member))
    (dest / "version.txt").write_text(stable["version"], encoding="utf-8")
    return stable["version"]


def main() -> int:
    missing = [str(p) for p in [*PARTS.values(), *FILES.values()] if not p.exists()]
    if missing:
        print("Missing (build it first):\n  " + "\n  ".join(missing))
        return 1

    if STAGE.exists():
        shutil.rmtree(STAGE)
    for dest, src in PARTS.items():
        ignore = None
        if dest == "console":
            # The export folder also holds Next's build internals; only the site ships.
            ignore = lambda d, names: [n for n in names if Path(d) == src and n in CONSOLE_SKIP]  # noqa: E731
        elif dest in SKIP_DIRS:
            skip = SKIP_DIRS[dest]
            ignore = lambda d, names, src=src, skip=skip: [n for n in names if Path(d) == src and n in skip]  # noqa: E731
        elif dest == ".":
            ignore = lambda d, names: [n for n in names if Path(d).name == "locales" and n.endswith(".pak") and n not in KEEP_LOCALES]  # noqa: E731
        shutil.copytree(src, STAGE / dest, ignore=ignore, dirs_exist_ok=True)
    for dest, src in FILES.items():
        (STAGE / dest).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, STAGE / dest)
    try:
        print(f"chromedriver {fetch_chromedriver(STAGE / 'server' / 'chromedriver')} bundled")
    except Exception as exc:  # noqa: BLE001 — a setup without it would download on every new PC again
        print(f"FAIL: could not fetch chromedriver from Chrome for Testing ({exc}); check the internet connection")
        return 1

    files = [p for p in STAGE.rglob("*") if p.is_file()]
    bad = [p for p in files if p.suffix.lower() in FORBIDDEN_SUFFIXES or p.name.startswith(".env")]
    if bad:
        print(f"FAIL: {len(bad)} files that must not ship, e.g. {bad[0].relative_to(STAGE)}")
        return 1
    size = sum(p.stat().st_size for p in files) / 1e6
    print(f"OK: staged {len(files)} files, {size:.0f} MB, in {STAGE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
