"""AST code gate tests — ported from mos_safety SecurityAgent."""
from __future__ import annotations

import pytest

from sovereign_agent.code_gate import check_code


def test_clean_code_passes():
    r = check_code("x = 1 + 2\nprint(x)")
    assert r.ok


def test_eval_blocked():
    r = check_code("eval('1+1')")
    assert not r.ok
    assert "eval" in r.reason


def test_exec_blocked():
    r = check_code("exec('x = 1')")
    assert not r.ok
    assert "exec" in r.reason


def test_compile_blocked():
    r = check_code("compile('x', '<s>', 'exec')")
    assert not r.ok


def test_os_system_string_blocked():
    r = check_code("import os\nos.system('ls')")
    assert not r.ok
    assert "os.system" in r.reason.lower()


def test_drop_table_blocked():
    r = check_code('cur.execute("DROP TABLE atoms")')
    assert not r.ok
    assert "DROP TABLE" in r.reason


def test_dunder_import_blocked():
    r = check_code("__import__('os').system('ls')")
    assert not r.ok


def test_attr_call_caught():
    # Module-attribute eval — caught by AST walk
    r = check_code("import builtins\nbuiltins.eval('1+1')")
    assert not r.ok


def test_syntax_error_caught():
    r = check_code("def foo(:")
    assert not r.ok
    assert "syntax" in r.reason.lower()


def test_pickle_loads_blocked():
    r = check_code("import pickle\npickle.loads(b'x')")
    assert not r.ok


@pytest.mark.parametrize("safe_call", [
    "len([1,2,3])",
    "max(1, 2)",
    "sorted([3,1,2])",
    "json.dumps({'a': 1})",
])
def test_normal_calls_pass(safe_call):
    r = check_code(f"import json\nx = {safe_call}")
    assert r.ok, f"unexpectedly blocked: {safe_call}: {r.reason}"
