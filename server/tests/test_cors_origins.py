"""Which pages may call the API: the dev console and the Windows app's window only.

    server/.venv/bin/python -m pytest server/tests/test_cors_origins.py
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: E402


@pytest.mark.parametrize("origin", ["http://localhost:4000", "http://127.0.0.1:4001", "app://hub"])
def test_the_consoles_are_allowed(origin):
    r = TestClient(app).options("/", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == origin


@pytest.mark.parametrize("origin", ["http://evil.example", "app://hub.evil", "https://localhost:4000", "app://other"])
def test_anything_else_is_not(origin):
    r = TestClient(app).options("/", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") is None
