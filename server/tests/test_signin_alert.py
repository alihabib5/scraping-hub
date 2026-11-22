"""Administrators get an email for every sign-in to the Windows app.

    server/.venv/bin/python -m pytest server/tests/test_signin_alert.py
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core import accounts
from app.services import signin_alert
from main import app
from tests.test_accounts import FakePanel


@pytest.fixture
def sent(monkeypatch):
    """Alerts on, with SES replaced by a list of what would have been sent."""
    out = []
    monkeypatch.setattr(settings, "signin_alert_emails", "boss@rizviz.example, it@rizviz.example")
    monkeypatch.setattr(signin_alert, "_send", lambda to, subject, text, body: out.append((to, subject, text, body)) or True)
    real = signin_alert.notify

    def wait(*args, **kwargs):  # run the background send to completion, so tests can look at it
        t = real(*args, **kwargs)
        if t:
            t.join(5)
        return t

    monkeypatch.setattr(signin_alert, "notify", wait)
    return out


@pytest.fixture
def panel(monkeypatch, tmp_path):
    monkeypatch.setattr(accounts, "CACHE_FILE", tmp_path / "accounts_cache.json")
    monkeypatch.setattr(accounts, "_session", None)
    monkeypatch.setenv(accounts.URL_SETTING, "https://hub-admin.example.vercel.app/")
    monkeypatch.setenv(accounts.KEY_SETTING, "the-app-key")
    fake = FakePanel()
    fake.accounts["nadia@fedpoint.us"] = {"name": "Nadia Rahman", "password": "window frame", "approved": True}
    monkeypatch.setattr(accounts.requests, "post", fake.post)
    return fake


def _login(password="window frame"):
    return TestClient(app).post("/auth/login", json={"username": "Nadia@FedPoint.us", "password": password})


def test_an_online_sign_in_emails_who_when_and_the_public_ip(sent, panel):
    assert _login().status_code == 200
    [(to, subject, text, body)] = sent
    assert to == ["boss@rizviz.example", "it@rizviz.example"]
    assert "Nadia Rahman <nadia@fedpoint.us>" in subject
    for fact in ("Public IP: 203.0.113.7", "Computer name:", "Windows user:", "Local IP:", "Time (UTC):",
                 "Signed in via: Account server (online)"):
        assert fact in text
    assert "203.0.113.7" in body and "<table" in body


def test_an_offline_sign_in_is_reported_too_without_a_public_ip(sent, panel):
    assert _login().status_code == 200
    panel.down = True
    assert _login().status_code == 200
    text = sent[-1][2]
    assert "Remembered on this PC" in text and "Public IP: not known" in text


def test_a_wrong_password_sends_nothing(sent, panel):
    assert _login(password="nope").status_code == 401
    assert sent == []


def test_an_issued_account_is_reported(sent, monkeypatch, tmp_path):
    monkeypatch.setattr(accounts, "CACHE_FILE", tmp_path / "c.json")
    monkeypatch.delenv(accounts.URL_SETTING, raising=False)
    monkeypatch.setenv(accounts.SETTING, json.dumps({"sara": {"name": "Sara Khan", **accounts.hash_password("correct horse")}}))
    assert TestClient(app).post("/auth/login", json={"username": "sara", "password": "correct horse"}).status_code == 200
    assert "Issued account" in sent[0][2]


def test_no_addresses_means_no_alert(monkeypatch):
    monkeypatch.setattr(settings, "signin_alert_emails", " , ")
    assert signin_alert.notify("a@b.c", "A", "panel") is None


def test_a_failing_email_never_blocks_the_sign_in(monkeypatch, panel):
    monkeypatch.setattr(settings, "signin_alert_emails", "boss@rizviz.example")
    monkeypatch.setattr(signin_alert, "notify", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("smtp down")))
    assert _login().status_code == 200


def test_times_are_given_in_local_time_and_utc():
    karachi = datetime(2026, 11, 22, 23, 5, 9, tzinfo=timezone(timedelta(hours=5)))
    rows = dict(signin_alert.details("a@b.c", "A", "panel", "1.2.3.4", now=karachi))
    assert rows["Time (UTC)"] == "2026-11-22 18:05:09 UTC"
    assert "+0500" in rows["Time (this PC)"]


def test_names_with_markup_are_escaped():
    subject, _, body = signin_alert._message("x@y.z", "<b>Eve</b>", [("Name", "<b>Eve</b>")])
    assert "<b>Eve</b>" not in body and "&lt;b&gt;Eve&lt;/b&gt;" in body
