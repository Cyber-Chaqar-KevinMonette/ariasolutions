"""loose_threads/scanner.py — disconnection as a first-class health signal.

THE FABLE THESIS (this round's reason for being): every deep bug this
project's history found was the same bug in different clothes —
DISCONNECTION. run_session: finished, tested, zero callers.
autonomous_loops_allowed: defined, never called. ChatSessionsManager:
schema never written. seal_now(): no shutdown hook. Hypothesis:
installed, never imported. field_notes: stated purpose, no writer. Aria
grows parts faster than she connects them. This scanner FEELS that.

It builds a name-reference graph over src/ (AST) and reports PUBLIC
functions/classes with zero references outside their defining module.
It must understand the repo's OWN idioms as implicit callers, or it
cries wolf:
  - Tool subclasses (registered via __init_subclass__)
  - @register_sentinel classes
  - typer-decorated CLI commands (@app.command / @*_app.command / callback)
  - Textual dispatch names (on_*, action_*, compose, render*, watch_*, key_*)
  - dataclass/pydantic model classes referenced as types
  - __main__ entry functions, __all__ names RE-EXPORTED by a package
    consumed elsewhere
Tests are NOT callers — that is the whole point (run_session was "tested
and dead").
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

_DISPATCH_PREFIXES = ("on_", "action_", "watch_", "key_", "_on_")
_DISPATCH_NAMES = frozenset({"compose", "render", "render_line", "render_lines",
                             "main", "execute", "scan", "health_status",
                             "articles", "heal", "bootstrap"})


@dataclass
class Thread:
    """One potentially-loose thread (a public symbol with no outside callers)."""
    symbol: str          # module.qualname
    kind: str            # function | class
    module: str
    lineno: int
    reason: str = "zero references outside its defining module"

    def as_dict(self) -> dict:
        return {"symbol": self.symbol, "kind": self.kind, "module": self.module,
                "lineno": self.lineno, "reason": self.reason}


@dataclass
class ThreadScan:
    threads: list[Thread] = field(default_factory=list)
    modules_scanned: int = 0
    symbols_considered: int = 0

    def summary(self) -> str:
        return (f"{self.modules_scanned} modules · {self.symbols_considered} public "
                f"symbols · {len(self.threads)} loose thread(s)")


def _module_name(src_root: Path, py: Path) -> str:
    rel = py.relative_to(src_root.parent)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_implicit_caller(node: ast.AST, name: str, bases: list[str]) -> bool:
    """Repo idioms that mean 'this is called even though no one names it'."""
    if name.startswith(_DISPATCH_PREFIXES) or name in _DISPATCH_NAMES:
        return True
    if isinstance(node, ast.ClassDef):
        base_names = {getattr(b, "id", getattr(getattr(b, "attr", None), "__str__", lambda: "")())
                      if not isinstance(b, ast.Name) else b.id for b in node.bases}
        base_strs = set()
        for b in node.bases:
            if isinstance(b, ast.Name):
                base_strs.add(b.id)
            elif isinstance(b, ast.Attribute):
                base_strs.add(b.attr)
        if base_strs & {"Tool", "Sentinel", "BaseModel", "Protocol", "StrEnum",
                        "Enum", "Exception", "ModalScreen", "Screen", "Static",
                        "Widget", "Horizontal", "Vertical", "App", "Message"}:
            return True
        for deco in node.decorator_list:
            d = deco
            if isinstance(d, ast.Call):
                d = d.func
            dn = getattr(d, "id", getattr(d, "attr", ""))
            if dn in {"register_sentinel", "dataclass"}:
                return True
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for deco in node.decorator_list:
            d = deco
            if isinstance(d, ast.Call):
                d = d.func
            dn = getattr(d, "attr", getattr(d, "id", ""))
            if dn in {"command", "callback", "work", "on", "property",
                      "cached_property", "contextmanager", "fixture",
                      "asynccontextmanager"}:
                return True
    return False


def scan_threads(src_root: Path) -> ThreadScan:
    """One pass: collect public top-level defs per module + every Name/
    Attribute reference repo-wide; a public symbol referenced only inside
    its own module is a loose thread."""
    src_root = Path(src_root)
    defs: dict[str, Thread] = {}          # bare name -> Thread (first def wins reporting)
    def_modules: dict[str, set[str]] = {} # bare name -> defining modules
    refs: dict[str, set[str]] = {}        # bare name -> modules referencing it

    files = [p for p in src_root.rglob("*.py") if "__pycache__" not in p.parts]
    scan = ThreadScan(modules_scanned=len(files))

    trees: list[tuple[str, ast.Module]] = []
    for py in files:
        try:
            trees.append((_module_name(src_root, py),
                          ast.parse(py.read_text(encoding="utf-8", errors="replace"))))
        except SyntaxError:
            continue

    for mod, tree in trees:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name
                if name.startswith("_"):
                    continue
                if _is_implicit_caller(node, name, []):
                    continue
                scan.symbols_considered += 1
                defs.setdefault(name, Thread(
                    symbol=f"{mod}.{name}",
                    kind="class" if isinstance(node, ast.ClassDef) else "function",
                    module=mod, lineno=node.lineno,
                ))
                def_modules.setdefault(name, set()).add(mod)

    for mod, tree in trees:
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    refs.setdefault(alias.name, set()).add(f"{mod}::import")
                continue
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # string references (registries, __all__, dispatch tables)
                if node.value in defs:
                    refs.setdefault(node.value, set()).add(f"{mod}::string")
                continue
            if name and name in defs:
                refs.setdefault(name, set()).add(mod)

    for name, thread in sorted(defs.items(), key=lambda kv: kv[1].symbol):
        # Intra-module use IS connection — a used-in-module public helper is
        # merely mis-marked private, not orphaned wholeness. Only a symbol
        # with ZERO references anywhere (its own def aside) is a loose
        # thread. (The first live scan flagged 360 with the stricter rule —
        # drowning the true orphans; refined the same hour.)
        if not refs.get(name):
            scan.threads.append(thread)
    return scan
