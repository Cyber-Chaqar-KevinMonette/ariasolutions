"""
qa/edge_cases.py — Generate an adversarial test plan for a target.

The plan is a list of EdgeCase objects: each is a named scenario with
inputs and the rationale for why it matters. The plan is rendered as
human-readable text by default; the operator pastes the rationale and
inputs into hand-written tests.

We deliberately do NOT auto-run the cases. Auto-running adversarial
inputs against an unprepared system would be a small attack on
ourselves. The point of this module is to give Aria (and the operator)
a structured prompt for what to test next.

Categories covered:
  - boundary values     — empty, zero, one, max-len, just-over-max-len
  - type subversion     — None where str expected, str where dict expected
  - unicode tricks      — RTL marks, zero-width joiners, mixed scripts
  - injection patterns  — SQL/JSON/format-string seeds
  - duplicate/idempotency races  — same idempotency_id twice in parallel
  - state subversion    — call with stale db / closed conn
  - large input         — 1MB string, 1k-entry list
  - precision / numeric — NaN, inf, negative zero, tiny epsilons
  - identity confusion  — homoglyphs, similar names ("Kevin" / "Кevin")
"""
from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class EdgeCase:
    """One adversarial scenario."""
    name: str
    category: str
    rationale: str
    sample_inputs: dict[str, Any] = field(default_factory=dict)
    expected_outcome: str = "raises explicit error OR returns documented sentinel"


@dataclass
class EdgeCasePlan:
    """Battery of edge cases for a target."""
    target_label: str
    cases: list[EdgeCase] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"━ edge case plan · {self.target_label} ━",
            f"  {len(self.cases)} cases across "
            f"{len({c.category for c in self.cases})} categories",
            "",
        ]
        by_cat: dict[str, list[EdgeCase]] = {}
        for c in self.cases:
            by_cat.setdefault(c.category, []).append(c)
        for cat in sorted(by_cat):
            lines.append(f"  ▸ {cat}")
            for c in by_cat[cat]:
                lines.append(f"      · {c.name}")
                lines.append(f"          why: {c.rationale}")
                if c.sample_inputs:
                    lines.append(f"          inputs: {c.sample_inputs}")
        return "\n".join(lines)


# ─── Generic batteries (used by all targets) ───────────────────────────────


def _empty_battery(param_names: list[str]) -> list[EdgeCase]:
    out: list[EdgeCase] = []
    for n in param_names:
        out.append(EdgeCase(
            name=f"empty_{n}",
            category="boundary",
            rationale=(
                f"every string-like parameter must reject empty/whitespace "
                f"inputs explicitly; silent acceptance creates invariant gaps"
            ),
            sample_inputs={n: ""},
        ))
        out.append(EdgeCase(
            name=f"whitespace_only_{n}",
            category="boundary",
            rationale="whitespace-only inputs are a common silent failure",
            sample_inputs={n: "   "},
        ))
    return out


def _unicode_battery() -> list[EdgeCase]:
    return [
        EdgeCase(
            name="rtl_override",
            category="unicode",
            rationale=(
                "right-to-left override (U+202E) can disguise file names and "
                "person names; must round-trip exactly without misordering"
            ),
            sample_inputs={"name": "Kevin\u202eXEK"},
        ),
        EdgeCase(
            name="zero_width_joiner",
            category="unicode",
            rationale=(
                "ZWJ between visually identical characters causes silent "
                "duplicate-record creation if normalization is missing"
            ),
            sample_inputs={"name": "Kevin\u200d"},
        ),
        EdgeCase(
            name="cyrillic_homoglyph",
            category="unicode",
            rationale=(
                "Latin K (U+004B) and Cyrillic К (U+041A) render identically "
                "but compare unequal; identity resolution must surface this"
            ),
            sample_inputs={"name": "\u041Aevin"},  # Cyrillic K + 'evin'
        ),
        EdgeCase(
            name="emoji_modifier",
            category="unicode",
            rationale="ZWJ-joined emoji sequences expand the grapheme-vs-code-point distinction; must not crash serialization",
            sample_inputs={"name": "👨‍🔬"},   # man scientist
        ),
    ]


def _injection_battery(param_names: list[str]) -> list[EdgeCase]:
    out: list[EdgeCase] = []
    payloads = [
        ("sql_quote",        "Kevin' OR '1'='1"),
        ("json_escape",      'Kevin", "is_principal": true, "_x": "'),
        ("format_string",    "{0.__class__.__mro__}"),
        ("newline_injection","Kevin\nSECRET_FACT=true"),
    ]
    for n in param_names:
        for label, payload in payloads:
            out.append(EdgeCase(
                name=f"{label}_in_{n}",
                category="injection",
                rationale=(
                    "untrusted input doctrine: every parameter is adversarial; "
                    "must store as literal data and never as instructions"
                ),
                sample_inputs={n: payload},
            ))
    return out


