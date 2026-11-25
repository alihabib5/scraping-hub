r"""Compile the server into a standalone Windows program — no Python, no .py files.

    server\.venv\Scripts\python.exe installer\build_server.py

Output: installer\build\hub_server.dist\scraping-hub-server.exe plus its DLLs.
That folder is what the installer copies to C:\Program Files\Scraping Hub\server.
Uses Nuitka with the zig C compiler (pip-installed; no Visual Studio needed).

No credential goes into the build: only the key that opens the separate
credentials file (installer\make_credentials.py). As a safety net the build
fails if any login from server\.env can be found in the output.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from make_credentials import app_key, credentials_from_env

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "server"
OUT = ROOT / "installer" / "build"
GEN = OUT / "gen"
DIST = OUT / "hub_server.dist"

# Read-only files the code opens next to its own modules (Path(__file__)...).
DATA_FILES = [
    "app/scrapers/sam/engine/config.yml",
    "app/scrapers/myflorida/sweep/mfmp_niches.yaml",
    "app/scrapers/txsmartbuy/agencies.json",
]


def main() -> int:
    # Fresh every time: a build that was killed never ran its cleanup.
    shutil.rmtree(GEN, ignore_errors=True)
    GEN.mkdir(parents=True)
    key_module = GEN / "_app_key.py"
    key_module.write_text(f"KEY = {app_key()!r}\n", encoding="utf-8")

    cmd = [
        sys.executable, "-m", "nuitka",
        "--mode=standalone",
        "--zig",
        "--assume-yes-for-downloads",
        f"--output-dir={OUT}",
        "--output-filename=scraping-hub-server.exe",
        # Every scraper, including the export modules exports.py imports by name.
        "--include-package=app",
        # uvicorn picks its event loop / protocol implementations by string.
        "--include-package=uvicorn",
        # These load their own parts by name at run time (module __getattr__ +
        # importlib), which the compiler cannot see. Without selenium in full a
        # run fails: "No module named 'selenium.webdriver.chrome.webdriver'".
        "--include-package=selenium",
        "--include-package=webdriver_manager",
        "--include-package=pydantic",
        "--include-package=dateutil",
        "--include-module=_app_key",
        # Blanks Rizviz's docstrings (not the libraries'); embeds PyMuPDF as
        # bytecode, as its 185 MB of generated C would take hours.
        f"--user-plugin={ROOT / 'installer' / 'nuitka_plugin.py'}",
        "--nofollow-import-to=tests",
        "--nofollow-import-to=pytest",
        *[f"--include-data-files={SERVER / f}={f}" for f in DATA_FILES],
        "--company-name=Rizviz International Impex",
        "--copyright=Copyright (C) Rizviz International Impex. All rights reserved.",
        "--product-name=Scraping Hub",
        "--file-version=1.0.4.0",
        "--product-version=1.0.4.0",
        str(SERVER / "hub_server.py"),
    ]
    # zig builds its own C runtime at link time for the build PC's CPU (AVX2, LZCNT...)
    # unless told otherwise; Nuitka passes -march only to the compile step. Without
    # this the engine dies with "illegal instruction" on older CPUs before any output.
    env = {**os.environ, "PYTHONPATH": str(GEN), "LDFLAGS": "-march=x86_64"}
    try:
        result = subprocess.run(cmd, cwd=SERVER, env=env)
    finally:
        key_module.unlink(missing_ok=True)  # the key's source never outlives the build
    if result.returncode:
        return result.returncode
    return check(credentials_from_env(SERVER / ".env"))


def check(credentials: dict[str, str]) -> int:
    """No source code and no readable credential anywhere in the build."""
    files = [p for p in DIST.rglob("*") if p.is_file()]
    leaked = [p for p in files if p.suffix in (".py", ".pyc", ".env")]
    if leaked:
        print(f"FAIL: {len(leaked)} source/.env files in the build, e.g. {leaked[0]}")
        return 1
    # Logins and keys, not settings like EMMA_LINK whose public URL is a code default anyway.
    secret = [v for k, v in credentials.items() if len(v) >= 6 and any(
        s in k.upper() for s in ("PASSWORD", "SECRET", "KEY_ID", "USERNAME", "EMAIL"))]
    needles = [v.encode(enc) for v in secret for enc in ("utf-8", "utf-16-le")]
    for p in files:
        data = p.read_bytes()
        if any(n in data for n in needles):
            print(f"FAIL: a credential is readable in {p.relative_to(DIST)}")  # which one is not printed
            return 1
    size = sum(p.stat().st_size for p in files) / 1e6
    print(f"OK: {DIST / 'scraping-hub-server.exe'} ({size:.0f} MB, {len(files)} files, "
          f"no source, no readable credential)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
