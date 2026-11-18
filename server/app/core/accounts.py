"""Employee sign-in for the installed Windows app.

The accounts travel inside the encrypted credentials file as one setting,
SCRAPING_HUB_ACCOUNTS: JSON {username: {"name", "salt", "hash"}} holding
PBKDF2-SHA256 hashes, never passwords (installer/make_credentials.py writes
it). The desktop app asks /auth/login, then sends the signed-in username as
X-Hub-User on every request, so runs record who started them. Development
has no accounts and sends no header: nothing changes there.

Limit: the engine only listens on 127.0.0.1 and trusts that header, so this
keeps other people at the PC out of the app, not someone scripting the API.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from contextvars import ContextVar

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

SETTING = "SCRAPING_HUB_ACCOUNTS"
USERNAME = re.compile(r"^[a-z0-9._-]{2,32}$")
ROUNDS = 200_000

# Who is signed in for the request being handled; set by main.py's middleware.
current_user: ContextVar[str | None] = ContextVar("current_user", default=None)


def hash_password(password: str, salt: str | None = None) -> dict[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), ROUNDS)
    return {"salt": salt, "hash": digest.hex()}


def accounts() -> dict[str, dict[str, str]]:
    try:
        return json.loads(os.environ.get(SETTING) or "{}")
    except ValueError:
        return {}


def verify(username: str, password: str) -> str | None:
    """The employee's full name if the password is right, else None."""
    account = accounts().get(username.strip().lower())
    if not account:
        return None
    attempt = hash_password(password, account["salt"])["hash"]
    return account["name"] if hmac.compare_digest(attempt, account["hash"]) else None


router = APIRouter(prefix="/auth", tags=["auth"])


class SignIn(BaseModel):
    username: str
    password: str


@router.get("/status")
def status() -> dict:
    return {"accounts": len(accounts())}


@router.post("/login")
def login(body: SignIn) -> dict:
    name = verify(body.username, body.password)
    if name is None:
        raise HTTPException(status_code=401, detail="Wrong username or password")
    return {"username": body.username.strip().lower(), "name": name}