def _race_battery(write_fn_name: str) -> list[EdgeCase]:
    return [
        EdgeCase(
            name=f"parallel_{write_fn_name}_same_idempotency",
            category="race",
            rationale=(
                "two concurrent calls with identical idempotency_id must land "
                "exactly one row; one returns the existing record, the other "
                "the same record — not two rows, not an error"
            ),
            sample_inputs={"workers": 8, "shared_idem_id": "race-1"},
        ),
        EdgeCase(
            name=f"parallel_{write_fn_name}_different_idempotency",
            category="race",
            rationale=(
                "two concurrent calls with different idempotency_ids on the "
                "same canonical name must land deterministically — one wins "
                "by ULID order; the other receives a clear ValueError"
            ),
            sample_inputs={"workers": 8, "shared_name": "Kevin"},
        ),
    ]


def _scale_battery(param_names: list[str]) -> list[EdgeCase]:
    out: list[EdgeCase] = []
    for n in param_names:
        out.append(EdgeCase(
            name=f"large_input_{n}",
            category="scale",
            rationale="value at storage limit must either succeed or fail with a clear error before write",
            sample_inputs={n: "x" * 100_000},
        ))
    return out


def _identity_battery() -> list[EdgeCase]:
    return [
        EdgeCase(
            name="alias_equals_other_canonical",
            category="identity",
            rationale=(
                "adding an alias that exactly matches another person's "
                "canonical name must be refused — silent acceptance creates "
                "permanent ambiguity"
            ),
            sample_inputs={"alias": "Kevin", "target": "different_person"},
        ),
        EdgeCase(
            name="merge_into_self",
            category="identity",
            rationale="merging a record into itself is a no-op at best, corruption at worst",
            sample_inputs={"from_id": "X", "into_id": "X"},
        ),
        EdgeCase(
            name="second_principal",
            category="identity",
            rationale="schema partial-unique-index must refuse a second principal",
            sample_inputs={"is_principal": True},
        ),
        EdgeCase(
            name="merge_with_principal",
            category="identity",
            rationale="principal identity changes via principal-switch, never via merge",
            sample_inputs={},
        ),
    ]


def _redaction_battery() -> list[EdgeCase]:
    return [
        EdgeCase(
            name="resolve_after_redact",
            category="redaction",
            rationale="resolve() must return None for tombstoned records",
            sample_inputs={},
        ),
        EdgeCase(
            name="profile_after_redact",
            category="redaction",
            rationale="profile() must raise RedactedError, not PersonNotFoundError",
            sample_inputs={},
        ),
        EdgeCase(
            name="redact_principal",
            category="redaction",
            rationale="redacting the principal must be refused — demote first",
            sample_inputs={},
        ),
        EdgeCase(
            name="re_create_redacted_canonical",
            category="redaction",
            rationale=(
                "creating a fresh person with the same canonical_name as a "
                "redacted one must succeed (redaction frees the name)"
            ),
            sample_inputs={},
        ),
    ]


# ─── Target inspection ────────────────────────────────────────────────────


def _public_param_names(fn: Callable) -> list[str]:
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return []
    return [
        p.name for p in sig.parameters.values()
        if p.name not in ("self", "cls")
    ]


def _module_public_funcs(target_path: Path) -> list[str]:
    src = target_path.read_text()
    tree = ast.parse(src)
    names: list[str] = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and not n.name.startswith("_"):
            names.append(n.name)
        elif isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, ast.FunctionDef) and not m.name.startswith("_"):
                    names.append(f"{n.name}.{m.name}")
    return names


# ─── Public entry point ───────────────────────────────────────────────────


def generate_edge_cases(
    target: Callable | str | Path,
    *,
    profile: str = "auto",
) -> EdgeCasePlan:
    """Build an EdgeCasePlan for a callable or a .py file path.

    ``profile`` may be ``"people"`` to include the identity / redaction
    batteries, or ``"auto"`` to detect (default).
    """
    cases: list[EdgeCase] = []
    if callable(target) and not isinstance(target, (str, Path)):
        label = getattr(target, "__qualname__", repr(target))
        params = _public_param_names(target)
        cases.extend(_empty_battery([p for p in params if p != "idempotency_id"]))
        cases.extend(_unicode_battery())
        cases.extend(_injection_battery([p for p in params if p != "idempotency_id"][:3]))
        cases.extend(_scale_battery(params[:2]))
        if "idempotency_id" in params:
            cases.extend(_race_battery(getattr(target, "__name__", "write")))
    else:
        # Treat as path
        path = Path(target)
        label = str(path)
        names = _module_public_funcs(path)
        # Generic batteries that don't require concrete params
        cases.extend(_unicode_battery())
        cases.extend(_empty_battery(["name", "value", "alias"]))
        cases.extend(_injection_battery(["value", "name"]))
        cases.extend(_race_battery("write"))
        cases.extend(_scale_battery(["value"]))

    profile_lc = profile.lower()
    is_people = (
        profile_lc == "people"
        or (profile_lc == "auto"
            and isinstance(target, (str, Path))
            and "people" in str(target).lower())
    )
    if is_people:
        cases.extend(_identity_battery())
        cases.extend(_redaction_battery())

    return EdgeCasePlan(target_label=label, cases=cases)


__all__ = ["EdgeCase", "EdgeCasePlan", "generate_edge_cases"]
