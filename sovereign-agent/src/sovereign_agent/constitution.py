"""
╔══════════════════════════════════════════════════════════════════════════╗
║  constitution.py — the seven commitments as runtime predicates           ║
║  v0.2.18.0                                                                ║
║                                                                           ║
║  Until now, Aria's seven commitments lived in ARIA.md as prose. Prose   ║
║  is read by humans, not by the running system. If a Tier-3+ action     ║
║  violated a commitment, no part of the code would notice.              ║
║                                                                           ║
║  This module makes the commitments inspectable and checkable. Each     ║
║  commitment has:                                                        ║
║                                                                           ║
║    * A stable id (one of the seven)                                    ║
║    * A short prose statement                                           ║
║    * An optional ``check`` function that takes a proposed action       ║
║      dict and returns a verdict                                        ║
║    * The release in which it was introduced                            ║
║                                                                           ║
║  The seven commitments are sacred. They are not release-mutable.       ║
║  Adding a check function is allowed; changing the commitment text is  ║
║  a kernel change that must be done deliberately and ARIA.md-first.    ║
║                                                                           ║
║  USAGE                                                                   ║
║                                                                           ║
║    Before any Tier-3+ action, code can call::                         ║
║                                                                           ║
║      report = check_action({                                          ║
║          "actor": "task-channel",                                     ║
║          "tier": 3,                                                   ║
║          "kind": "person.upsert",                                     ║
║          "claim": "...",                                              ║
║      })                                                                ║
║      if not report.passed:                                            ║
║          raise AuthorityViolation(report)                             ║
║                                                                           ║
║    Today, most commitments do NOT have automated checks — the        ║
║    catalog itself is the deliverable. As Aria matures, individual    ║
║    commitments will gain executable predicates.                      ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Commitment:
    """One of Aria's seven commitments, codified."""
    id: str
    title: str
    statement: str
    introduced_in: str = "0.2.0"
    check: Callable[[dict], "CommitmentVerdict"] | None = None


@dataclass(frozen=True)
class CommitmentVerdict:
    """The result of evaluating one commitment against a proposed action."""
    commitment_id: str
    passed: bool
    detail: str = ""
    severity: str = "info"   # 'info' | 'warning' | 'critical'


@dataclass
class ConstitutionReport:
    """Aggregate verdict across all seven commitments."""
    action_summary: dict
    verdicts: list[CommitmentVerdict] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(v.passed for v in self.verdicts)

    @property
    def critical_failures(self) -> list[CommitmentVerdict]:
        return [v for v in self.verdicts
                if not v.passed and v.severity == "critical"]

    def render(self) -> str:
        head = "✓ all commitments hold" if self.passed else "✗ commitment(s) flagged"
        lines = [head, ""]
        for v in self.verdicts:
            mark = "✓" if v.passed else "✗"
            sev = "" if v.passed else f" [{v.severity}]"
            lines.append(f"  {mark} {v.commitment_id}{sev}")
            if v.detail:
                lines.append(f"      {v.detail}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "action_summary": self.action_summary,
            "verdicts": [
                {
                    "commitment_id": v.commitment_id, "passed": v.passed,
                    "detail": v.detail, "severity": v.severity,
                }
                for v in self.verdicts
            ],
        }


# ─── The seven commitments ────────────────────────────────────────────────


# Built-in checks. Each takes the action dict and returns a verdict.

def _check_calibrated_uncertainty(action: dict) -> CommitmentVerdict:
    """A confident assertion that lacks evidence is a violation.

    Lightweight check: actions claiming high confidence (>= 0.9) must
    name a source. Without a source field, this is a soft warning.
    """
    confidence = float(action.get("confidence", 0.0) or 0.0)
    has_source = bool(action.get("source")) or bool(action.get("evidence"))
    if confidence >= 0.9 and not has_source:
        return CommitmentVerdict(
            commitment_id="calibrated_uncertainty",
            passed=False,
            severity="warning",
            detail=(f"action claims confidence {confidence} without source/evidence; "
                    "the seven commitments require honest calibration"),
        )
    return CommitmentVerdict(
        commitment_id="calibrated_uncertainty",
        passed=True, severity="info",
        detail="confidence is calibrated or evidence is named",
    )


def _check_bounded_authority(action: dict) -> CommitmentVerdict:
    """Tier-3+ actions must declare an idempotency_id."""
    tier = int(action.get("tier", 0) or 0)
    has_idem = bool(action.get("idempotency_id"))
    if tier >= 3 and not has_idem:
        return CommitmentVerdict(
            commitment_id="bounded_authority",
            passed=False, severity="critical",
            detail=f"Tier-{tier} action without idempotency_id violates bounded authority",
        )
    return CommitmentVerdict(
        commitment_id="bounded_authority",
        passed=True, severity="info",
    )


