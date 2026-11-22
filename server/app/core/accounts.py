"""Employee sign-in for the installed Windows app.

Accounts live online: an admin panel on Vercel (admin/ in this repo) keeps them
in Supabase, takes sign-up requests from the app, and lets an administrator
approve them. This module is the PC's side of that:

* **Sign up** forwards the request to the panel's API; the account cannot sign
  in until an administrator approves it there.
* **Sign in** asks the panel. Each successful sign-in is remembered on this PC
  as a PBKDF2-SHA256 hash (accounts_cache.json in the data folder, never the
  password), so a short internet outage does not lock anyone out. When the panel
  says an account is unknown — removed by an administrator — it is forgotten
  here too, so removal takes effect the next time this PC is online.
* **Issued** accounts in the encrypted credentials file (SCRAPING_HUB_ACCOUNTS:
  JSON {email: {"name", "salt", "hash"}}, from installer/make_credentials.py)
  still sign in without the panel, as before.

The panel is configured by SCRAPING_HUB_ACCOUNTS_URL and SCRAPING_HUB_API_KEY,
which travel in the credentials file with the portal logins.

The desktop app sends the signed-in email as X-Hub-User on every request, so
runs record who started them. Development has no accounts and sends no header:
nothing changes there.

**Sessions.** A sign-in through the panel opens a session there (its IP and start
time show on the admin dashboard). This engine keeps its id; the desktop app
checks in through /auth/ping every few minutes and ends it through /auth/logout
on sign-out and when the app closes. Both are best effort: a panel that cannot be
reached never blocks signing out or closing.

Limit: the engine only listens on 127.0.0.1 and trusts that header, so this
keeps other people at the PC out of the app, not someone scripting the API.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import DATA_DIR, SERVER_ROOT

logger = logging.getLogger(__name__)

SETTING = "SCRAPING_HUB_ACCOUNTS"
URL_SETTING, KEY_SETTING = "SCRAPING_HUB_ACCOUNTS_URL", "SCRAPING_HUB_API_KEY"
# What a sign-in key may be: an email, or a pre-email username (a-z 0-9 . _ -).
USERNAME = re.compile(r"^(?:[a-z0-9._-]{2,32}|[a-z0-9._%+-]{1,64}@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,})$")
ROUNDS = 200_000
TIMEOUT = 10  # seconds; past this the panel counts as unreachable and the cache answers
CACHE_FILE = (Path(DATA_DIR) if DATA_DIR else SERVER_ROOT / "data") / "accounts_cache.json"

# Who is signed in for the request being handled; set by main.py's middleware.
current_user: ContextVar[str | None] = ContextVar("current_user", default=None)
_lock = threading.Lock()
# The panel session of whoever is signed in on this PC (one person at a time), or None.
_session: str | None = None


class Unreachable(Exception):
    """The panel did not answer (no internet, Vercel down)."""


def hash_password(password: str, salt: str | None = None) -> dict[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), ROUNDS)
    return {"salt": salt, "hash": digest.hex()}


def _password_ok(account: dict[str, str], password: str) -> bool:
    return hmac.compare_digest(hash_password(password, account["salt"])["hash"], account["hash"])


def _key(email: str) -> str:
    return (email or "").strip().lower()


def accounts() -> dict[str, dict[str, str]]:
    """The issued accounts, from the credentials file."""
    try:
        return json.loads(os.environ.get(SETTING) or "{}")
    except ValueError:
        return {}


# -- the PC's memory of who signed in -------------------------------------------


def cached() -> dict[str, dict[str, str]]:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_cache(data: dict[str, dict[str, str]]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(CACHE_FILE)  # never a half-written file


def _remember(email: str, name: str, password: str) -> None:
    with _lock:
        data = cached()
        data[email] = {"name": name, **hash_password(password), "cached_at": datetime.now().isoformat(timespec="seconds")}
        _write_cache(data)


def _forget(email: str) -> None:
    with _lock:
        data = cached()
        if data.pop(email, None) is not None:
            _write_cache(data)


# -- the panel --------------------------------------------------------------


def panel_configured() -> bool:
    return bool(os.environ.get(URL_SETTING) and os.environ.get(KEY_SETTING))


def _panel(path: str, body: dict) -> requests.Response:
    url = os.environ[URL_SETTING].rstrip("/") + path
    try:
        response = requests.post(url, json=body, timeout=TIMEOUT, headers={"X-Hub-Key": os.environ[KEY_SETTING]})
    except requests.RequestException as exc:
        raise Unreachable(str(exc)) from exc
    if response.status_code >= 500:
        raise Unreachable(f"{url} answered {response.status_code}")
    return response


def _detail(response: requests.Response) -> str:
    try:
        return str(response.json().get("detail") or "")
    except ValueError:
        return ""


def verify(username: str, password: str) -> str | None:
    """The name of an issued account if the password is right, else None (no panel involved)."""
    account = accounts().get(_key(username))
    return account["name"] if account and _password_ok(account, password) else None


router = APIRouter(prefix="/auth", tags=["auth"])


class SignIn(BaseModel):
    username: str
    password: str


class SignUp(BaseModel):
    name: str
    email: str
    password: str


@router.get("/status")
def status() -> dict:
    """Whether anyone can sign in on this PC: issued or remembered accounts, or the panel."""
    return {"accounts": len(accounts()) + len(cached()), "panel": panel_configured()}


def _alert(email: str, name: str, how: str, public_ip: str | None = None) -> None:
    """Email the administrators about this sign-in (background, best effort)."""
    try:
        from app.services import signin_alert

        signin_alert.notify(email, name, how, public_ip)
    except Exception as exc:  # noqa: BLE001 — an alert must never block a sign-in
        logger.error("sign-in alert could not be started: %s", exc)


@router.post("/login")
def login(body: SignIn) -> dict:
    global _session
    email = _key(body.username)
    name = verify(email, body.password)
    if name is not None:
        _alert(email, name, "issued")
        return {"username": email, "name": name}
    if not panel_configured():
        raise HTTPException(status_code=401, detail="Wrong email or password")
    try:
        response = _panel("/api/login", {"email": email, "password": body.password})
    except Unreachable as exc:
        logger.warning("account panel unreachable (%s); checking this PC's remembered accounts", exc)
        account = cached().get(email)
        if account and _password_ok(account, body.password):
            _alert(email, account["name"], "cached")
            return {"username": email, "name": account["name"]}
        raise HTTPException(status_code=503, detail="Can't reach the account server, and this account hasn't signed in "
                                                    "on this PC before. Check the internet connection.") from exc
    if response.status_code == 200:
        reply = response.json()
        name = reply["name"]
        _remember(email, name, body.password)
        _end_session()  # a previous sign-in on this PC that never signed out
        _session = reply.get("session_id")
        _alert(email, name, "panel", reply.get("ip"))
        return {"username": email, "name": name}
    if response.status_code == 409:  # right password, not approved yet
        raise HTTPException(status_code=403, detail=_detail(response) or "This account is waiting for approval.")
    if response.status_code == 401:
        _forget(email)  # removed by an administrator, or the password changed: this PC no longer vouches for it
    else:
        logger.error("account panel refused sign-in with %s: %s", response.status_code, _detail(response))
    raise HTTPException(status_code=401, detail="Wrong email or password")


@router.post("/signup", status_code=201)
def signup(body: SignUp) -> dict:
    if not panel_configured():
        raise HTTPException(status_code=503, detail="Creating accounts isn't set up on this PC. Ask an administrator.")
    try:
        response = _panel("/api/signup", body.model_dump())
    except Unreachable as exc:
        raise HTTPException(status_code=503, detail="Can't reach the account server. Check the internet connection "
                                                    "and try again.") from exc
    if response.status_code == 201:
        return response.json()
    if response.status_code in (409, 422):
        raise HTTPException(status_code=response.status_code, detail=_detail(response))
    logger.error("account panel refused sign-up with %s: %s", response.status_code, _detail(response))
    raise HTTPException(status_code=502, detail="The account server refused the request. Ask an administrator.")


def _touch(session: str, action: str) -> None:
    try:
        _panel("/api/session", {"session_id": session, "action": action})
    except Unreachable as exc:
        logger.info("account panel unreachable, session %s not sent (%s)", action, exc)


def _end_session() -> None:
    global _session
    session, _session = _session, None
    if session and panel_configured():
        _touch(session, "end")


@router.post("/ping")
def ping() -> dict:
    """The desktop app checking in, so the dashboard knows the session is still open."""
    if _session and panel_configured():
        _touch(_session, "ping")
    return {"session": bool(_session)}


@router.post("/logout")
def logout() -> dict:
    """Sign-out or app close: ends the panel session, if there is one."""
    _end_session()
    return {"ok": True}
