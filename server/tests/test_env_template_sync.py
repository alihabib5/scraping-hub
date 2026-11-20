"""The account panel's Encryptor builds its Scraping Hub form from a copy of
server/.env.example (admin/src/lib/env-template.ts). This fails if the copy is
stale, so a setting added here is never missing from the credentials the panel
makes. Fix: `node admin/scripts/sync-env-template.mjs` (it also runs before every
panel build).

    server/.venv/Scripts/python -m pytest server/tests/test_env_template_sync.py
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_panels_env_template_matches_env_example():
    copy = (ROOT / "admin" / "src" / "lib" / "env-template.ts").read_text(encoding="utf-8")
    match = re.search(r"export const ENV_EXAMPLE = (\".*\");", copy, re.S)
    assert match, "env-template.ts is not in the generated shape"
    source = (ROOT / "server" / ".env.example").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert json.loads(match.group(1)) == source, (
        "admin/src/lib/env-template.ts is out of date: run node admin/scripts/sync-env-template.mjs"
    )
