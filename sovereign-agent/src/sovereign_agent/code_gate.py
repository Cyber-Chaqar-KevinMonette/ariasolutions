"""AST code gate. Ported from mos_safety.SecurityAgent.

A focused, single-purpose check for tools that accept Python code as input
(e.g., a future ``run_python`` tool). Blocks dangerous patterns at parse time
*before* dispatch — the model never gets to run code that contains them.

This is NOT a full sandbox. It's a cheap pre-flight check that catches the
obvious-bad patterns. The real isolation comes from bwrap (architecture §12)
and the authority/path layers. Belt + suspenders.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass


# String-level patterns scanned case-insensitively against the raw source.
FORBIDDEN_STRINGS: frozenset[str] = frozenset({
    "DROP TABLE",
    "DROP DATABASE",
    "__import__",
    "os.system",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.run",
    "ctypes",
    "marshal.loads",
    "pickle.loads",
    "shutil.rmtree(/)",
    "rm -rf /",
})

# Identifier names that, when called, are forbidden — caught via AST walk.
FORBIDDEN_CALLS: frozenset[str] = frozenset({
    "eval",
    "exec",
    "compile",
    "breakpoint",
})


@dataclass(frozen=True)
class CodeGateResult:
    ok: bool
    reason: str = ""


def check_code(source: str) -> CodeGateResult:
    """Scan source for forbidden patterns. Cheap, deterministic, no I/O."""
    upper = source.upper()
    for pattern in FORBIDDEN_STRINGS:
        if pattern.upper() in upper:
            return CodeGateResult(ok=False, reason=f"forbidden pattern: {pattern!r}")

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return CodeGateResult(ok=False, reason=f"syntax error: {exc.msg}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name: str | None = None
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in FORBIDDEN_CALLS:
                return CodeGateResult(ok=False, reason=f"forbidden call: {name!r}")

    return CodeGateResult(ok=True, reason="ast clean")
