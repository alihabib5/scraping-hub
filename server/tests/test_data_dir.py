"""Where the server writes, with and without SCRAPING_HUB_DATA_DIR.

The installed Windows app lives in C:\\Program Files, which is read-only, so it
sets SCRAPING_HUB_DATA_DIR (C:\\ProgramData\\Scraping Hub) and everything the
server writes must land there. Unset — development — nothing may move.

The paths are fixed at import time, so each case runs in a fresh interpreter.

    server/.venv/bin/python -m pytest server/tests/test_data_dir.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent

PROBE = """
import json, os
from app import config
from app.scrapers.bidnet import filters
from app.scrapers.sam.engine import sam_scraper
s = config.settings
print(json.dumps({
    "env_file": str(config.ENV_FILE),
    "bidnet_cache": str(filters.OPTIONS_CACHE),
    "sam_temp_docs": str(sam_scraper._TEMP_DOCS_ROOT),
    "sam_log": os.path.abspath(sam_scraper._log_file),
    "archive_root": str(s.archive_root),
    "documents_root": str(s.documents_root),
    "work_root": str(s.work_root),
    "nd_profile": str(s.northdakota_profile_path),
}))
"""


def _probe(tmp_path, env_extra):
    env = {k: v for k, v in os.environ.items()
           if k not in ("SCRAPING_HUB_DATA_DIR", "ARCHIVE_DIR", "DOWNLOAD_DIR", "WORK_DIR", "NORTHDAKOTA_PROFILE_DIR")}
    env.update(env_extra)
    env["PYTHONPATH"] = str(SERVER)
    out = subprocess.run([sys.executable, "-c", PROBE], cwd=tmp_path, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    return {k: Path(v) for k, v in json.loads(out.stdout.strip().splitlines()[-1]).items()}


def test_unset_nothing_moves(tmp_path):
    p = _probe(tmp_path, {})
    assert p["env_file"] == SERVER / ".env"
    assert p["bidnet_cache"] == SERVER / "data" / "bidnet_filter_options.json"
    assert p["sam_temp_docs"] == SERVER / "app" / "scrapers" / "sam" / "engine" / "temp_docs"
    assert p["archive_root"] == (SERVER / ".." / "data" / "archives").resolve()


def test_set_everything_written_lands_in_the_data_dir(tmp_path):
    data = tmp_path / "ProgramData" / "Scraping Hub"
    p = _probe(tmp_path, {
        "SCRAPING_HUB_DATA_DIR": str(data),
        # What the installed app sets for the paths that are already settings.
        "ARCHIVE_DIR": str(data / "archives"),
        "DOWNLOAD_DIR": str(data / "documents"),
        "WORK_DIR": str(data / "work"),
        "NORTHDAKOTA_PROFILE_DIR": str(data / "chrome_profiles" / "northdakota"),
    })
    for name, path in p.items():
        assert data in path.parents or path == data, f"{name} escaped the data dir: {path}"
    assert p["env_file"] == data / ".env"
    assert p["sam_log"] == data / "logs" / "sam_scraper.log"
