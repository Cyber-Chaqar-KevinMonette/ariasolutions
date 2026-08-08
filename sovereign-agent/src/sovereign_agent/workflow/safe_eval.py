"""safe_eval.py — a restricted boolean-expression evaluator for workflow verify criteria.

god_engine.py's `verify_step` used to evaluate operator/model-supplied `criteria` strings with
raw `eval(criteria, {"__builtins__": {}}, ns)`. Emptying `__builtins__` is a well-known incomplete
sandbox: attribute-traversal gadget chains (e.g. `().__class__.__bases__[0].__subclasses__()`)
reach arbitrary classes without ever touching a builtin name, so a crafted criteria string could
escalate to full code execution.

`safe_eval` closes that hole by walking the parsed AST first and rejecting anything that isn't a
boolean/comparison expression over plain names, literals, lists, and tuples — no attribute access,
no calls, no subscripting, no comprehensions, no lambdas. There is no way to reach a `__subclasses__`
style gadget without a `Call` or `Attribute` node, so those are rejected outright rather than merely
hidden behind an emptied namespace.
"""
from __future__ import annotations

import ast
from typing import Any

_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp, ast.And, ast.Or,
    ast.UnaryOp, ast.Not,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.Name, ast.Load,
    ast.Constant, ast.List, ast.Tuple,
)


class UnsafeCriteriaError(ValueError):
    """Raised when a criteria string contains a disallowed expression element."""


def safe_eval(criteria: str, ns: dict[str, Any]) -> Any:
    """Evaluate a boolean criteria expression over a fixed namespace `ns`.

    Only boolean ops, comparisons, plain name lookups (restricted to keys already in `ns`),
    literals, lists, and tuples are permitted. Raises `UnsafeCriteriaError` (a ValueError
    subclass) for anything else — including a `SyntaxError` from `ast.parse`, which is
    re-raised as `UnsafeCriteriaError` so callers have one exception type to catch.
    """
    try:
        tree = ast.parse(criteria, mode="eval")
    except SyntaxError as exc:
        raise UnsafeCriteriaError(f"invalid criteria syntax: {exc}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise UnsafeCriteriaError(
                f"disallowed expression element: {type(node).__name__}"
            )
        if isinstance(node, ast.Name) and node.id not in ns:
            raise UnsafeCriteriaError(f"unknown name: {node.id!r}")

    return eval(compile(tree, "<criteria>", "eval"), {"__builtins__": {}}, ns)  # noqa: S307
