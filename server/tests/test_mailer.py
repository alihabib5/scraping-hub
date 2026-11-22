"""Which mail server the hub's emails go through: Gmail (any SMTP) first, AWS SES as the fallback.

    server/.venv/bin/python -m pytest server/tests/test_mailer.py
"""

from email.mime.text import MIMEText

import pytest

from app.config import settings
from app.services import mailer


@pytest.fixture
def nothing_set(monkeypatch):
    for name in ("smtp_host", "smtp_username", "smtp_password", "smtp_from",
                 "aws_ses_from_email", "aws_ses_username", "aws_ses_password"):
        monkeypatch.setattr(settings, name, "")
    monkeypatch.setattr(settings, "smtp_port", 587)


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def starttls(self):
        pass

    def login(self, user, password):
        self.user, self.password = user, password

    def sendmail(self, sender, to, data):
        FakeSMTP.sent.append((self.host, self.port, self.user, self.password, sender, to, data))


def test_gmail_is_used_when_set_and_app_password_spaces_are_dropped(nothing_set, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_username", "alerts@gmail.com")
    monkeypatch.setattr(settings, "smtp_password", "abcd efgh ijkl mnop")
    monkeypatch.setattr(settings, "aws_ses_from_email", "no-reply@x.com")  # SES also set: Gmail still wins
    monkeypatch.setattr(settings, "aws_ses_username", "u")
    monkeypatch.setattr(settings, "aws_ses_password", "p")
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent.clear()
    msg = MIMEText("hi")
    msg["Subject"] = "t"
    assert mailer.send(msg, ["boss@x.com"], "test")
    host, port, user, password, sender, to, data = FakeSMTP.sent[0]
    assert (host, port, user, password, sender, to) == (
        "smtp.gmail.com", 587, "alerts@gmail.com", "abcdefghijklmnop", "alerts@gmail.com", ["boss@x.com"])
    assert b"From: alerts@gmail.com" in data


def test_ses_is_the_fallback(nothing_set, monkeypatch):
    monkeypatch.setattr(settings, "aws_ses_from_email", "no-reply@x.com")
    monkeypatch.setattr(settings, "aws_ses_username", "u")
    monkeypatch.setattr(settings, "aws_ses_password", "p")
    monkeypatch.setattr(settings, "aws_region", "eu-west-1")
    srv = mailer.server()
    assert (srv.host, srv.sender) == ("email-smtp.eu-west-1.amazonaws.com", "no-reply@x.com")


def test_nothing_set_sends_nothing_and_does_not_raise(nothing_set):
    assert mailer.server() is None
    assert mailer.send(MIMEText("hi"), ["a@b.c"], "test") is False


def test_half_set_gmail_is_not_used(nothing_set, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_username", "alerts@gmail.com")
    assert mailer.server() is None


def test_a_refused_login_is_logged_not_raised(nothing_set, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_username", "alerts@gmail.com")
    monkeypatch.setattr(settings, "smtp_password", "wrong")

    class Refusing(FakeSMTP):
        def login(self, user, password):
            raise mailer.smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")

    monkeypatch.setattr(mailer.smtplib, "SMTP", Refusing)
    assert mailer.send(MIMEText("hi"), ["a@b.c"], "test") is False


def test_a_sender_name_shows_in_the_inbox_but_not_in_the_envelope(nothing_set, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_username", "alerts@gmail.com")
    monkeypatch.setattr(settings, "smtp_password", "abcdefghijklmnop")
    monkeypatch.setattr(settings, "smtp_from", "Scraping Hub <alerts@gmail.com>")
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent.clear()
    assert mailer.send(MIMEText("hi"), ["boss@x.com"], "test")
    *_, sender, _, data = FakeSMTP.sent[0]
    assert sender == "alerts@gmail.com"
    assert b"From: Scraping Hub <alerts@gmail.com>" in data
