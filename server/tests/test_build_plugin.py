"""The build plugin blanks Rizviz's docstrings without changing what the code does.

    server/.venv/bin/python -m pytest server/tests/test_build_plugin.py
"""

import ast
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER.parent / "installer"))

from nuitka_plugin import strip_docstrings  # noqa: E402

SAMPLE = '''"""Module docstring: how the scraper works."""
from __future__ import annotations

PORTAL = """not a docstring"""


class Scraper:
    """Class docstring
    over two lines."""

    def run(self, n):
        """Method docstring — with ünïcode."""
        label = "kept"
        return f"{label}:{n}"


async def fetch():
    """Async docstring."""
    return 1


def no_doc():
    return "also kept"
'''


def _docstrings(source):
    tree = ast.parse(source)
    return [ast.get_docstring(n, clean=False) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and ast.get_docstring(n, clean=False)]


def test_docstrings_go_and_everything_else_stays():
    out = strip_docstrings(SAMPLE)
    assert _docstrings(out) == []
    for gone in ("how the scraper works", "Class docstring", "ünïcode", "Async docstring"):
        assert gone not in out
    for kept in ('"""not a docstring"""', '"kept"', '"also kept"', "from __future__ import annotations"):
        assert kept in out


def test_every_line_keeps_its_number():
    out = strip_docstrings(SAMPLE)
    assert len(out.splitlines()) == len(SAMPLE.splitlines())
    for before, after in zip(SAMPLE.splitlines(), out.splitlines()):
        if "def " in before or "return" in before or "class " in before:
            assert before == after


def test_the_code_still_runs_the_same():
    ns = {}
    exec(compile(strip_docstrings(SAMPLE), "sample", "exec"), ns)
    assert ns["Scraper"]().run(3) == "kept:3"
    assert ns["no_doc"]() == "also kept"
    assert ns["PORTAL"] == "not a docstring"


def test_every_server_module_strips_cleanly():
    files = [*SERVER.joinpath("app").rglob("*.py"), SERVER / "main.py", SERVER / "hub_server.py"]
    assert len(files) > 100
    for path in files:
        source = path.read_text(encoding="utf-8")
        out = strip_docstrings(source)
        compile(out, str(path), "exec")  # still valid Python
        assert len(out.splitlines()) == len(source.splitlines()), path
        assert _docstrings(out) == [], path
