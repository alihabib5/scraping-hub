"""RideMetro's two accounts: resolution, credential routing, and the API gate.

No browser and no portal — what these pin down is that the *right* credentials
reach the login step, that an account which cannot work is refused before a run
exists, and that choosing an account changes nothing else about the flow.

    server/.venv/bin/python -m pytest server/tests/test_ridemetro_accounts.py
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.scrapers.ridemetro import accounts  # noqa: E402

CREDENTIAL_FIELDS = (
    "hoope_lab_username", "hoope_lab_password",
    "fedpoint_username", "fedpoint_password",
    "euna_bonfire_email", "euna_bonfire_password",
)


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Both accounts unset, with a setter for the fields under test.

    Patches Settings rather than os.environ: that is where accounts.py reads
    from. `ENV_FILE` is pointed at a path that does not exist for the same
    reason — the credential check compares a loaded value against the literal
    `.env`, so without this every assertion here would depend on whatever the
    developer happens to have in their own file. That comparison is what
    test_credentials.py exists to cover, against files it writes itself.
    """
    monkeypatch.setattr(accounts, "ENV_FILE", tmp_path / "absent.env")
    for field in CREDENTIAL_FIELDS:
        monkeypatch.setattr(settings, field, "", raising=False)

    def configure(**fields: str) -> None:
        for field, value in fields.items():
            monkeypatch.setattr(settings, field, value, raising=False)

    return configure


# -- resolution --------------------------------------------------------------


def test_both_accounts_are_offered_with_stable_keys():
    assert list(accounts.ACCOUNTS) == ["hoope_lab", "fedpoint"]
    assert [a.label for a in accounts.ACCOUNTS.values()] == ["Hoope Lab", "FedPoint"]


def test_a_blank_choice_falls_back_to_the_default_account():
    """An existing caller that names no account keeps the behaviour it had."""
    for value in (None, "", "   "):
        assert accounts.get(value).key == accounts.DEFAULT_ACCOUNT


def test_the_key_is_matched_regardless_of_case_or_padding():
    assert accounts.get(" FedPoint ").key == "fedpoint"
    assert accounts.get("HOOPE_LAB").key == "hoope_lab"


def test_an_unknown_account_names_the_valid_choices():
    with pytest.raises(accounts.UnknownAccount) as excinfo:
        accounts.get("acme")
    assert "hoope_lab" in str(excinfo.value) and "fedpoint" in str(excinfo.value)


# -- credential routing ------------------------------------------------------


def test_each_account_reads_its_own_credentials(env):
    env(
        hoope_lab_username="hoope@example.com", hoope_lab_password="hoope-secret",
        fedpoint_username="fed@example.com", fedpoint_password="fed-secret",
    )
    hoope, fed = accounts.get("hoope_lab"), accounts.get("fedpoint")
    assert (hoope.username, hoope.password) == ("hoope@example.com", "hoope-secret")
    assert (fed.username, fed.password) == ("fed@example.com", "fed-secret")


def test_hoope_lab_falls_back_to_the_pre_accounts_keys(env):
    """A deployment whose .env still has RIDEMETRO_* keeps working untouched."""
    env(euna_bonfire_email="old@example.com", euna_bonfire_password="old-secret")
    account = accounts.get("hoope_lab")
    assert (account.username, account.password) == ("old@example.com", "old-secret")
    assert account.is_configured


def test_the_accounts_own_keys_win_over_the_fallback(env):
    env(
        hoope_lab_username="new@example.com", hoope_lab_password="new-secret",
        euna_bonfire_email="old@example.com", euna_bonfire_password="old-secret",
    )
    account = accounts.get("hoope_lab")
    assert (account.username, account.password) == ("new@example.com", "new-secret")


def test_fedpoint_has_no_fallback_to_the_shared_keys(env):
    """The old keys were one account's; they must not silently become the other's."""
    env(euna_bonfire_email="old@example.com", euna_bonfire_password="old-secret")
    account = accounts.get("fedpoint")
    assert (account.username, account.password) == ("", "")
    assert not account.is_configured


# -- validation --------------------------------------------------------------


def test_a_half_configured_account_is_refused_and_names_the_missing_key(env):
    env(fedpoint_username="fed@example.com")  # password left unset
    with pytest.raises(accounts.AccountNotConfigured) as excinfo:
        accounts.require("fedpoint")
    message = str(excinfo.value)
    assert "FEDPOINT_PASSWORD" in message
    assert "FEDPOINT_USERNAME" not in message  # that half is fine — don't muddy it


def test_an_entirely_unset_account_names_both_keys(env):
    with pytest.raises(accounts.AccountNotConfigured) as excinfo:
        accounts.require("fedpoint")
    assert "FEDPOINT_USERNAME" in str(excinfo.value)
    assert "FEDPOINT_PASSWORD" in str(excinfo.value)


