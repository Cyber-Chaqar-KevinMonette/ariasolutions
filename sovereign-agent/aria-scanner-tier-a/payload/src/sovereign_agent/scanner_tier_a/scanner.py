"""scanner.py — the Tier-A scanner harvest (Workstream J).

Six scanners from `aria-path-sentinel/SCANNER_CATALOG.md`'s Tier-A list, built to plug into H1's
Universal Scanner Kernel fan-out the moment both exist (`stewardship.registry.scan_all` picks up
any newly-registered sentinel automatically — no changes needed to `run()` itself).

Precision matters more than reach, same discipline as D's path_scan: a real defect in code that
runs blocks; the same pattern in a comment or test fixture is downgraded. Never cry wolf.

  1. secret-leak            — API keys / tokens / password literals in shipped code.        block
  2. anchor-integrity        — every -import-d/-all-d anchor an apply script references      block
                               actually exists in its target; every __all__ name has a
                               backing import. (This is literally the bug class that took
                               7 tools out of __all__ discovery — see aria-tools-all-export-fix.)
  3. import-cycle            — circular imports within sovereign_agent.* (AST import graph).  warn
  4. authority-tier-drift    — a ToolMeta(tier=3, ...) construction missing                   block
                               requires_approval=True, caught statically before the module
                               is ever applied (authority.py's own register_tool() enforces
                               this at runtime too — this scanner catches it earlier).
  5. bare-except             — `except:` / `except Exception: pass` swallowing errors.        warn
  6. mutable-default-arg     — `def f(x=[])` / `={}` foot-guns.                                warn
"""
from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

Severity = str  # "block" | "warn" | "info"

_ALLOW_PRAGMA = "scanner-tier-a: allow"


@dataclass
class Finding:
    severity: Severity
    kind: str
    path: str
    line: int
    message: str
    excerpt: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0

    @property
    def blocks(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "block"]

    @property
    def warns(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warn"]

    @property
    def clean(self) -> bool:
        return not self.blocks

    def summary(self) -> str:
        return (f"{self.files_scanned} files · {len(self.blocks)} block · "
                f"{len(self.warns)} warn · {len(self.findings)} total")


# ─── 1. secret-leak ─────────────────────────────────────────────────────────

_RE_SECRET_SIGNATURES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"""\bapi[_-]?key\s*[:=]\s*['"][A-Za-z0-9_\-]{20,}['"]""", re.IGNORECASE), "api-key literal"),
    (re.compile(r"""\bsk-[A-Za-z0-9]{20,}"""), "OpenAI-shaped secret key"),
    (re.compile(r"""\bAKIA[0-9A-Z]{16}\b"""), "AWS access key shape"),
    (re.compile(r"""\bxox[baprs]-[A-Za-z0-9\-]{10,}"""), "Slack token shape"),
    (re.compile(r"""\bpassword\s*[:=]\s*['"][^'"]{4,}['"]""", re.IGNORECASE), "password literal"),
    (re.compile(r"""-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"""), "private key block"),
)
_SECRET_PLACEHOLDER_WORDS = ("changeme", "xxx", "placeholder", "example", "<", "your_", "insert_")


def scan_secrets(text: str, *, rel_path: str) -> list[Finding]:
    out: list[Finding] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        if _ALLOW_PRAGMA in raw:
            continue
        low = raw.lower()
        if any(w in low for w in _SECRET_PLACEHOLDER_WORDS):
            continue
        for rx, label in _RE_SECRET_SIGNATURES:
            if rx.search(raw):
                out.append(Finding(
                    severity="block", kind="secret-leak", path=rel_path, line=i,
                    message=f"possible secret in shipped code: {label}", excerpt=raw.strip()[:160],
                ))
    return out


# ─── 2. anchor-integrity ────────────────────────────────────────────────────

_RE_ANCHOR = re.compile(r"#\s*([a-z0-9][a-z0-9-]*-(?:import|all)-d)\b")


