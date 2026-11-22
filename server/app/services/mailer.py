"""Sends the hub's emails (run results, sign-in alerts) through one SMTP server.

Gmail (or any SMTP server) when SMTP_HOST is set; otherwise AWS SES's SMTP
interface (AWS_SES_* settings), as before. Best effort: returns False and logs
instead of raising, so an email problem never breaks a run or a sign-in.
"""

import logging
import smtplib
from dataclasses import dataclass
from email.message import Message
from email.utils import parseaddr

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Server:
    name: str  # for the log: "smtp.gmail.com", "AWS SES"
    host: str
    port: int
    username: str
    password: str
    sender: str


def server() -> Server | None:
    """The configured mail server, or None when nothing usable is set."""
    if settings.smtp_host:
        username = settings.smtp_username
        password = settings.smtp_password.replace(" ", "")  # Google shows app passwords in groups of four
        sender = settings.smtp_from or username
        if not (username and password and sender):
            return None
        return Server(settings.smtp_host, settings.smtp_host, settings.smtp_port or 587, username, password, sender)
    if settings.aws_ses_from_email and settings.aws_ses_username and settings.aws_ses_password:
        host = f"email-smtp.{settings.aws_region or 'us-east-1'}.amazonaws.com"
        return Server("AWS SES", host, 587, settings.aws_ses_username, settings.aws_ses_password, settings.aws_ses_from_email)
    return None


def send(msg: Message, recipients: list[str], what: str) -> bool:
    """Send `msg` (From is filled in here) to `recipients`. `what` names the email in the log."""
    srv = server()
    if srv is None:
        logger.warning("%s not sent: no email server set up (SMTP_* or AWS_SES_* settings)", what)
        return False
    if "From" in msg:
        del msg["From"]
    msg["From"] = srv.sender
    envelope = parseaddr(srv.sender)[1] or srv.sender  # "Scraping Hub <a@b.c>" -> a@b.c
    try:
        with smtplib.SMTP(srv.host, srv.port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(srv.username, srv.password)
            smtp.sendmail(envelope, recipients, msg.as_bytes())
        logger.info("%s sent via %s to %s", what, srv.name, recipients)
        return True
    except Exception as exc:  # noqa: BLE001 — email is best effort
        logger.error("%s failed via %s: %s", what, srv.name, exc)
        return False
