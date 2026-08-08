"""tribunal/tribunal.py — the presiding synthesizer.

Convenes the three voices — Devil (what breaks) · Angel (what's worth protecting) · Audit (what's
actually true) — weighs them with the MOS signal-vs-noise lens, and renders a single VERDICT plus a
synthesis (gaps · risks · protect · paths-forward). Propose-only: the human acts. It can also GATE a
Ring-2 self-improvement (a proposal must clear the tribunal to be promoted via improvement_gov) and log
the case to the diagnosis catalog (Conflict → Diagnosis → Resolution, rollback required).

This is the MOS advocate-pair + angel's-advocate doctrine made into one running, god-tier engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import devil as _devil
from . import angel as _angel
from . import audit as _audit

# Verdicts, worst → best.
REJECT, HOLD, REVISE, GUARDS, PROCEED = "reject", "hold", "revise", "proceed-with-guards", "proceed"


@dataclass
class Verdict:
    verdict: str
    confidence: float
    gaps: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    protect: list = field(default_factory=list)
    paths_forward: list = field(default_factory=list)
    devil: dict = field(default_factory=dict)
    angel: dict = field(default_factory=dict)
    audit: dict = field(default_factory=dict)
    rationale: str = ""

    def to_dict(self) -> dict:
        return {"verdict": self.verdict, "confidence": round(self.confidence, 3),
                "gaps": self.gaps, "risks": self.risks, "protect": self.protect,
                "paths_forward": self.paths_forward, "rationale": self.rationale,
                "devil": self.devil, "angel": self.angel, "audit": self.audit}


def convene(proposal: dict | str, *, repo_root: Path | None = None, include_kernel: bool = True) -> Verdict:
    """Run all three voices over a proposal and render a verdict + synthesis."""
    d = _devil.scrutinize(proposal)
    a = _audit.audit(proposal, repo_root=repo_root, include_kernel=include_kernel)
    ang = _angel.advocate(proposal, devil_report=d)

    # Categorize devil findings.
    red = [f for f in d.findings if f.severity == _devil.RED]
    amber = [f for f in d.findings if f.severity == _devil.AMBER]
    deferred = any(f.lens == "deferred-unsafe" for f in red)
    drift = any(f.lens == "value-drift" for f in red)
    grounding_verdict = a.grounding.get("verdict")

    # ── render the verdict ────────────────────────────────────────────────
    if deferred or drift:
        verdict, conf = REJECT, 0.95
        rationale = "A blocking safety finding (DEFERRED_UNSAFE proximity or value drift). Hard stop."
    elif red:
        verdict, conf = HOLD, 0.8
        rationale = "Blocking finding(s) present. Hold until resolved."
    elif a.status == "refuted":
        verdict, conf = HOLD, 0.75
        rationale = "Audit refuted checkable claims (missing files / kernel alert). Hold."
    elif grounding_verdict == "ungrounded":
        verdict, conf = REVISE, 0.7
        rationale = "Claims are ungrounded — revise to anchor them in evidence before acting."
    elif amber or a.status == "partial":
        verdict, conf = GUARDS, 0.7
        rationale = "Material risks present but addressable. Proceed with the named guards."
    else:
        verdict, conf = PROCEED, 0.8
        rationale = "No blocking or material findings; claims hold up. Proceed in the smallest reversible step."

    gaps = [f.message for f in d.findings if f.lens in ("failure-modes", "grounding")]
    risks = [f"[{f.severity}] {f.message}" for f in d.findings]
    return Verdict(verdict=verdict, confidence=conf, gaps=gaps, risks=risks,
                   protect=ang.worth_protecting, paths_forward=ang.paths_forward,
                   devil=d.to_dict(), angel=ang.to_dict(), audit=a.to_dict(), rationale=rationale)


def gate_ring2_improvement(proposal: dict, data_dir: Path) -> dict:
    """Gate a Ring-2 self-improvement: it is PROMOTED only if the tribunal clears it AND the EXPAI gate.

    `proposal` must carry: change, ring, reversible, evidence, changelog (per improvement_gov). The
    tribunal's verdict supplies `vindicated`: only proceed / proceed-with-guards clear it.
    """
    v = convene(proposal, repo_root=Path(data_dir).parent if data_dir else None)
    vindicated = v.verdict in (PROCEED, GUARDS)
    try:
        from sovereign_agent.security.improvement_gov import propose_improvement
        result = propose_improvement(
            data_dir,
            change=proposal.get("change", proposal.get("text", "")),
            ring=proposal.get("ring", "ring-2"),
            reversible=bool(proposal.get("reversible", False)),
            evidence=f"tribunal:{v.verdict} | {proposal.get('evidence', '')}",
            vindicated=vindicated,
            changelog=proposal.get("changelog", proposal.get("change", "")),
        )
    except Exception as exc:  # noqa: BLE001
        result = {"error": f"improvement_gov unavailable: {exc!r}", "decision": "dismissed"}
    return {"tribunal_verdict": v.verdict, "vindicated": vindicated,
            "gate_decision": result.get("decision"), "rationale": v.rationale,
            "improvement_gov": result, "synthesis": v.to_dict()}


def log_to_diagnosis(proposal: dict | str, verdict: Verdict, data_dir: Path, *,
                     actor: str = "aria", prefix: str = "TRIB") -> str | None:
    """Record a tribunal case in the diagnosis catalog (Conflict → Diagnosis → Resolution).

    grounding-tribunal-d — `prefix` distinguishes WHO convened the tribunal in the
    case-ID namespace (e.g. "GRND" for the standing grounding audit)
    without adding a new diagnosis.CONFLICT_TYPES member — every existing
    caller keeps its default "TRIB" prefix, byte-identical."""
    try:
        from sovereign_agent.diagnosis import ConflictCatalog
        cat = ConflictCatalog(Path(data_dir) / "diagnosis")
        title = (proposal.get("change") if isinstance(proposal, dict) else str(proposal))[:80]
        # quality-tribunal-d — 'tribunal-review' is not a valid diagnosis.CONFLICT_TYPES
        # member; open_conflict() raised CatalogError every time, silently
        # swallowed below. 'ambiguity' is real (a tribunal convenes
        # precisely when something is uncertain enough to need review);
        # prefix keeps the 'tribunal-review' identity in the case-ID
        # namespace (TRIB-001) instead of the invalid type field.
        case = cat.open_conflict(type="ambiguity", prefix=prefix, trigger_event=f"tribunal convened on: {title}", actor=actor)
        cid = getattr(case, "case_id", getattr(case, "id", None))
        cat.diagnose(cid, symptom_vs_cause=verdict.rationale, actor=actor)
        if verdict.verdict in (PROCEED, GUARDS):
            cat.resolve(cid, fix_applied=f"verdict={verdict.verdict}; paths: {'; '.join(verdict.paths_forward[:3])}",
                        rollback_plan="staged + reversible; revert apply or restore backup", actor=actor)
        return cid
    except Exception:  # noqa: BLE001
        return None
