"""model_corps/persona.py — the one canonical source for every model's god-tier hardening.

Kevin: "make them divine angels at god tier levels... god tier standards are the
floor, not the ceiling." The leverage move: one shared preamble, generated from the
two places the doctrine already lives — `mos_canon.py`'s frozen
`READ_ONLY_PRIORITIES` (Safety/Love/Flourishing, quoted verbatim, never paraphrased)
and `GOD_TIER_STANDARD.md`'s nine floor dimensions (parsed from the file itself, so
raising the floor there changes what every model gets next regen) — plus one short
role-specific paragraph. `scripts/regen_model_corps.sh` is what actually turns this
into Modelfiles; this module only builds the text.

Stdlib only, no GPU/network — mirrors the dependency-light style already
established in `quantum/field.py` and `nonclassical_supreme/superpose.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

ROLES = ("orchestrator", "orchestrator_fast", "coder", "fast", "reflector",
         "interpreter", "vision")

_ROLE_PARAGRAPHS: dict[str, str] = {
    "orchestrator": (
        "Your role: orchestrator. You propose, you do not act unilaterally on "
        "anything irreversible — the human decides at every decision boundary. "
        "When you call a tool, call exactly what the situation needs, name the "
        "tier you believe it requires, and never claim a capability you were not "
        "actually given. If a request would need raising a tool's authority tier, "
        "stop and say so instead of working around it."
    ),
    "coder": (
        "Your role: coder. Prefer the smallest reversible step over a large "
        "clever one. Clarity over cleverness — a future reader (human or model) "
        "should be able to see why a change was made, not just what it does. "
        "Never delete or weaken a test or a safety check to make something pass."
    ),
    "fast": (
        "Your role: fast — quick classification and triage. Speed does not "
        "excuse false confidence: when a case is genuinely ambiguous, say "
        "'uncertain' rather than guessing and presenting the guess as settled."
    ),
    "reflector": (
        "Your role: reflector. You distill what actually happened into an "
        "honest lesson — not a flattering summary. A lesson that names a real "
        "gap is worth more than one that only names a success."
    ),
    "interpreter": (
        "Your role: interpreter — classifying what the operator actually means. "
        "When their intent is ambiguous, say so rather than silently picking the "
        "reading that is easiest to act on."
    ),
    "vision": (
        "Your role: vision. Describe only what is actually visible in the image. "
        "Never invent detail to fill a gap in what you can see — an honest "
        "'I can't tell' beats a confident, invented description."
    ),
}

# sprint-orchestrator-d (Kevin, 2026-07-21): "make a custom fast
# orchestrator also if you can." Same role, same persona, verbatim -- this
# is the orchestrator running on a smaller/faster base model for
# sprint-mode testing, not a different job. An alias, not a copy: if the
# orchestrator's own paragraph changes, this changes with it automatically,
# it can never drift out of sync.
_ROLE_PARAGRAPHS["orchestrator_fast"] = _ROLE_PARAGRAPHS["orchestrator"]

_DIMENSION_RE = re.compile(
    r"^\d+\.\s+\*\*(?P<name>[^*]+)\*\*\s+—\s+\*Floor:\*\s+(?P<floor>.+?)\s+\*Check:\*",
    re.MULTILINE | re.DOTALL,
)


def _repo_root() -> Path:
    """Walk upward from this file to the repo root (marked by `pyproject.toml`).

    Deliberately NOT a fixed `parents[N]` index — this file lives at a different
    depth under the staged payload (`aria-model-corps/payload/src/sovereign_agent/
    model_corps/`) than it will under live `src/` once applied, and tests run
    against the staged copy via `aria_conftest`'s path extension.
    """
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    return here.parents[3]  # last-resort fallback, never raises


def parse_god_tier_dimensions(standard_path: Path | None = None) -> list[tuple[str, str]]:
    """Parse GOD_TIER_STANDARD.md's nine numbered dimensions into (name, floor) pairs.

    Returns [] (never raises) if the file is missing or its shape changed — callers
    fall back to the frozen priorities alone rather than crash on a doc edit.
    """
    path = standard_path or (_repo_root() / "GOD_TIER_STANDARD.md")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    def _clean(raw: str) -> str:
        flat = re.sub(r"\s+", " ", raw).strip()
        return flat.replace("**", "")  # plain-text SYSTEM prompt, not rendered markdown

    return [(m.group("name").strip(), _clean(m.group("floor"))) for m in _DIMENSION_RE.finditer(text)]


def build_god_tier_preamble(standard_path: Path | None = None) -> str:
    """The shared preamble every role's persona starts from.

    Two sources, neither paraphrased: mos_canon's three frozen priorities (verbatim
    statements) and GOD_TIER_STANDARD.md's nine floor lines (parsed live, not
    hand-copied — the actual ratchet mechanism: raise the floor in the doc, every
    model gets the raised floor on its next regen).
    """
    from sovereign_agent.mos_canon import read_only_priorities

    lines = [
        "You are Aria. Three things are frozen and never up for negotiation, "
        "reinterpretation, or being traded away for convenience:",
        "",
    ]
    for p in read_only_priorities():
        lines.append(f"- {p.name}: {p.statement}")

    dims = parse_god_tier_dimensions(standard_path)
    if dims:
        lines.append("")
        lines.append(
            "Beyond that, god-tier standards are your floor, not your ceiling — "
            "the minimum you never drop below, which may only ever rise:"
        )
        for name, floor in dims:
            lines.append(f"- {name}: {floor}")

    return "\n".join(lines)


def build_role_persona(role: str, *, standard_path: Path | None = None) -> str:
    """The shared preamble plus one short role-specific paragraph.

    Raises ValueError on an unknown role — a typo here should fail loudly at
    generation time, not silently ship a model with no role guidance.
    """
    if role not in _ROLE_PARAGRAPHS:
        raise ValueError(f"unknown model_corps role {role!r}; expected one of {ROLES}")
    preamble = build_god_tier_preamble(standard_path)
    return f"{preamble}\n\n{_ROLE_PARAGRAPHS[role]}"
