"""Employee sign-in for the Windows app: hashed accounts, /auth/login, runs record who started them.

    server/.venv/bin/python -m pytest server/tests/test_accounts.py
"""

import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "installer"))

from app.core import accounts, run_manager  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _own_cache_and_no_panel(monkeypatch, tmp_path):
    """Remembered sign-ins go to a throwaway file, and no test reaches a real account server."""
    monkeypatch.setattr(accounts, "CACHE_FILE", tmp_path / "accounts_cache.json")
    monkeypatch.setattr(accounts, "_session", None)
    monkeypatch.delenv(accounts.URL_SETTING, raising=False)
    monkeypatch.delenv(accounts.KEY_SETTING, raising=False)


@pytest.fixture
def two_employees(monkeypatch):
    monkeypatch.setenv(accounts.SETTING, json.dumps({
        "sara": {"name": "Sara Khan", **accounts.hash_password("correct horse")},
        "omar": {"name": "Omar Ali", **accounts.hash_password("battery staple")},
    }))


def test_only_the_right_password_signs_in(two_employees):
    assert accounts.verify("sara", "correct horse") == "Sara Khan"
    assert accounts.verify("SARA ", "correct horse") == "Sara Khan"  # typed with caps / a space
    assert accounts.verify("sara", "battery staple") is None
    assert accounts.verify("nobody", "correct horse") is None


def test_login_endpoint(two_employees):
    client = TestClient(app)
    assert client.get("/auth/status").json() == {"accounts": 2, "panel": False}
    ok = client.post("/auth/login", json={"username": "omar", "password": "battery staple"})
    assert ok.status_code == 200 and ok.json() == {"username": "omar", "name": "Omar Ali"}
    assert client.post("/auth/login", json={"username": "omar", "password": "nope"}).status_code == 401


def test_no_accounts_means_nobody_signs_in(monkeypatch):
    monkeypatch.delenv(accounts.SETTING, raising=False)
    assert TestClient(app).get("/auth/status").json() == {"accounts": 0, "panel": False}
    assert accounts.verify("sara", "correct horse") is None


def test_a_run_records_who_started_it(tmp_path):
    # A throwaway route so the test goes through the real middleware without starting a scrape.
    @app.post("/_test/create-run")
    def _create():
        return run_manager.create_run("septa", tmp_path)

    client = TestClient(app)
    assert client.post("/_test/create-run", headers={"X-Hub-User": "sara"}).json()["started_by"] == "sara"
    assert client.post("/_test/create-run").json()["started_by"] is None  # development: no header
    assert client.post("/_test/create-run", headers={"X-Hub-User": "<script>"}).json()["started_by"] is None


def test_make_credentials_reads_the_accounts_csv(tmp_path):
    make_credentials = pytest.importorskip("make_credentials")  # installer/ is not in git
    csv = tmp_path / "accounts.csv"
    csv.write_text("username,name,password\nSara,Sara Khan,correct horse\n", encoding="utf-8")
    made = make_credentials.accounts_from_csv(csv)
    assert set(made) == {"sara"} and "correct horse" not in json.dumps(made)
    for bad in ("x,Short Name,longenough1\n", "sara,,longenough1\n", "sara,Sara,short\n",
                "sara,Sara,longenough1\nsara,Sara 2,longenough2\n"):
        csv.write_text("username,name,password\n" + bad, encoding="utf-8")
        with pytest.raises(SystemExit):
            make_credentials.accounts_from_csv(csv)


class Reply:
    def __init__(self, status_code, body):
        self.status_code, self._body = status_code, body

    def json(self):
        return self._body


class FakePanel:
    """The Vercel panel's /api/login and /api/signup, as the engine sees them."""

    def __init__(self):
        self.accounts = {}  # email -> {"name", "password", "approved"}
        self.down = False
        self.keys = []
        self.sessions = []  # (session id, "ping" | "end") as the engine reported them
        self.opened = 0

    def post(self, url, json, timeout, headers):
        self.keys.append(headers.get("X-Hub-Key"))
        if self.down:
            raise accounts.requests.ConnectionError("no internet")
        if url.endswith("/api/session"):
            self.sessions.append((json["session_id"], json["action"]))
            return Reply(200, {"ok": True})
        if url.endswith("/api/signup"):
            email = json["email"].strip().lower()
            if email in self.accounts:
                return Reply(409, {"detail": "An account with this email already exists or is waiting for approval."})
            self.accounts[email] = {"name": json["name"], "password": json["password"], "approved": False}
            return Reply(201, {"email": email, "status": "pending"})
        account = self.accounts.get(json["email"])
        if not account or account["password"] != json["password"]:
            return Reply(401, {"detail": "Wrong email or password"})
        if not account["approved"]:
            return Reply(409, {"detail": "This account is waiting for an administrator to approve it."})
        self.opened += 1
        return Reply(200, {"email": json["email"], "name": account["name"], "session_id": f"s{self.opened}"})


@pytest.fixture
def panel(monkeypatch):
    monkeypatch.setenv(accounts.URL_SETTING, "https://hub-admin.example.vercel.app/")
    monkeypatch.setenv(accounts.KEY_SETTING, "the-app-key")
    fake = FakePanel()
    monkeypatch.setattr(accounts.requests, "post", fake.post)
    return fake


