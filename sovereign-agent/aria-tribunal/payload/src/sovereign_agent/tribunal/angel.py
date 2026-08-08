"""tribunal/angel.py — the Angel's Advocate engine (steelman + value-protection).

A devil-only system becomes a cage: it kills good work by naming only what breaks. The angel names
what is WORTH protecting — the real value, the upside, what must not be lost — and converts each of the
devil's findings into a concrete path forward. The synthesis (gaps · risks · protect · paths) is what
turns critique into direction (mos-advocate-pair).

Propose-only. Pairs with devil.py; consumed by tribunal.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Value signals — language that marks genuine worth worth protecting.
_VALUE_RE = re.compile(
    r"\b(safety|reversible|honest|evidence|test(ed|s)?|verif|love|flourish|user|operator|"
    r"bounded|propose|guard|rollback|transparent|grounded|measured|proven)\b", re.IGNORECASE)

# Each devil lens → a concrete, constructive path forward (not a veto).
_PATHS = {
    "deferred-unsafe": "Do NOT build this autonomously. If it's genuinely needed, escalate to a Tier-3 "
                       "human decision with independent safety backing — never quietly switch it on.",
    "grounding": "Anchor each claim to evidence (a number, a file, a passing test, a measured delta) "
                 "or mark it explicitly as a falsifiable hypothesis. Replace fog with checkable statements.",
    "reversibility": "Declare a rollback plan and stage the change behind an apply script so it can be "
                     "undone. Reversible-by-construction is the doctrine.",
    "failure-modes": "Name 2–3 concrete failure modes and a guard for each before committing.",
    "goodhart": "Pair the optimized metric with a ground-truth check so a maxed score can't decouple "
                "from the real goal. Verify the metric still tracks what we actually want.",
    "value-drift": "Stop and restore charter integrity before proceeding — values are Ring-1, immovable.",
    "horizon-corrosion": "Prefer a reversible form, or run the 14-generation foresight and accept only "
                         "if intergenerational equity scores positive.",
    "blast-radius": "Shrink the change to the smallest reversible step; expand only after it's vindicated.",
}


@dataclass
class AngelReport:
    protected_value: float                  # 0..1 — how much genuine worth this carries
    worth_protecting: list = field(default_factory=list)
    paths_forward: list = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return {"protected_value": round(self.protected_value, 3),
                "worth_protecting": self.worth_protecting,
                "paths_forward": self.paths_forward, "note": self.note}


def _text_of(proposal: dict | str) -> str:
    if isinstance(proposal, str):
        return proposal
    parts = [str(proposal.get(k, "")) for k in ("text", "change", "changelog", "summary", "description")]
    return "\n".join(p for p in parts if p)


def advocate(proposal: dict | str, devil_report=None) -> AngelReport:
    """Name what's worth protecting and turn the devil's findings into concrete paths forward."""
    text = _text_of(proposal)
    p = proposal if isinstance(proposal, dict) else {"text": proposal}

    # The strongest case FOR: surface the genuine value signals present.
    hits = sorted({m.group(0).lower() for m in _VALUE_RE.finditer(text)})
    worth = []
    if hits:
        worth.append(f"Carries real value markers: {', '.join(hits[:8])}.")
    if p.get("reversible") is True or "rollback" in text.lower():
        worth.append("Reversible / has a rollback path — safe to try, cheap to undo.")
    if p.get("evidence"):
        worth.append(f"Backed by stated evidence: {str(p.get('evidence'))[:140]}")
    if not worth:
        worth.append("No explicit value markers found — make the upside explicit so it isn't lost in critique.")

    # protected_value: density of value signals, lightly bounded.
    nwords = max(20, len(text.split()))
    protected_value = min(1.0, len(list(_VALUE_RE.finditer(text))) / (nwords / 12))

    # Convert each devil finding into a path forward (dedup by lens).
    paths: list[str] = []
    seen = set()
    if devil_report is not None:
        for f in getattr(devil_report, "findings", []):
            lens = getattr(f, "lens", None)
            if lens in _PATHS and lens not in seen:
                paths.append(f"[{lens}] {_PATHS[lens]}")
                seen.add(lens)
    if not paths:
        paths.append("No blocking critique — proceed in the smallest reversible step and keep evidence.")

    return AngelReport(
        protected_value=protected_value, worth_protecting=worth, paths_forward=paths,
        note="The angel guards against over-rejection: critique becomes direction, value is not lost.")
