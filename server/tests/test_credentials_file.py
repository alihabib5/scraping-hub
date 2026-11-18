"""The separate encrypted credentials file the installed Windows app reads.

Made by installer/make_credentials.py, placed by the setup wizard in the data
dir, opened at start-up by hub_server.py with the key compiled into the exe.

    server/.venv/bin/python -m pytest server/tests/test_credentials_file.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER.parent / "installer"))

import make_credentials  # noqa: E402
from app.core.credentials_file import FILE_NAME, decrypt, encrypt  # noqa: E402

KEY = bytes(range(32))
ENV = """\
BIDNET_USERNAME=buyer@rizviz.example
BIDNET_PASSWORD='p#ss w0rd $till'
EMPTY_ONE=
DATABASE_URL=postgresql+psycopg2://postgres:x@localhost:5432/scraping-hub
DOWNLOAD_DIR=../data/documents
"""


def test_only_credentials_go_in_and_they_come_back_out(tmp_path):
    env = tmp_path / ".env"
    env.write_text(ENV, encoding="utf-8")
    values = make_credentials.credentials_from_env(env)
    assert values == {"BIDNET_USERNAME": "buyer@rizviz.example", "BIDNET_PASSWORD": "p#ss w0rd $till"}
    assert decrypt(encrypt(values, KEY), KEY) == values


def test_the_file_does_not_show_any_credential():
    values = {"BIDNET_PASSWORD": "p#ss w0rd $till", "BIDNET_USERNAME": "buyer@rizviz.example"}
    data = encrypt(values, KEY)
    for value in values.values():
        assert value.encode() not in data


def test_a_file_for_another_build_or_a_damaged_one_is_refused():
    data = encrypt({"A": "b"}, KEY)
    with pytest.raises(ValueError):
        decrypt(data, bytes(32))  # another build's key
    with pytest.raises(ValueError):
        decrypt(data[:-1] + bytes([data[-1] ^ 1]), KEY)
    with pytest.raises(ValueError):
        decrypt(b"not a credentials file", KEY)


def _start(tmp_path, data_dir, extra_env=None):
    """Run the entry point's loader in a fresh interpreter, with a fake compiled-in key."""
    (tmp_path / "_app_key.py").write_text(f"KEY = {KEY!r}\n", encoding="utf-8")
    probe = (
        "import os, hub_server; hub_server._load_credentials_file(); "
        "print(os.environ.get('HUB_TEST_FROM_FILE'), os.environ.get('HUB_TEST_PRESET'))"
    )
    env = {**os.environ, "PYTHONPATH": f"{tmp_path}{os.pathsep}{SERVER}",
           "SCRAPING_HUB_DATA_DIR": str(data_dir), **(extra_env or {})}
    out = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.split(), out.stderr


def test_the_app_loads_the_file_from_the_data_dir_without_overriding(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / FILE_NAME).write_bytes(encrypt({"HUB_TEST_FROM_FILE": "from-file", "HUB_TEST_PRESET": "from-file"}, KEY))
    values, _ = _start(tmp_path, data, {"HUB_TEST_PRESET": "already-set"})
    assert values == ["from-file", "already-set"]


def test_no_file_yet_the_app_still_starts_and_says_so(tmp_path):
    values, log = _start(tmp_path, tmp_path / "empty")
    assert values == ["None", "None"]


def test_a_wrong_file_is_reported_not_fatal(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / FILE_NAME).write_bytes(encrypt({"HUB_TEST_FROM_FILE": "x"}, bytes(32)))
    values, _ = _start(tmp_path, data)
    assert values == ["None", "None"]


def test_development_without_a_compiled_key_changes_nothing():
    probe = "import os, hub_server; before = dict(os.environ); hub_server._load_credentials_file(); print(before == dict(os.environ))"
    env = {**os.environ, "PYTHONPATH": str(SERVER)}
    out = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "True"


def _self_check(tmp_path, data_dir):
    (tmp_path / "_app_key.py").write_text(f"KEY = {KEY!r}\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": f"{tmp_path}{os.pathsep}{SERVER}", "SCRAPING_HUB_DATA_DIR": str(data_dir)}
    return subprocess.run([sys.executable, str(SERVER / "hub_server.py"), "--self-check"],
                          env=env, cwd=tmp_path, capture_output=True, text=True, timeout=120)


def test_self_check_passes_when_everything_a_run_needs_is_there(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / FILE_NAME).write_bytes(encrypt({"HUB_TEST_FROM_FILE": "x"}, KEY))
    out = _self_check(tmp_path, data)
    assert out.returncode == 0, out.stdout + out.stderr
    for line in ("OK    server app", "OK    PDF reading", "OK    Word reading", "OK    credentials file"):
        assert line in out.stdout
    assert "Self-check passed" in out.stdout


def test_self_check_fails_without_the_credentials_file(tmp_path):
    out = _self_check(tmp_path, tmp_path / "empty")
    assert out.returncode == 1
    assert "FAIL  credentials file" in out.stdout


def test_the_installed_layout_puts_every_folder_in_programdata():
    probe = (
        "import os, json, hub_server; hub_server._apply_installed_layout(); "
        "print(json.dumps({k: os.environ[k] for k in ('SCRAPING_HUB_DATA_DIR', 'ARCHIVE_DIR', "
        "'DOWNLOAD_DIR', 'WORK_DIR', 'NORTHDAKOTA_PROFILE_DIR')}))"
    )
    env = {k: v for k, v in os.environ.items() if k not in (
        "SCRAPING_HUB_DATA_DIR", "ARCHIVE_DIR", "DOWNLOAD_DIR", "WORK_DIR", "NORTHDAKOTA_PROFILE_DIR")}
    env.update({"PYTHONPATH": str(SERVER), "ProgramData": r"C:\ProgramData", "WORK_DIR": r"D:\keep-me"})
    out = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    paths = json.loads(out.stdout)
    assert paths["SCRAPING_HUB_DATA_DIR"] == r"C:\ProgramData\Scraping Hub"
    assert paths["ARCHIVE_DIR"] == r"C:\ProgramData\Scraping Hub\archives"
    assert paths["NORTHDAKOTA_PROFILE_DIR"] == r"C:\ProgramData\Scraping Hub\chrome_profiles\northdakota"
    assert paths["WORK_DIR"] == r"D:\keep-me"  # whoever started it wins


def _check(tmp_path, file):
    """`hub_server.py --check-credentials FILE` with a fake compiled-in key."""
    (tmp_path / "_app_key.py").write_text(f"KEY = {KEY!r}\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": f"{tmp_path}{os.pathsep}{SERVER}"}
    return subprocess.run([sys.executable, str(SERVER / "hub_server.py"), "--check-credentials", str(file)],
                          env=env, cwd=tmp_path, capture_output=True, text=True, timeout=60)


def test_check_credentials_accepts_a_file_for_this_build(tmp_path):
    good = tmp_path / "new.shc"
    good.write_bytes(encrypt({"A": "1", "B": "2"}, KEY))
    out = _check(tmp_path, good)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "OK - 2 settings"


def test_check_credentials_refuses_another_builds_file_a_wrong_file_or_none(tmp_path):
    other = tmp_path / "other.shc"
    other.write_bytes(encrypt({"A": "1"}, bytes(32)))
    junk = tmp_path / "notes.shc"
    junk.write_text("hello", encoding="utf-8")
    for file in (other, junk, tmp_path / "missing.shc"):
        out = _check(tmp_path, file)
        assert out.returncode == 1, file
        assert out.stdout.startswith("FAIL - "), out.stdout