def test_require_returns_a_usable_account(env):
    env(fedpoint_username="fed@example.com", fedpoint_password="fed-secret")
    assert accounts.require("fedpoint").key == "fedpoint"


# -- what the console is told ------------------------------------------------


def test_the_catalog_reports_configuration_without_naming_the_login(env):
    """The console identifies an account by label. The address is not sent —
    not even masked — so it cannot end up on screen or in a network payload."""
    env(
        hoope_lab_username="raheel@hoopoelabs.com", hoope_lab_password="hoope-secret",
        fedpoint_username="", fedpoint_password="",
    )
    catalog = accounts.catalog()
    assert [entry["key"] for entry in catalog] == ["hoope_lab", "fedpoint"]

    hoope, fed = catalog
    assert hoope["configured"] is True and fed["configured"] is False
    # The keys to fix are named; the credentials and the address are not.
    assert fed["password_env"] == "FEDPOINT_PASSWORD"
    payload = str(catalog)
    for secret in ("raheel@hoopoelabs.com", "hoopoelabs.com", "raheel", "hoope-secret"):
        assert secret not in payload
    assert "username" not in hoope


def test_mask_keeps_the_domain_and_hides_the_local_part():
    assert accounts.mask("raheel@hoopoelabs.com") == "ra…@hoopoelabs.com"
    assert accounts.mask("ab@x.com") == "…@x.com"      # too short to show any of
    assert accounts.mask("plainuser") == "pl…"          # not an address at all
    assert accounts.mask("") == "(not set)"


# -- the API gate ------------------------------------------------------------


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app)


def test_accounts_endpoint_lists_both_and_the_default(client):
    body = client.get("/ridemetro/accounts").json()
    assert body["default"] == accounts.DEFAULT_ACCOUNT
    assert [entry["key"] for entry in body["accounts"]] == ["hoope_lab", "fedpoint"]


def test_starting_an_unconfigured_account_is_refused_before_a_run_exists(client, env):
    from app.core import run_manager

    before = len(run_manager.list_runs("ridemetro"))
    response = client.post("/ridemetro/scrape", params={"account": "fedpoint"})
    assert response.status_code == 400
    assert "FEDPOINT_USERNAME" in response.json()["detail"]
    # No run was created, so nothing appears in the history to explain away.
    assert len(run_manager.list_runs("ridemetro")) == before


def test_starting_an_unknown_account_is_a_400_not_a_default(client):
    response = client.post("/ridemetro/scrape", params={"account": "acme"})
    assert response.status_code == 400
    assert "Unknown EUNA BONFIRE account" in response.json()["detail"]


def test_a_started_run_records_which_account_it_uses(client, env, monkeypatch):
    env(fedpoint_username="fed@example.com", fedpoint_password="fed-secret")
    # Don't actually launch a browser: the background task is what runs it.
    monkeypatch.setattr(
        "app.scrapers.ridemetro.router.execute_run", lambda run_id: None
    )
    body = client.post("/ridemetro/scrape", params={"account": "fedpoint"}).json()

    from app.core import run_manager

    run = run_manager.get_run(body["run_id"])
    assert body["account"] == "fedpoint"
    assert run["account"] == "fedpoint"
    assert run["account_label"] == "FedPoint"
    # Run state is served to the console, so the address is not on it.
    assert "fed@example.com" not in str(run)
    # The account is in the workspace name, so it reaches the archive filename —
    # two accounts' reports must not be told apart only by timestamp.
    assert "FedPoint" in Path(run["folder"]).name


# -- the flow is unchanged by the choice -------------------------------------


def test_the_scraper_types_the_selected_accounts_credentials(env, monkeypatch):
    """The login sequence is untouched; only the strings it types differ."""
    env(fedpoint_username="fed@example.com", fedpoint_password="fed-secret")

    from app.core import run_manager
    from app.scrapers.ridemetro.scraper import RideMetroScraper

    run = run_manager.create_run("ridemetro", Path("/tmp"), {"account": "fedpoint"})
    scraper = RideMetroScraper(run["run_id"])
    scraper._select_account()

    assert scraper.account.key == "fedpoint"
    assert scraper.account.username == "fed@example.com"
    assert scraper.account.password == "fed-secret"
    # …and the run publishes which account it is by name only.
    stored = run_manager.get_run(run["run_id"])
    assert stored["account_label"] == "FedPoint"
    for secret in ("fed-secret", "fed@example.com"):
        assert secret not in str(stored)


def test_a_run_whose_account_became_unusable_fails_before_the_browser_starts(env):
    from app.core import run_manager
    from app.scrapers.ridemetro.scraper import RideMetroScraper

    run = run_manager.create_run("ridemetro", Path("/tmp"), {"account": "fedpoint"})
    scraper = RideMetroScraper(run["run_id"])
    with pytest.raises(accounts.AccountNotConfigured):
        scraper._select_account()
    assert scraper.driver is None
