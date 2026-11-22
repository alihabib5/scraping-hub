"""Email the administrators every time someone signs in to the Windows app.

Who (name, email), when (this PC's local time and UTC), from where (public IP
as the account server saw it, this PC's name, Windows user and local IP) and
how the sign-in was checked (account server, this PC's remembered accounts
while offline, or an issued account).

Sent through the same mail server as the run notifications (Gmail via SMTP_*,
else AWS SES; services/mailer.py), to SIGNIN_ALERT_EMAILS (comma-separated). Blank = off.
Best effort and in the background: a slow or failed email never delays or
blocks a sign-in. An offline sign-in can't send either; it is logged.
"""

import getpass
import html
import logging
import os
import platform
import socket
import threading
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings
from app.services import mailer

logger = logging.getLogger(__name__)

HOW = {
    "panel": "Account server (online)",
    "cached": "Remembered on this PC (account server unreachable)",
    "issued": "Issued account from the credentials file",
}


def recipients() -> list[str]:
    return [e.strip() for e in (settings.signin_alert_emails or "").split(",") if e.strip()]


def _local_ip() -> str:
    """The address this PC uses on its network. UDP 'connect' sends nothing; it only picks the route."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "unknown"


def details(email: str, name: str, how: str, public_ip: str | None, now: datetime | None = None) -> list[tuple[str, str]]:
    """The facts the email lists, in order. `now` is for tests."""
    local = (now or datetime.now().astimezone()).astimezone()
    try:
        windows_user = getpass.getuser()
    except Exception:  # noqa: BLE001 — no user name is not a reason to skip the alert
        windows_user = "unknown"
    return [
        ("Name", name or "—"),
        ("Email", email),
        ("Time (this PC)", local.strftime("%A %d %B %Y, %I:%M:%S %p %Z (UTC%z)")),
        ("Time (UTC)", local.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")),
        ("Public IP", public_ip or "not known (signed in without the account server)"),
        ("Local IP", _local_ip()),
        ("Computer name", socket.gethostname() or "unknown"),
        ("Windows user", windows_user),
        ("Windows", f"{platform.system()} {platform.release()} ({platform.version()})"),
        ("App version", os.environ.get("SCRAPING_HUB_VERSION", "unknown")),
        ("Signed in via", HOW.get(how, how)),
    ]


def _message(email: str, name: str, rows: list[tuple[str, str]]) -> tuple[str, str, str]:
    """(subject, plain text, html)."""
    who = f"{name} <{email}>" if name else email
    host = dict(rows).get("Computer name", "")
    subject = f"Scraping Hub sign-in: {who} on {host}"
    text = "Someone signed in to Scraping Hub.\n\n" + "\n".join(f"{k}: {v}" for k, v in rows)
    text += "\n\nIf this was not expected, remove the account in the account panel."
    cells = "".join(
        f'<tr><td style="padding:6px 14px 6px 0;color:#5b6475;white-space:nowrap;vertical-align:top">{html.escape(k)}</td>'
        f'<td style="padding:6px 0;color:#1c2333">{html.escape(v)}</td></tr>'
        for k, v in rows
    )
    body = (
        '<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1c2333">'
        f'<p style="margin:0 0 12px"><strong>{html.escape(who)}</strong> signed in to Scraping Hub.</p>'
        f'<table style="border-collapse:collapse">{cells}</table>'
        '<p style="margin:16px 0 0;color:#5b6475;font-size:12px">If this was not expected, remove the account '
        "in the account panel. &copy; Rizviz International Impex.</p></div>"
    )
    return subject, text, body


def _send(to: list[str], subject: str, text: str, body: str) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["To"] = subject, ", ".join(to)
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(body, "html", "utf-8"))
    return mailer.send(msg, to, "sign-in alert")


def notify(email: str, name: str, how: str, public_ip: str | None = None) -> threading.Thread | None:
    """Send the alert in the background. Returns the thread (tests join it), or None when alerts are off."""
    to = recipients()
    if not to:
        return None
    rows = details(email, name, how, public_ip)
    logger.info("sign-in by %s via %s from %s", email, how, public_ip or "unknown IP")
    t = threading.Thread(target=_send, args=(to, *_message(email, name, rows)), name="signin-alert", daemon=True)
    t.start()
    return t
