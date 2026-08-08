"""
╔══════════════════════════════════════════════════════════════════════════╗
║  horizon.py — Just-Horizon document generator                            ║
║  v0.2.14 · MOS canon §6.5                                                 ║
║                                                                           ║
║  A Horizon Scan is a forward projection: will this design still be the  ║
║  right one in 3 months? 12 months? 3 years? 7 generations? It is part   ║
║  of the MOS universal workflow loop, called after Angel's Advocate and  ║
║  before Transmit.                                                        ║
║                                                                           ║
║  This module renders a Horizon Scan as a markdown document, optionally  ║
║  saves it through the appendix system, and returns the rendered text   ║
║  for inclusion in CLI output or model prompts.                          ║
║                                                                           ║
║  THE FOUR HORIZONS                                                       ║
║                                                                           ║
║    3-month — what must be true for this to remain right?                 ║
║    12-month — emerging risks, protocol changes, capability shifts        ║
║    3-year — architectural bets; what becomes irreversible                ║
║    7th-generation — sovereignty, lock-in, flourishing trajectory         ║
║                                                                           ║
║  Aria emits these proactively at major decision points (dream start,    ║
║  project pivots, financial commitments) and the operator can request   ║
║  one any time via `sov horizon scan`.                                   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class HorizonInputs:
    """The decision under audit. Caller fills in what they know.

    Empty fields render as "(none specified)" in the output rather than
    crashing — Horizon Scans are scaffolds; they accept partial input.
    """
    label: str                              # short title for the scan
    decision: str                           # what is being decided
    three_month: str = ""                   # what must remain true
    twelve_month: str = ""                  # emerging risks
    three_year: str = ""                    # irreversibility points
    seventh_generation: str = ""            # sovereignty / flourishing
    emerging_signals: list[str] = field(default_factory=list)
    best_forward_path: str = ""             # the one thing to prioritize


def render(inputs: HorizonInputs) -> str:
    """Render a Horizon Scan as markdown.

    Output shape mirrors the MOS canon §6.5 template exactly, so the
    rendered doc is reusable in operator briefings, ADRs, and PR
    descriptions without translation.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# Horizon Scan — {inputs.label}",
        "",
        f"*Generated {now} by Aria-Sovereign-V1*",
        "",
        f"**Decision:** {inputs.decision}",
        "",
        "## 3-month",
        "",
        f"_What must be true for this to remain right?_",
        "",
        inputs.three_month or "(none specified)",
        "",
        "## 12-month",
        "",
        f"_Emerging risks, protocol changes, capability shifts._",
        "",
        inputs.twelve_month or "(none specified)",
        "",
        "## 3-year",
        "",
        f"_Architectural bets; what becomes irreversible._",
        "",
        inputs.three_year or "(none specified)",
        "",
        "## 7th-generation",
        "",
        f"_Sovereignty, lock-in, flourishing trajectory._",
        "",
        inputs.seventh_generation or "(none specified)",
        "",
        "## Emerging signals to watch",
        "",
    ]
    if inputs.emerging_signals:
        for sig in inputs.emerging_signals:
            lines.append(f"- {sig}")
    else:
        lines.append("(none yet identified)")
    lines.append("")
    lines.append("## ✓ Best forward path")
    lines.append("")
    lines.append(inputs.best_forward_path or "(decide before transmit)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Per MOS canon §6.5. Score ≤ −1 escalates; −2 rejects.*")
    return "\n".join(lines)


def save_through_appendix(
    conn,
    *,
    appendix_dir: Path,
    inputs: HorizonInputs,
    atom_id: str | None = None,
):
    """Generate a Horizon Scan and persist it through the appendix system.

    Returns the AppendixDoc record. Convenience wrapper combining
    `render()` with `appendix.write_doc()`.
    """
    from .appendix import write_doc
    body = render(inputs)
    return write_doc(
        conn, appendix_dir=appendix_dir,
        kind="horizon", title=f"Horizon: {inputs.label}",
        body=body, summary=inputs.decision,
        atom_id=atom_id, created_by="aria-horizon",
    )


# ─────────────────────────────────────────────────────────────────────────
# v0.2.29.0 — The Horizon Gate
# ─────────────────────────────────────────────────────────────────────────


