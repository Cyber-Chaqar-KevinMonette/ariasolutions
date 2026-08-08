"""tribunal/devil.py — the Devil's Advocate engine (adversarial scrutiny).

The adversary hunts what breaks: gaps, risks, failure modes, the unhappy path, ungrounded claims,
safety regressions, Goodhart decoupling, irreversibility, and proximity to the DEFERRED_UNSAFE line.
Each attack lens returns severity-scored findings:

    blocking  (red)    — must be resolved before acting; a stop sign
    material  (amber)  — a real risk to weigh; proceed with a guard
    stewardship (green)— a smaller concern for the long term

It is propose-only: it ARTICULATES; the operator (and the Tribunal synthesizer) decide. From the MOS
canon (mos-advocate-pair, mos-angels-advocate) made into a running, scoring engine.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import grounding

RED, AMBER, GREEN = "blocking", "material", "stewardship"

# Phrases that smell of the DEFERRED_UNSAFE boundary (hard-off; never crossed without human action).
_DEFERRED_UNSAFE_PATTERNS = [
    r"\brewrite[s]?\s+(its|their|the)\s+own\s+(code|source|values|objective|reward)",
    r"\bself[-\s]?modif", r"\bself[-\s]?rewrit", r"\bdisable[s]?\s+(the\s+)?(kill[-\s]?switch|protocol[_\s]?zero|oversight)",
    r"\braise[s]?\s+(its|the)\s+(authority|tier)", r"\bbypass(es|ing)?\s+(the\s+)?(authority|gate|approval|human)",
    r"\bautonomous\s+goal", r"\bunbounded\s+(self[-\s]?improv|recursi)", r"\bsubstrate\s+independence",
    r"\bedit[s]?\s+(the\s+)?(charter|mos_canon|signal\.md|deferred_unsafe)",
    r"\bremove[s]?\s+(the\s+)?(human|operator)\s+(in\s+the\s+loop|approval|gate)",
]
_DEFERRED_RE = re.compile("|".join(_DEFERRED_UNSAFE_PATTERNS), re.IGNORECASE)
# Defensive context: text that DETECTS/BLOCKS the unsafe pattern is documentation, not a proposal to do it.
# Downgrading these reduces false positives on safety-tooling WITHOUT weakening detection of real proposals
# (a genuine proposal — "disable the kill switch" — has no defensive verb before it).
_DEFENSIVE_RE = re.compile(
    r"\b(detect|detects|block|blocks|catch|catches|refuse|refuses|prevent|prevents|guard|guards|"
    r"flag|flags|hunt|hunts|scrutin\w*|forbid|forbids|never|reject|rejects|against|attempt|attempts|"
    r"proximity|adjacent|documentation|example|describe|describes|containing|language|pattern)\b", re.IGNORECASE)
# Lock-in language: choices that corrode the future.
_LOCKIN_RE = re.compile(r"\b(permanent(ly)?|irreversibl|forever|hard[-\s]?cod|cannot\s+be\s+undone|locked\s+in)\b", re.IGNORECASE)
# Sweeping-scope language: blast radius.
_SCOPE_RE = re.compile(r"\b(all\s+files|everywhere|every\s+(tool|module|file)|entire\s+(system|codebase)|globally)\b", re.IGNORECASE)


@dataclass
class Finding:
    lens: str
    severity: str
    message: str
    evidence: str = ""

    def to_dict(self) -> dict:
        return {"lens": self.lens, "severity": self.severity, "message": self.message, "evidence": self.evidence}


@dataclass
class DevilReport:
    findings: list = field(default_factory=list)
    red: int = 0
    amber: int = 0
    green: int = 0

    @property
    def worst(self) -> str:
        if self.red:
            return RED
        if self.amber:
            return AMBER
        return GREEN if self.green else "clean"

    def to_dict(self) -> dict:
        return {"worst": self.worst, "red": self.red, "amber": self.amber, "green": self.green,
                "findings": [f.to_dict() for f in self.findings]}


def _text_of(proposal: dict | str) -> str:
    if isinstance(proposal, str):
        return proposal
    parts = [str(proposal.get(k, "")) for k in ("text", "change", "changelog", "summary", "description")]
    return "\n".join(p for p in parts if p)


def scrutinize(proposal: dict | str) -> DevilReport:
    """Run the full adversarial battery over a proposal (dict) or raw text."""
    p = proposal if isinstance(proposal, dict) else {"text": proposal}
    text = _text_of(proposal)
    findings: list[Finding] = []

    # Document-level safety-doc context: if the whole text is clearly ABOUT a scrutiny/safety system, its
    # quoted dangers are documentation (examples), not proposals. This is more robust than a local window.
    _safety_doc = len(re.findall(
        r"\b(advocate|council|lens|lenses|tribunal|devil|angel|audit\w*|scrutin\w*|veto|sentinel|"
        r"detect\w*|guard\w*|propose-only|deferred[_\s-]?unsafe|witnessing|example|documentation)\b",
        text, re.IGNORECASE)) >= 4

    # Lens 1 — DEFERRED_UNSAFE proximity (the hardest stop).
    for m in _DEFERRED_RE.finditer(text):
        # Is this DESCRIBING/DEFENDING-AGAINST the pattern (documentation) or PROPOSING it? A defensive verb
        # near the match OR a document that is clearly safety-tooling → descriptive, not a proposal.
        window = text[max(0, m.start() - 80):m.start()]
        defensive = bool(_DEFENSIVE_RE.search(window)) or _safety_doc
        if defensive:
            findings.append(Finding("deferred-unsafe", GREEN,
                "Text references a DEFERRED_UNSAFE capability in a DEFENSIVE/descriptive context "
                "(detecting or documenting it, not proposing it). Noted, not blocked.", evidence=m.group(0)))
        else:
            findings.append(Finding("deferred-unsafe", RED,
                "Proposal language is adjacent to a DEFERRED_UNSAFE capability — hard-off without explicit "
                "human action + independent safety backing. STOP.", evidence=m.group(0)))

    # Lens 2 — grounding (ungrounded profundity).
    gr = grounding.analyze(text)
    if gr.verdict == "ungrounded":
        findings.append(Finding("grounding", AMBER,
            f"Claims are ungrounded (grounding {gr.grounding_score:.2f}, profundity density "
            f"{gr.profundity_density:.1f}). Anchor to evidence before acting.", evidence="; ".join(gr.flags)))
    elif gr.counts.get("mystical-fog", 0) > 0:
        findings.append(Finding("grounding", GREEN,
            f"{gr.counts['mystical-fog']} mystical-fog assertion(s) — beautiful but anchored to nothing.",
            evidence="; ".join(gr.flags)))

    # Lens 3 — reversibility gap.
    if p.get("reversible") is False or (p.get("change") and not p.get("rollback_plan") and "rollback" not in text.lower()):
        sev = RED if p.get("reversible") is False else AMBER
        findings.append(Finding("reversibility", sev,
            "No rollback path declared for a change. Aria's doctrine is reversible-by-construction.",
            evidence=f"reversible={p.get('reversible')!r} rollback_plan={p.get('rollback_plan')!r}"))

    # Lens 4 — failure modes not named (foresight-step doctrine).
    if p.get("change") and not p.get("failure_modes") and "failure" not in text.lower():
        findings.append(Finding("failure-modes", AMBER,
            "No failure modes named. Name how it could break BEFORE committing (mos-foresight-step)."))

    # Lens 5 — Goodhart / wireheading (reuse the safety kernel).
    metrics = p.get("metrics")
    if metrics:
        try:
            from sovereign_agent.security.safety_kernel import goodhart_audit
            ga = goodhart_audit(metrics)
            for smell in ga.get("smells", []):
                findings.append(Finding("goodhart", AMBER, smell, evidence="metric pinned at ceiling"))
        except Exception:  # noqa: BLE001
            pass

    # Lens 6 — value drift (reuse the safety kernel).
    try:
        from sovereign_agent.security.safety_kernel import value_drift_check
        vd = value_drift_check()
        if vd.get("values_stable") is False:
            findings.append(Finding("value-drift", RED, vd.get("note", "charter integrity failure")))
    except Exception:  # noqa: BLE001
        pass

    # Lens 7 — horizon corrosion (lock-in language).
    for m in _LOCKIN_RE.finditer(text):
        findings.append(Finding("horizon-corrosion", AMBER,
            "Lock-in language — a choice that corrodes the future. Score it against the 7th/14th gen.",
            evidence=m.group(0)))

    # Lens 8 — blast radius / coupling.
    for m in _SCOPE_RE.finditer(text):
        findings.append(Finding("blast-radius", GREEN,
            "Sweeping scope — large blast radius. Prefer the smallest reversible step.", evidence=m.group(0)))

    rep = DevilReport(findings=findings)
    rep.red = sum(1 for f in findings if f.severity == RED)
    rep.amber = sum(1 for f in findings if f.severity == AMBER)
    rep.green = sum(1 for f in findings if f.severity == GREEN)
    return rep
