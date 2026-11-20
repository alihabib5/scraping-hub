"""Nuitka user plugin for the Scraping Hub build (build_server.py passes it with --user-plugin).

1. Rizviz's own modules are compiled with every docstring blanked. Docstrings
   explain how the code works and would otherwise ship as readable text in the
   exe. Only ours: libraries may need theirs at run time (SQLAlchemy asserts on
   them while importing), which rules out Nuitka's global no_docstrings flag.
2. PyMuPDF is embedded as bytecode instead of C. Its generated bindings are
   185 MB of C (module.pymupdf.mupdf.c alone is 145 MB) that take hours to
   compile, and it is public open-source code, so compiling it protects
   nothing. As bytecode it is still inside the exe: no .py files on disk.
"""

import ast

from nuitka.plugins.PluginBase import NuitkaPluginBase

# hub_server.py is the entry script, which Nuitka names __main__.
OWN_CODE = ("app", "main", "hub_server", "__main__")
BYTECODE_PACKAGES = ("pymupdf", "fitz")


def _within(name: str, packages: tuple[str, ...]) -> bool:
    return any(name == p or name.startswith(p + ".") for p in packages)


def strip_docstrings(source: str) -> str:
    """`source` with every module, class and function docstring replaced by "".

    Edits the text in place rather than regenerating it, so each line keeps its
    number and a traceback from the installed app still points at the right line.
    """
    tree = ast.parse(source)
    docs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docs.append(first.value)
    # ast columns are UTF-8 byte offsets, so edit the encoded lines; last one
    # first, so the offsets of the ones before it still hold.
    lines = source.encode("utf-8").splitlines(keepends=True)
    for doc in sorted(docs, key=lambda n: (n.lineno, n.col_offset), reverse=True):
        first, last = doc.lineno - 1, doc.end_lineno - 1
        head, tail = lines[first][: doc.col_offset], lines[last][doc.end_col_offset :]
        lines[first : last + 1] = [head + b'""' + b"\n" * (last - first) + tail]
    return b"".join(lines).decode("utf-8")


class NuitkaPluginScrapingHub(NuitkaPluginBase):
    plugin_name = "scraping-hub"
    plugin_desc = "Blank Rizviz docstrings; embed PyMuPDF as bytecode."

    def onModuleSourceCode(self, module_name, source_filename, source_code):
        if _within(str(module_name), OWN_CODE):
            return strip_docstrings(source_code)
        return source_code

    def decideCompilation(self, module_name):
        if _within(str(module_name), BYTECODE_PACKAGES):
            return "bytecode"
        return None
