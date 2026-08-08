"""
qa/hardening.py — Apply a MOS-aligned hardening checklist to a module.

This is not a static analyzer in the linter sense. It's a structured
checklist scored against the AST of one Python module plus shallow
project context (does this module have a matching test file? do its
public functions accept idempotency_id? is BEGIN IMMEDIATE used for
write paths?).

Each check is one named, document-able criterion. The output is a
HardeningReport that lists which checks passed and which failed,
together with a per-check weight so the operator can see what mattered
most.

The categories follow MOS doctrine:
  - validates_inputs     — does the code reject malformed input early?
  - bounded_authority    — does it declare a tier? (channels only)
  - idempotency_present  — Tier 3+ writes accept idempotency_id?
  - observability        — does it emit events / log decisions?
  - rollback_path        — for stateful changes, is there an inverse op?
  - error_taxonomy       — does it raise specific exceptions, not bare?
  - has_tests            — is there a test file targeting this module?
  - typed_signatures     — do public functions carry type hints?
  - no_bare_except       — no naked ``except:`` clauses?
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class HardeningCheck:
    """One named criterion in the checklist."""
    key: str
    label: str
    passed: bool
    weight: int                          # 1-10; higher = more critical
    detail: str = ""


@dataclass
class HardeningReport:
    """Result of harden_module(). ``ok`` iff every weight-≥8 check passed."""
    target_module: str
    checks: list[HardeningCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks if c.weight >= 8)

    @property
    def weighted_score(self) -> float:
        """Sum of passed weights / sum of all weights, in [0,1]."""
        total = sum(c.weight for c in self.checks)
        if total == 0:
            return 0.0
        return sum(c.weight for c in self.checks if c.passed) / total

    def failures(self) -> list[HardeningCheck]:
        return [c for c in self.checks if not c.passed]

    def render(self) -> str:
        status = "✓" if self.ok else "✗"
        lines = [
            f"{status} hardening · {self.target_module}",
            f"  weighted score: {self.weighted_score * 100:.1f}%",
            "",
        ]
        for c in self.checks:
            mark = "✓" if c.passed else "✗"
            color_hint = "" if c.passed else f"  (weight {c.weight})"
            lines.append(f"  {mark} {c.label}{color_hint}")
            if c.detail:
                lines.append(f"      {c.detail}")
        return "\n".join(lines)


# ─── AST helpers ───────────────────────────────────────────────────────────


def _public_funcs(tree: ast.Module) -> list[ast.FunctionDef]:
    """Top-level public functions (no leading underscore)."""
    return [
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")
    ]


def _public_methods(tree: ast.Module) -> list[ast.FunctionDef]:
    """Public methods on any top-level class."""
    out: list[ast.FunctionDef] = []
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, ast.FunctionDef) and not m.name.startswith("_"):
                    out.append(m)
    return out


def _source(tree: ast.Module, source: str) -> str:
    return source


def _has_substring_anywhere(source: str, needle: str) -> bool:
    return needle in source


# ─── Individual checks ─────────────────────────────────────────────────────


def _check_validates_inputs(tree: ast.Module, source: str) -> HardeningCheck:
    """Heuristic: any public function with parameters should ``raise ValueError``
    or check arguments somewhere. We accept either explicit raises in the
    function or guard-style ``if ... raise`` patterns."""
    funcs = _public_funcs(tree) + _public_methods(tree)
    funcs_with_args = [f for f in funcs if len(f.args.args) > 1]   # >1 to skip self-only
    if not funcs_with_args:
        return HardeningCheck(
            key="validates_inputs", label="validates inputs (no public functions with args to check)",
            passed=True, weight=8,
        )
    bad: list[str] = []
    for f in funcs_with_args:
        body_src = ast.unparse(f) if hasattr(ast, "unparse") else ""
        if "raise " not in body_src and "ValueError" not in body_src and "assert " not in body_src:
            bad.append(f.name)
    if bad:
        return HardeningCheck(
            key="validates_inputs", label="validates inputs",
            passed=False, weight=8,
            detail=f"functions without visible validation: {', '.join(bad[:5])}",
        )
    return HardeningCheck(
        key="validates_inputs", label="validates inputs",
        passed=True, weight=8,
    )


def _check_bounded_authority(tree: ast.Module, source: str) -> HardeningCheck:
    """Channels declare a ChannelSpec with an authority_tier. Non-channel
    files don't need this — so we only require it if the file references
    ``ChannelSpec``."""
    if "ChannelSpec" not in source:
        return HardeningCheck(
            key="bounded_authority", label="bounded authority (n/a — not a channel)",
            passed=True, weight=5,
        )
    has_tier = "authority_tier" in source
    return HardeningCheck(
        key="bounded_authority", label="declares authority_tier on ChannelSpec",
        passed=has_tier, weight=9,
        detail="" if has_tier else "channel module missing authority_tier",
    )


def _check_idempotency(tree: ast.Module, source: str) -> HardeningCheck:
    """If the module is a tier-3 channel, public write methods must accept
    idempotency_id. We approximate 'tier 3' by looking for the literal."""
    is_tier3 = "authority_tier=3" in source or "authority_tier = 3" in source
    if not is_tier3:
        return HardeningCheck(
            key="idempotency_present", label="idempotency (n/a — not Tier 3+)",
            passed=True, weight=4,
        )
    methods = _public_methods(tree)
    write_like = [
        m for m in methods
        if any(kw in m.name.lower() for kw in (
            "record", "add", "upsert", "merge", "split", "redact",
            "register", "create", "set",
        ))
    ]
    if not write_like:
        return HardeningCheck(
            key="idempotency_present",
            label="idempotency on Tier 3 writes (no write-like methods detected)",
            passed=True, weight=8,
        )
    bad = []
    for m in write_like:
        arg_names = {a.arg for a in m.args.args} | {a.arg for a in m.args.kwonlyargs}
        if "idempotency_id" not in arg_names:
            bad.append(m.name)
    if bad:
        return HardeningCheck(
            key="idempotency_present", label="idempotency on Tier 3 writes",
            passed=False, weight=9,
            detail=f"methods missing idempotency_id: {', '.join(bad)}",
        )
    return HardeningCheck(
        key="idempotency_present", label="idempotency on Tier 3 writes",
        passed=True, weight=9,
    )


def _check_observability(tree: ast.Module, source: str) -> HardeningCheck:
    """Module either emits an event or routes its writes through MemoryChannel
    (whose base class emits)."""
    has_event = "emit_event" in source or "MemoryChannel" in source
    return HardeningCheck(
        key="observability",
        label="observability (emits events or extends MemoryChannel)",
        passed=has_event, weight=8,
        detail="" if has_event else "no event emission or MemoryChannel base detected",
    )


def _check_rollback(tree: ast.Module, source: str) -> HardeningCheck:
    """Stateful mutators should have a documented inverse — merge ↔ split,
    add ↔ remove, set ↔ unset, redact ↔ restore. Heuristic: pair detection."""
    methods = _public_methods(tree)
    names = {m.name for m in methods}
    pairs = [
        ({"merge", "split"}, "merge / split"),
        ({"redact", "restore"}, "redact / restore"),
        ({"add_alias", "remove_alias"}, "add_alias / remove_alias"),
        ({"confirm_fact", "retract_fact"}, "confirm / retract"),
    ]
    is_state_module = any(
        "write_atom" in source or m.name.startswith(("record", "add", "upsert", "set"))
        for m in methods
    )
    if not is_state_module:
        return HardeningCheck(
            key="rollback_path", label="rollback path (n/a — non-stateful module)",
            passed=True, weight=5,
        )
    found_pairs = [
        label for needed, label in pairs if needed.issubset(names)
    ]
    # At least one rollback pair OR redaction tombstone present
    has_redact = "redact" in names or "tombstone" in source.lower()
    passed = bool(found_pairs) or has_redact
    detail = (
        f"pairs found: {', '.join(found_pairs)}" if found_pairs
        else ("redaction tombstone present" if has_redact else "no inverse operation detected")
    )
    return HardeningCheck(
        key="rollback_path", label="rollback path",
        passed=passed, weight=8, detail=detail,
    )


def _check_error_taxonomy(tree: ast.Module, source: str) -> HardeningCheck:
    """Are exceptions specific, not bare ``raise Exception(...)``?"""
    bare_raises = 0
    typed_raises = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc:
            if isinstance(node.exc, ast.Call):
                fname = getattr(node.exc.func, "id", None) or \
                        getattr(node.exc.func, "attr", None)
                if fname in ("Exception", "BaseException"):
                    bare_raises += 1
                else:
                    typed_raises += 1
    if bare_raises > 0:
        return HardeningCheck(
            key="error_taxonomy", label="error taxonomy (typed exceptions, not bare Exception)",
            passed=False, weight=6,
            detail=f"{bare_raises} bare Exception/BaseException raise(s) found",
        )
    return HardeningCheck(
        key="error_taxonomy", label="error taxonomy",
        passed=True, weight=6,
        detail=f"{typed_raises} typed raise(s)",
    )


def _check_has_tests(tree: ast.Module, source: str, *, target_path: Path,
                    repo_root: Path) -> HardeningCheck:
    """Is there a test file that references this module?"""
    mod_name = target_path.stem
    tests_dir = repo_root / "tests"
    if not tests_dir.is_dir():
        return HardeningCheck(
            key="has_tests", label="has tests (no tests/ dir found)",
            passed=False, weight=9,
        )
    needle = mod_name
    for p in tests_dir.glob("test_*.py"):
        try:
            txt = p.read_text(errors="ignore")
        except OSError:
            continue
        if needle in txt:
            return HardeningCheck(
                key="has_tests", label="has tests",
                passed=True, weight=9,
                detail=f"referenced in {p.name}",
            )
    return HardeningCheck(
        key="has_tests", label="has tests",
        passed=False, weight=9,
        detail=f"no test file references module {needle!r}",
    )


def _check_typed_signatures(tree: ast.Module, source: str) -> HardeningCheck:
    """Public functions / methods carry type hints?"""
    funcs = _public_funcs(tree) + _public_methods(tree)
    if not funcs:
        return HardeningCheck(
            key="typed_signatures", label="typed signatures (no public functions)",
            passed=True, weight=4,
        )
    untyped: list[str] = []
    for f in funcs:
        # Skip 'self'/'cls'
        params = [a for a in f.args.args if a.arg not in ("self", "cls")]
        params += list(f.args.kwonlyargs)
        for p in params:
            if p.annotation is None:
                untyped.append(f"{f.name}/{p.arg}")
                break
    if untyped:
        return HardeningCheck(
            key="typed_signatures", label="typed signatures",
            passed=False, weight=4,
            detail=f"{len(untyped)} param(s) lack annotations: {', '.join(untyped[:4])}",
        )
    return HardeningCheck(
        key="typed_signatures", label="typed signatures",
        passed=True, weight=4,
    )


def _check_no_bare_except(tree: ast.Module, source: str) -> HardeningCheck:
    bare = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                bare += 1
    if bare > 0:
        return HardeningCheck(
            key="no_bare_except", label="no bare except clauses",
            passed=False, weight=5,
            detail=f"{bare} bare except(s)",
        )
    return HardeningCheck(
        key="no_bare_except", label="no bare except clauses",
        passed=True, weight=5,
    )


# ─── Public entry point ───────────────────────────────────────────────────


def harden_module(target_path: str | Path, *,
                  repo_root: str | Path | None = None) -> HardeningReport:
    """Run the full hardening checklist on ``target_path``.

    ``target_path`` must be an existing .py file. ``repo_root`` defaults
    to the nearest ancestor containing pyproject.toml.
    """
    p = Path(target_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(p)
    if p.suffix != ".py":
        raise ValueError(f"target must be a .py file: {p}")

    if repo_root is None:
        # walk up looking for pyproject.toml
        cur = p.parent
        for _ in range(8):
            if (cur / "pyproject.toml").is_file():
                repo_root = cur
                break
            cur = cur.parent
        else:
            repo_root = p.parent
    repo_root = Path(repo_root)

    source = p.read_text()
    tree = ast.parse(source, filename=str(p))

    checks = [
        _check_validates_inputs(tree, source),
        _check_bounded_authority(tree, source),
        _check_idempotency(tree, source),
        _check_observability(tree, source),
        _check_rollback(tree, source),
        _check_error_taxonomy(tree, source),
        _check_has_tests(tree, source, target_path=p, repo_root=repo_root),
        _check_typed_signatures(tree, source),
        _check_no_bare_except(tree, source),
    ]
    return HardeningReport(target_module=str(p), checks=checks)


__all__ = ["HardeningCheck", "HardeningReport", "harden_module"]
