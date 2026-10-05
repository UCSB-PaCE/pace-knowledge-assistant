"""Smoke tests: no DB, no model, no network.

Streamlit/pymongo/voyageai/sentence-transformers are NOT installed in CI, so the
heavy modules are only parsed/compiled, never imported. vector-index.py creates a
live Atlas search index at import time and must never be imported by a test.
"""
import ast
import glob
import os
import py_compile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_FILES = sorted(glob.glob(os.path.join(ROOT, "*.py")))


def test_expected_modules_present():
    names = {os.path.basename(p) for p in PY_FILES}
    assert {"app.py", "zohoai_app.py", "mongodb_RAG.py", "llm_agent.py",
            "intent_agent.py", "vector-index.py"} <= names


@pytest.mark.parametrize("path", PY_FILES, ids=os.path.basename)
def test_parses_and_compiles(path, tmp_path):
    with open(path, encoding="utf-8") as f:
        ast.parse(f.read(), filename=path)
    py_compile.compile(path, cfile=str(tmp_path / "x.pyc"), doraise=True)


def test_vector_index_has_import_time_side_effects():
    # Documents why it is never imported: it connects to MongoDB at module level.
    tree = ast.parse(open(os.path.join(ROOT, "vector-index.py"), encoding="utf-8").read())
    calls = [n for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)]
    assert any(getattr(c.value.func, "id", "") == "MongoClient" for c in calls)


def test_no_hardcoded_secrets_in_sources():
    import re
    pat = re.compile(r"(mongodb(\+srv)?://[^\s\"']+:[^\s\"']+@|sk-[A-Za-z0-9]{20,}|pa-[A-Za-z0-9_-]{30,})")
    for path in PY_FILES:
        assert not pat.search(open(path, encoding="utf-8").read()), os.path.basename(path)
