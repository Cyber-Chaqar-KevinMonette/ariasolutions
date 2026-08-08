"""Behavior tests for aria-workflow-safe-eval — prove the restricted evaluator
still does its job (normal verify_step criteria evaluate correctly) AND closes
the sandbox-escape hole a raw eval() with emptied __builtins__ leaves open."""
from __future__ import annotations

import pytest

from sovereign_agent.workflow.safe_eval import UnsafeCriteriaError, safe_eval

NS = {"succeeded": True, "status": "done", "exit_code": 0, "artifacts": ["a.txt", "b.log"]}


# ── normal verify_step usage keeps working ──────────────────────────────────

def test_plain_name_lookup():
    assert safe_eval("succeeded", NS) is True


def test_comparison():
    assert safe_eval("exit_code == 0", NS) is True
    assert safe_eval("exit_code != 0", NS) is False


def test_boolean_combination():
    assert safe_eval("succeeded and exit_code == 0", NS) is True
    assert safe_eval("not succeeded or exit_code == 1", NS) is False


def test_membership_check():
    assert safe_eval("'a.txt' in artifacts", NS) is True
    assert safe_eval("'missing.txt' in artifacts", NS) is False


def test_string_equality():
    assert safe_eval("status == 'done'", NS) is True


# ── the actual vulnerability this module closes ─────────────────────────────

def test_gadget_chain_rejected():
    """The exact escape a raw eval(criteria, {'__builtins__': {}}, ns) allows:
    attribute-traversal reaches object subclasses without touching a builtin name."""
    with pytest.raises(UnsafeCriteriaError):
        safe_eval("().__class__.__bases__[0].__subclasses__()", NS)


@pytest.mark.parametrize("attack", [
    "__import__('os').system('id')",
    "(1).bit_length()",
    "[].append(1)",
    "artifacts.append(1)",
    "succeeded.__class__",
    "(lambda: 1)()",
    "[x for x in artifacts]",
])
def test_other_escape_vectors_rejected(attack):
    with pytest.raises(UnsafeCriteriaError):
        safe_eval(attack, NS)


def test_unknown_name_rejected():
    """A name not present in the namespace is rejected rather than raising a
    bare NameError deep inside eval — fails closed, with a clear reason."""
    with pytest.raises(UnsafeCriteriaError, match="unknown name"):
        safe_eval("some_undeclared_variable", NS)


def test_invalid_syntax_rejected():
    with pytest.raises(UnsafeCriteriaError, match="invalid criteria syntax"):
        safe_eval("succeeded and", NS)


def test_error_type_is_a_value_error():
    """Callers that already catch ValueError/Exception broadly keep working."""
    assert issubclass(UnsafeCriteriaError, ValueError)
