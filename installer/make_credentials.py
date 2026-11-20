"""Make the encrypted credentials file the setup wizard asks for.

    server\\.venv\\Scripts\\python.exe installer\\make_credentials.py [path\\to\\.env] [-o file.shc]

Defaults: reads server\\.env, writes installer\\output\\rizviz-credentials.shc.
Give that file to the team alongside the setup .exe; the wizard copies it to
C:\\ProgramData\\Scraping Hub\\credentials.shc. To change a password later, make
a new file and replace that one — no reinstall.

The file opens only in a build made with the same installer\\credentials.key
(created on first use, gitignored). Back that key up: lose it and every file
must be remade and every PC rebuilt/reinstalled.
"""

import argparse
import csv
import json
import secrets
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from app.core.accounts import SETTING, USERNAME, hash_password  # noqa: E402
from app.core.credentials_file import encrypt  # noqa: E402

KEY_FILE = ROOT / "installer" / "credentials.key"
ACCOUNTS_CSV = ROOT / "installer" / "accounts.csv"  # gitignored: it holds plain passwords

# Per-machine settings, not credentials: each PC gets its own from the installer.
NOT_INCLUDED = {
    "DATABASE_URL", "DOWNLOAD_DIR", "ARCHIVE_DIR", "WORK_DIR",
    "NORTHDAKOTA_PROFILE_DIR", "PUBLIC_BASE_URL",
}


def app_key() -> bytes:
    """The build's credentials key, created once."""
    if not KEY_FILE.exists():
        KEY_FILE.write_bytes(secrets.token_bytes(32))
        print(f"Created {KEY_FILE} — back it up somewhere safe.")
    key = KEY_FILE.read_bytes()
    if len(key) != 32:
        raise SystemExit(f"{KEY_FILE} is damaged (expected 32 bytes)")
    return key


def credentials_from_env(env_path: Path) -> dict[str, str]:
    """Every set key in `env_path` except the per-machine ones."""
    return {k: v for k, v in dotenv_values(env_path).items() if v and k.upper() not in NOT_INCLUDED}


def accounts_from_csv(path: Path) -> dict[str, dict[str, str]]:
    """Employee sign-ins from a CSV with columns email,name,password (or the older
    username,name,password); passwords hashed. These accounts approve sign-ups."""
    accounts = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        for line, row in enumerate(csv.DictReader(f), start=2):
            username = (row.get("email") or row.get("username") or "").strip().lower()
            name, password = (row.get("name") or "").strip(), row.get("password") or ""
            if not USERNAME.match(username):
                raise SystemExit(f"{path.name} line {line}: needs an email address (or a username of 2-32 a-z 0-9 . _ -)")
            if username in accounts:
                raise SystemExit(f"{path.name} line {line}: {username} appears twice")
            if not name or len(password) < 8:
                raise SystemExit(f"{path.name} line {line}: needs a name and a password of 8+ characters")
            accounts[username] = {"name": name, **hash_password(password)}
    return accounts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("env", nargs="?", default=ROOT / "server" / ".env", type=Path)
    parser.add_argument("-o", "--out", default=ROOT / "installer" / "output" / "rizviz-credentials.shc", type=Path)
    args = parser.parse_args()

    values = credentials_from_env(args.env)
    if not values:
        print(f"No credentials found in {args.env}")
        return 1
    panel = values.get("SCRAPING_HUB_ACCOUNTS_URL") and values.get("SCRAPING_HUB_API_KEY")
    if not ACCOUNTS_CSV.exists() and not panel:
        print(f"No {ACCOUNTS_CSV} and no account panel (SCRAPING_HUB_ACCOUNTS_URL / SCRAPING_HUB_API_KEY in "
              f"{args.env.name}) - nobody would be able to sign in.")
        return 1
    # With the account panel, accounts.csv is optional: its accounts also sign in when the panel is unreachable.
    accounts = accounts_from_csv(ACCOUNTS_CSV) if ACCOUNTS_CSV.exists() else {}
    values[SETTING] = json.dumps(accounts)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(encrypt(values, app_key()))
    print(f"Wrote {args.out} ({len(values)} settings: {', '.join(sorted(values))}; "
          f"{len(accounts)} employee sign-ins: {', '.join(sorted(accounts))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