# The four prompts used to fill in the four horizons. Kept compact and
# decision-focused — the gate's job is fast triage, not deep analysis.
# A model call per horizon is too expensive; one call returns the whole
# scan in a structured response.
_HORIZON_PROMPT_TEMPLATE = """\
A Tier-2+ subtask is about to dispatch. Before it runs, produce a brief
Horizon Scan answering each section in 1-3 sentences. Be concrete and
calibrated; mark assumptions explicitly.

Subtask: {decision}

Respond with EXACTLY this format (preserve the section markers):

[3M] <what must remain true in 3 months>
[12M] <emerging risks or capability shifts in 12 months>
[3Y] <architectural bets; what becomes irreversible>
[7G] <sovereignty, lock-in, flourishing trajectory at 7 generations>
[BEST] <the one thing to prioritize as the forward path>
"""


# Parsing the structured response. Order-independent; missing sections
# render as "(none specified)" in the final scan.
_SECTION_PATTERNS: dict[str, str] = {
    "three_month": r"^\s*\[3M\]\s*(?P<v>.+?)(?=\n\s*\[\w+\]|\Z)",
    "twelve_month": r"^\s*\[12M\]\s*(?P<v>.+?)(?=\n\s*\[\w+\]|\Z)",
    "three_year": r"^\s*\[3Y\]\s*(?P<v>.+?)(?=\n\s*\[\w+\]|\Z)",
    "seventh_generation": r"^\s*\[7G\]\s*(?P<v>.+?)(?=\n\s*\[\w+\]|\Z)",
    "best_forward_path": r"^\s*\[BEST\]\s*(?P<v>.+?)(?=\n\s*\[\w+\]|\Z)",
}


def parse_horizon_response(text: str) -> HorizonInputs:
    """Extract horizon fields from a model response.

    Robust to mild deviations: extra blank lines, missing sections, varied
    bracket spacing. Missing sections become empty strings (which render
    as "(none specified)" in `render()`).

    Exposed at module level so tests don't need to mock the model.
    """
    import re as _re

    extracted: dict[str, str] = {}
    for field_name, pattern in _SECTION_PATTERNS.items():
        m = _re.search(pattern, text, _re.MULTILINE | _re.DOTALL)
        if m:
            extracted[field_name] = m.group("v").strip()

    return HorizonInputs(
        label="",   # caller sets this
        decision="",  # caller sets this
        three_month=extracted.get("three_month", ""),
        twelve_month=extracted.get("twelve_month", ""),
        three_year=extracted.get("three_year", ""),
        seventh_generation=extracted.get("seventh_generation", ""),
        best_forward_path=extracted.get("best_forward_path", ""),
    )


async def generate_for_subtask(
    *,
    label: str,
    decision: str,
    client=None,
    model: str | None = None,
) -> HorizonInputs | None:
    """Generate a Horizon Scan for a Tier-2+ subtask via the fast model.

    Returns a fully-populated HorizonInputs on success, or None if the
    fast model is unreachable. Callers decide what to do with None —
    the gate's policy is the caller's choice, not this module's.

    Authority: Tier 0 — model call to read the fast model, no writes.
    """
    from .ollama_client import CallKind, OllamaClient
    from .config import SETTINGS

    client = client or OllamaClient()
    model = model or SETTINGS.fast_model

    prompt = _HORIZON_PROMPT_TEMPLATE.format(decision=decision)

    try:
        response = await client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            tools=None,
            call_kind=CallKind.PLAN,
        )
    except Exception:  # noqa: BLE001
        return None

    text = response.get("message", {}).get("content", "")
    if not text:
        return None

    inputs = parse_horizon_response(text)
    inputs.label = label
    inputs.decision = decision

    # If the model returned nothing useful (all sections empty), treat
    # it as a generation failure — the caller can then decide whether
    # to block or override.
    if not any([
        inputs.three_month,
        inputs.twelve_month,
        inputs.three_year,
        inputs.seventh_generation,
        inputs.best_forward_path,
    ]):
        return None

    return inputs


__all__ = [
    "HorizonInputs",
    "render",
    "save_through_appendix",
    "generate_for_subtask",
    "parse_horizon_response",
]