def _login(client, email="nadia@fedpoint.us", password="window frame"):
    return client.post("/auth/login", json={"username": email, "password": password})


def test_a_sign_up_waits_for_approval_then_signs_in(panel):
    client = TestClient(app)
    made = client.post("/auth/signup", json={"name": "Nadia Rahman", "email": "Nadia@FedPoint.us", "password": "window frame"})
    assert made.status_code == 201 and made.json()["status"] == "pending"
    waiting = _login(client)
    assert waiting.status_code == 403 and "waiting" in waiting.json()["detail"]
    assert not accounts.CACHE_FILE.exists()  # nothing remembered before approval

    panel.accounts["nadia@fedpoint.us"]["approved"] = True  # an admin approves it on Vercel
    assert _login(client, email="NADIA@fedpoint.us").json() == {"username": "nadia@fedpoint.us", "name": "Nadia Rahman"}
    assert "window frame" not in accounts.CACHE_FILE.read_text(encoding="utf-8")  # only a hash is remembered
    assert set(panel.keys) == {"the-app-key"}  # every call carries the app's key
    assert client.get("/auth/status").json() == {"accounts": 1, "panel": True}


def test_offline_a_remembered_account_still_signs_in(panel):
    client = TestClient(app)
    panel.accounts["nadia@fedpoint.us"] = {"name": "Nadia Rahman", "password": "window frame", "approved": True}
    assert _login(client).status_code == 200
    panel.down = True
    assert _login(client).json()["name"] == "Nadia Rahman"
    assert _login(client, password="wrong one").status_code == 503  # offline, the cache never accepts a wrong password
    never = _login(client, email="omar@fedpoint.us")
    assert never.status_code == 503 and "internet" in never.json()["detail"]


def test_a_removed_account_is_forgotten_the_next_time_the_pc_is_online(panel):
    client = TestClient(app)
    panel.accounts["nadia@fedpoint.us"] = {"name": "Nadia Rahman", "password": "window frame", "approved": True}
    _login(client)
    del panel.accounts["nadia@fedpoint.us"]  # an admin removes her
    assert _login(client).status_code == 401
    panel.down = True
    assert _login(client).status_code == 503  # and offline she is no longer remembered either


def test_sign_up_problems_are_passed_on_in_words(panel):
    client = TestClient(app)
    body = {"name": "Nadia Rahman", "email": "nadia@fedpoint.us", "password": "window frame"}
    assert client.post("/auth/signup", json=body).status_code == 201
    again = client.post("/auth/signup", json=body)
    assert again.status_code == 409 and "already exists" in again.json()["detail"]
    panel.down = True
    offline = client.post("/auth/signup", json={**body, "email": "omar@fedpoint.us"})
    assert offline.status_code == 503 and "internet" in offline.json()["detail"]


def test_without_the_panel_only_issued_accounts_work(two_employees):
    client = TestClient(app)
    assert client.post("/auth/signup", json={"name": "N R", "email": "n@x.com", "password": "window frame"}).status_code == 503
    assert _login(client, email="sara", password="correct horse").json()["name"] == "Sara Khan"
    assert _login(client).status_code == 401


def test_an_issued_account_needs_no_panel(two_employees, panel):
    panel.down = True
    assert _login(TestClient(app), email="omar", password="battery staple").json()["name"] == "Omar Ali"


def test_an_email_identifies_the_runner():
    assert accounts.USERNAME.match("nadia@fedpoint.us") and accounts.USERNAME.match("sara")
    assert not accounts.USERNAME.match("<script>@x.com")


def test_a_sign_in_session_is_checked_in_and_ended(panel):
    client = TestClient(app)
    panel.accounts["nadia@fedpoint.us"] = {"name": "Nadia Rahman", "password": "window frame", "approved": True}
    _login(client)
    assert client.post("/auth/ping").json() == {"session": True}
    assert client.post("/auth/logout").json() == {"ok": True}
    assert panel.sessions == [("s1", "ping"), ("s1", "end")]
    client.post("/auth/logout")  # signing out twice ends it once
    assert client.post("/auth/ping").json() == {"session": False}
    assert panel.sessions == [("s1", "ping"), ("s1", "end")]


def test_a_new_sign_in_ends_a_session_left_open(panel):
    client = TestClient(app)
    panel.accounts["nadia@fedpoint.us"] = {"name": "Nadia Rahman", "password": "window frame", "approved": True}
    _login(client)
    _login(client)  # e.g. the app was killed before it could sign out
    assert panel.sessions == [("s1", "end")]
    client.post("/auth/logout")
    assert panel.sessions == [("s1", "end"), ("s2", "end")]


def test_signing_out_never_waits_on_an_unreachable_panel(panel):
    client = TestClient(app)
    panel.accounts["nadia@fedpoint.us"] = {"name": "Nadia Rahman", "password": "window frame", "approved": True}
    _login(client)
    panel.down = True
    assert client.post("/auth/ping").status_code == 200
    assert client.post("/auth/logout").json() == {"ok": True}
    assert client.post("/auth/ping").json() == {"session": False}


def test_an_offline_or_issued_sign_in_opens_no_session(two_employees, panel):
    client = TestClient(app)
    assert _login(client, email="omar", password="battery staple").status_code == 200
    assert client.post("/auth/ping").json() == {"session": False}
    client.post("/auth/logout")
    assert panel.sessions == []
