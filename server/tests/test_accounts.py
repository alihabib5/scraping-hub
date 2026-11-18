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

import make_credentials  # noqa: E402
from app.core import accounts, run_manager  # noqa: E402
from main import app  # noqa: E402


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
    assert client.get("/auth/status").json() == {"accounts": 2}
    ok = client.post("/auth/login", json={"username": "omar", "password": "battery staple"})
    assert ok.status_code == 200 and ok.json() == {"username": "omar", "name": "Omar Ali"}
    assert client.post("/auth/login", json={"username": "omar", "password": "nope"}).status_code == 401


def test_no_accounts_means_nobody_signs_in(monkeypatch):
    monkeypatch.delenv(accounts.SETTING, raising=False)
    assert TestClient(app).get("/auth/status").json() == {"accounts": 0}
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
    csv = tmp_path / "accounts.csv"
    csv.write_text("username,name,password\nSara,Sara Khan,correct horse\n", encoding="utf-8")
    made = make_credentials.accounts_from_csv(csv)
    assert set(made) == {"sara"} and "correct horse" not in json.dumps(made)
    for bad in ("x,Short Name,longenough1\n", "sara,,longenough1\n", "sara,Sara,short\n",
                "sara,Sara,longenough1\nsara,Sara 2,longenough2\n"):
        csv.write_text("username,name,password\n" + bad, encoding="utf-8")
        with pytest.raises(SystemExit):
            make_credentials.accounts_from_csv(csv)