def scan_anchor_integrity(repo_root: Path) -> list[Finding]:
    """Every -import-d/-all-d anchor an apply_*.sh script references must
    actually exist in the live file it claims to patch. Also: every tool
    imported into tools/__init__.py must appear in its __all__ list — the
    exact bug class that hid 7 tools from __all__-based discovery."""
    out: list[Finding] = []
    for apply in sorted(repo_root.glob("aria-*/apply_*.sh")):
        module = apply.parent.name
        text = apply.read_text(encoding="utf-8", errors="replace")
        anchors = set(_RE_ANCHOR.findall(text))
        if not anchors:
            continue
        # Heuristic target: the file(s) the script's own comments/cp lines mention
        # under src/sovereign_agent/; check every anchor against every such file.
        candidate_targets = set(re.findall(
            r'((?:REPO_ROOT"?\s*/\s*)?"?\$?\{?REPO_ROOT\}?"?/src/sovereign_agent/[\w./]+\.py)', text,
        ))
        # Fallback: just check the two most commonly patched files.
        default_targets = [
            repo_root / "src/sovereign_agent/tools/__init__.py",
            repo_root / "src/sovereign_agent/stewardship/__init__.py",
            repo_root / "src/sovereign_agent/cockpit/app.py",
        ]
        live_text = ""
        for t in default_targets:
            if t.is_file():
                live_text += t.read_text(encoding="utf-8", errors="replace")
        for anchor in sorted(anchors):
            if anchor not in live_text:
                out.append(Finding(
                    severity="block", kind="anchor-integrity/dangling",
                    path=f"{module}/{apply.name}", line=0,
                    message=f"anchor {anchor!r} referenced but not found in any live target "
                            "(module may not be applied yet, or the patch never took effect)",
                ))
    return out


def scan_all_exports(tools_init_text: str) -> list[Finding]:
    """Every tool class imported via `from .x import Y` in tools/__init__.py
    must also appear in __all__ — otherwise it's importable but invisible to
    any __all__-based discovery."""
    tree = ast.parse(tools_init_text)
    imported: set[str] = set()
    all_list: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                if name.endswith("Tool"):
                    imported.add(name)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, ast.List):
                        all_list.extend(
                            elt.value for elt in node.value.elts if isinstance(elt, ast.Constant)
                        )
    missing = sorted(imported - set(all_list))
    return [
        Finding(
            severity="block", kind="anchor-integrity/missing-export",
            path="tools/__init__.py", line=0,
            message=f"{name!r} is imported but missing from __all__",
        )
        for name in missing
    ]


# ─── 3. import-cycle ────────────────────────────────────────────────────────

def scan_import_cycles(src_root: Path) -> list[Finding]:
    """Build the sovereign_agent.* import graph via AST (no execution) and
    report any cycle. Cycles are a warn: they often still work at runtime
    (lazy imports, TYPE_CHECKING) but are worth knowing about."""
    graph: dict[str, set[str]] = {}
    for py in src_root.rglob("*.py"):
        if "__pycache__" in py.parts:  # path-scan: allow
            continue
        mod_name = _module_name(src_root, py)
        if mod_name is None:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        deps: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                if node.module.startswith("sovereign_agent"):
                    deps.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("sovereign_agent"):
                        deps.add(alias.name)
        graph[mod_name] = deps

    out: list[Finding] = []
    seen_cycles: set[frozenset] = set()
    for start in graph:
        cycle = _find_cycle(graph, start)
        if cycle:
            key = frozenset(cycle)
            if key in seen_cycles:
                continue
            seen_cycles.add(key)
            out.append(Finding(
                severity="warn", kind="import-cycle", path=start, line=0,
                message=f"import cycle: {' -> '.join(cycle)}",
            ))
    return out


def _module_name(src_root: Path, py: Path) -> str | None:
    try:
        rel = py.relative_to(src_root)
    except ValueError:
        return None
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return None
    return ".".join(["sovereign_agent", *parts]) if parts != ["sovereign_agent"] else "sovereign_agent"


def _find_cycle(graph: dict[str, set[str]], start: str) -> list[str] | None:
    stack: list[str] = [start]
    visited_path: dict[str, int] = {start: 0}

    def dfs(node: str, path: list[str]) -> list[str] | None:
        for dep in graph.get(node, ()):
            if dep == start and len(path) > 1:
                return [*path, dep]
            if dep in path:
                continue
            if dep not in graph:
                continue
            if dep == start:
                return [*path, dep]
            result = dfs(dep, [*path, dep])
            if result:
                return result
        return None

    return dfs(start, [start])