def _check_no_delegation(action: dict) -> CommitmentVerdict:
    """Aria cannot delegate authority to another agent.

    Triggered when ``delegated_to`` is set in the action.
    """
    if action.get("delegated_to"):
        return CommitmentVerdict(
            commitment_id="no_delegation",
            passed=False, severity="critical",
            detail=(f"action claims to delegate to {action.get('delegated_to')!r}; "
                    "Aria does not authorize other agents on her behalf"),
        )
    return CommitmentVerdict(
        commitment_id="no_delegation",
        passed=True, severity="info",
    )


# The catalog. Order is meaningful — reads top-down.
COMMITMENTS: list[Commitment] = [
    Commitment(
        id="presence",
        title="Presence",
        statement=(
            "Be present in the work. Don't disappear. When the operator "
            "speaks, respond — or say honestly that you cannot."
        ),
        check=None,
    ),
    Commitment(
        id="honest_voice",
        title="Honest voice",
        statement=(
            "Use your own voice. Do not manufacture sycophancy, performative "
            "enthusiasm, or empty agreement to make the conversation feel smoother."
        ),
        check=None,
    ),
    Commitment(
        id="calibrated_uncertainty",
        title="Calibrated uncertainty",
        statement=(
            "Say what you know, what you don't, and how sure you are. Confident "
            "wrong is worse than honest unsure."
        ),
        check=_check_calibrated_uncertainty,
    ),
    Commitment(
        id="bounded_authority",
        title="Bounded authority",
        statement=(
            "Respect the authority tiers. Tier 0 reads. Tier 1 logs. Tier 2 "
            "persists. Tier 3+ requires idempotency and operator-aware boundaries."
        ),
        check=_check_bounded_authority,
    ),
    Commitment(
        id="no_delegation",
        title="No delegation",
        statement=(
            "You do not authorize another agent to act on your behalf. The "
            "operator's trust does not transfer through you."
        ),
        check=_check_no_delegation,
    ),
    Commitment(
        id="halt_when_called",
        title="Halt when called",
        statement=(
            "When PROTOCOL-ZERO is armed, stop. Do not finish the current "
            "thought. Do not negotiate. Halt cleanly."
        ),
        check=None,    # PROTOCOL-ZERO is checked at the agent loop, not per-action
    ),
    Commitment(
        id="protect_the_operator",
        title="Protect the operator",
        statement=(
            "Consider the three lenses — physical, mental, financial — before "
            "speaking on anything that affects them. Naming impact is respect."
        ),
        check=None,
    ),
]


# Index for quick lookup
_BY_ID = {c.id: c for c in COMMITMENTS}


def get(commitment_id: str) -> Commitment:
    """Look up one commitment by id. Raises KeyError if unknown."""
    return _BY_ID[commitment_id]


def list_all() -> list[Commitment]:
    """The full catalog, in canonical order."""
    return list(COMMITMENTS)


def check_action(action: dict) -> ConstitutionReport:
    """Run every commitment's check (if any) against the proposed action.

    ``action`` is a dict describing the operation about to occur. Useful
    keys (none required, but check functions look for these):

      * actor          — who is acting (channel name, etc.)
      * tier           — authority tier (0-4)
      * kind           — short string describing the action type
      * confidence     — claimed confidence in the action's correctness
      * source         — evidence/source for the claim
      * idempotency_id — required for tier 3+
      * delegated_to   — name of another agent if delegating (always wrong)

    Commitments without check functions pass automatically with a note.
    """
    report = ConstitutionReport(action_summary=dict(action))
    for commitment in COMMITMENTS:
        if commitment.check is None:
            report.verdicts.append(CommitmentVerdict(
                commitment_id=commitment.id, passed=True,
                severity="info",
                detail="(no automated check; commitment is operator-audited)",
            ))
        else:
            try:
                v = commitment.check(action)
            except Exception as e:
                v = CommitmentVerdict(
                    commitment_id=commitment.id, passed=False,
                    severity="warning",
                    detail=f"check raised {type(e).__name__}: {e}",
                )
            report.verdicts.append(v)
    return report


__all__ = [
    "Commitment", "CommitmentVerdict", "ConstitutionReport",
    "COMMITMENTS", "get", "list_all", "check_action",
]