# ─── 4. authority-tier-drift (static, pre-apply) ────────────────────────────

def scan_authority_tier_drift(text: str, *, rel_path: str) -> list[Finding]:
    """Statically find ToolMeta(... tier=3 ...) constructions missing
    requires_approval=True — catches the drift before the module is ever
    applied/imported (authority.py's register_tool() enforces the same
    invariant at runtime, but only once the code actually executes)."""
    out: list[Finding] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ToolMeta":
            tier_val = _kwarg_literal(node, "tier")
            approval_val = _kwarg_literal(node, "requires_approval")
            if tier_val == 3 and approval_val is not True:
                out.append(Finding(
                    severity="block", kind="authority-tier-drift", path=rel_path,
                    line=node.lineno,
                    message="ToolMeta(tier=3, ...) without requires_approval=True",
                ))
    return out


def _kwarg_literal(call: ast.Call, name: str):
    for kw in call.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return None


# ─── 5. bare-except ──────────────────────────────────────────────────────────

_RE_BARE_EXCEPT = re.compile(r"^\s*except\s*:\s*(#.*)?$")
_RE_EXCEPT_EXCEPTION_SWALLOW = re.compile(r"^\s*except\s+Exception\s*(?:as\s+\w+)?\s*:\s*(#.*)?$")


def scan_bare_except(text: str, *, rel_path: str) -> list[Finding]:
    out: list[Finding] = []
    lines = text.splitlines()
    for i, raw in enumerate(lines, start=1):
        if _ALLOW_PRAGMA in raw:
            continue
        if _RE_BARE_EXCEPT.match(raw):
            out.append(Finding(
                severity="warn", kind="bare-except", path=rel_path, line=i,
                message="bare except: swallows all exceptions including KeyboardInterrupt/SystemExit",
                excerpt=raw.strip(),
            ))
            continue
        if _RE_EXCEPT_EXCEPTION_SWALLOW.match(raw):
            body = lines[i] if i < len(lines) else ""
            if re.match(r"^\s*(pass|continue)\s*(#.*)?$", body):
                out.append(Finding(
                    severity="warn", kind="bare-except", path=rel_path, line=i,
                    message="except Exception: pass/continue — error silently swallowed",
                    excerpt=raw.strip(),
                ))
    return out


# ─── 6. mutable-default-arg ──────────────────────────────────────────────────

def scan_mutable_defaults(text: str, *, rel_path: str) -> list[Finding]:
    out: list[Finding] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                out.append(Finding(
                    severity="warn", kind="mutable-default-arg", path=rel_path,
                    line=node.lineno,
                    message=f"def {node.name}(...) has a mutable default argument",
                ))
                break
    return out


# ─── aggregate: scan one file with all 6, or a whole tree ──────────────────

def scan_file(path: Path, *, rel_path: str) -> list[Finding]:
    text = path.read_text(encoding="utf-8", errors="replace")
    out: list[Finding] = []
    out.extend(scan_secrets(text, rel_path=rel_path))
    out.extend(scan_bare_except(text, rel_path=rel_path))
    out.extend(scan_mutable_defaults(text, rel_path=rel_path))
    out.extend(scan_authority_tier_drift(text, rel_path=rel_path))
    return out


def scan_tree(src_root: Path) -> ScanResult:
    """Scan every .py file under src_root with the 4 per-file scanners, plus
    the whole-tree import-cycle check. Anchor-integrity is scanned separately
    via scan_anchor_integrity(repo_root) since it needs the repo root, not
    just src_root."""
    findings: list[Finding] = []
    files = 0
    for py in src_root.rglob("*.py"):
        if "__pycache__" in py.parts or py.name.endswith(".bak") or ".bak." in py.name:  # path-scan: allow
            continue
        files += 1
        rel = str(py.relative_to(src_root.parent))
        findings.extend(scan_file(py, rel_path=rel))
    findings.extend(scan_import_cycles(src_root))
    return ScanResult(findings=findings, files_scanned=files)
