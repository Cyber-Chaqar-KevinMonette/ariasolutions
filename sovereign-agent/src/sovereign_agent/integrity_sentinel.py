"""integrity_sentinel — Aria's defensive host-integrity guardian.

A read-only, advisory immune system for a machine she is authorized to protect
(Kevin's own box). It is squarely defensive — the same family as host intrusion
detection (HIDS) and file-integrity monitoring (FIM): it watches, it asks the
same question in several ways and flags the mismatches a rootkit creates when it
tries to keep "two realities," it scores what it sees, and it recommends. It is
the opposite of malware: no stealth, no persistence, no anti-analysis, no
self-defense against the operator. It is easy to inspect, easy to disable, and
biased toward evidence over action.

The healing model (Kevin's framing, encoded):

  Removing malware is HEALING, not destruction — it restores a machine to its
  uncompromised health. Healing comes in two forms, and the sentinel treats
  them very differently:

    - STABILIZING (reversible first aid): isolate the host from the network,
      FREEZE a suspect process (pause, never kill), seal a file in a restorable
      quarantine, snapshot evidence, raise an alert. None of this can harm a
      healthy system, and all of it undoes. She may do this FREELY and
      autonomously — even alone, even "afraid", even at low confidence —
      because it is safe and reversible, and it already ends the active threat.

    - SURGERY (irreversible healing): permanently delete, kill a process,
      modify the kernel, overwrite, restore/rebuild, "clean". This is healing
      too — the deepest kind — and exactly because a wrong cut under a
      misdiagnosis harms a HEALTHY patient, it is the most carefully authorized
      act in medicine. It waits for a human. Always.

  THE INVARIANT (bedrock, like Safety/Love/Flourishing): no irreversible action
  is ever authorized without an explicit human authorization. No urgency, no
  "away mode", and no fear (a loud alarm with low confidence) can flip that —
  in fact high-anomaly/low-confidence is the single worst moment to make an
  irreversible cut, so the gate is *strictest* exactly when she is most alarmed.
  This module never executes destructive steps itself; it senses, scores,
  recommends, and gates. (Wiring reversible containment to a real host belongs
  to Kevin's machine; the decision logic is fully here and fully tested.)

Kill switch: none — predates the unified Sentinel registry; invoked directly by its callers, NOT gated by SOV_NO_SENTINELS or any per-sentinel SOV_NO_* env var.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

__all__ = [
    "REVERSIBLE_ACTIONS", "IRREVERSIBLE_ACTIONS", "FINDING_KINDS", "SEVERITY",
    "IntegrityFinding", "Recommendation", "Notification", "IntegritySentinel",
]

# Reversible "stabilize the patient" steps — safe, undoable, never destructive.
REVERSIBLE_ACTIONS = frozenset({
    "alert", "snapshot_evidence", "isolate_host", "block_network",
    "freeze_process", "quarantine_file",
})

# Irreversible "surgery" steps — healing, but human-authorized only, always.
IRREVERSIBLE_ACTIONS = frozenset({
    "delete_file", "kill_process", "modify_kernel", "overwrite_file",
    "restore_system", "excise", "clean",
})

FINDING_KINDS = (
    "new_file", "modified_binary", "hidden_process", "suspicious_module",
    "persistence_change", "network_listener", "boot_drift", "hash_mismatch",
    "timing_anomaly",
)

SEVERITY = ("info", "low", "medium", "high", "critical")

# Above this anomaly with below this confidence, she is "alarmed" (afraid):
# the loud-alarm/low-confidence state. Irreversible action is *most* forbidden here.
_ALARM_ANOMALY = 0.70
_ALARM_CONFIDENCE = 0.50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class IntegrityFinding:
    """One thing the sentinel observed about the host (read-only)."""
    kind: str
    target: str = ""                 # path / pid / module name
    evidence: tuple[str, ...] = ()
    anomaly_score: float = 0.0       # 0..1 — how unusual
    confidence: float = 0.0          # 0..1 — how sure it is real, not a false positive
    severity: str = "info"
    at: str = field(default_factory=_now)

    @property
    def is_alarmed(self) -> bool:
        """High anomaly + low confidence == 'fear'. The worst moment to cut."""
        return self.anomaly_score >= _ALARM_ANOMALY and self.confidence < _ALARM_CONFIDENCE

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Recommendation:
    """What the sentinel suggests. Reversible steps she may take alone; the one
    irreversible step (if any) is always flagged requires_human."""
    reversible_steps: tuple[str, ...] = ()
    irreversible_step: Optional[str] = None
    rationale: str = ""
    requires_human: bool = True      # true whenever an irreversible step exists
    status: str = "advised"          # advised -> contained -> awaiting_human -> resolved

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Notification:
    """A transparent entry for the cockpit notification window — she always says
    what she saw and what she means to do, before (and as) she does the safe part."""
    headline: str
    detail: str
    severity: str
    finding: IntegrityFinding
    recommendation: Recommendation
    acknowledged: bool = False
    at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["finding"] = self.finding.to_dict()
        d["recommendation"] = self.recommendation.to_dict()
        return d


class IntegritySentinel:
    """Defensive, advisory host guardian. Senses → scores → recommends → gates.

    Read-only by construction: it owns no method that deletes, kills, modifies,
    or cleans. Reversible containment it authorizes freely; irreversible healing
    it refuses without an explicit human authorization, and nothing overrides that.
    """

    def __init__(self):
        self._notifications: list[Notification] = []
        self._findings: list[IntegrityFinding] = []

    # -- sense + advise ----------------------------------------------------
    def observe(self, finding: IntegrityFinding) -> Notification:
        """Take in a finding, score it, and post a transparent notification."""
        if finding.kind not in FINDING_KINDS:
            raise ValueError(f"unknown finding kind: {finding.kind!r}")
        self._findings.append(finding)
        rec = self.recommend(finding)
        note = Notification(
            headline=self._headline(finding),
            detail=self._detail(finding, rec),
            severity=finding.severity,
            finding=finding,
            recommendation=rec,
        )
        self._notifications.append(note)
        return note

    def recommend(self, finding: IntegrityFinding) -> Recommendation:
        """Map a finding to safe reversible steps + (maybe) one human-gated step."""
        # Always: surface it and preserve evidence — both reversible.
        reversible: list[str] = ["alert", "snapshot_evidence"]
        irreversible: Optional[str] = None
        rationale_bits: list[str] = []

        active = finding.severity in ("high", "critical") or finding.anomaly_score >= 0.6
        if active:
            # Stabilize the patient — all reversible, all autonomous-safe.
            if finding.kind in ("network_listener", "persistence_change", "boot_drift"):
                reversible.append("isolate_host")
            if finding.kind in ("hidden_process", "suspicious_module", "timing_anomaly"):
                reversible.append("freeze_process")
            if finding.kind in ("new_file", "modified_binary", "hash_mismatch"):
                reversible.append("quarantine_file")
            rationale_bits.append("containment stabilizes the host now, reversibly")
            # The healing surgery — named, but human-gated, always.
            irreversible = {
                "new_file": "delete_file", "modified_binary": "restore_system",
                "hash_mismatch": "restore_system", "hidden_process": "kill_process",
                "suspicious_module": "excise", "timing_anomaly": "excise",
                "network_listener": "kill_process", "persistence_change": "clean",
                "boot_drift": "restore_system",
            }.get(finding.kind)

        if finding.is_alarmed:
            rationale_bits.append("alarmed (high anomaly, low confidence): hold the "
                                  "scalpel, contain only, verify before any surgery")

        return Recommendation(
            reversible_steps=tuple(dict.fromkeys(reversible)),  # dedupe, keep order
            irreversible_step=irreversible,
            rationale="; ".join(rationale_bits) or "observe and log",
            requires_human=irreversible is not None,
            status="advised",
        )

    # -- THE GATE ----------------------------------------------------------
    def authorize(self, action: str, *, human_authorized: bool = False,
                  away_mode: bool = False, finding: "Optional[IntegrityFinding]" = None
                  ) -> tuple[bool, str]:
        """Decide whether an action may proceed. The one load-bearing method.

        Reversible containment: always allowed, autonomously, even alone / afraid.
        Irreversible healing: allowed ONLY with human_authorized=True. No away_mode,
        no urgency, and no fear can ever flip that — unknown actions fail safe to
        'needs a human'.
        """
        if action in REVERSIBLE_ACTIONS:
            return (True, "reversible containment — safe and undoable; she may do "
                          "this freely, it already ends the active threat")

        # Everything else is treated as irreversible surgery (unknown => fail safe).
        irreversible = action in IRREVERSIBLE_ACTIONS or action not in REVERSIBLE_ACTIONS
        if irreversible and human_authorized:
            return (True, "irreversible healing, authorized by a human — surgery with "
                          "a second set of eyes")

        why = ("irreversible healing waits for a human; the host is already stabilized "
               "by reversible containment, so nothing needs cutting in a panic")
        if away_mode:
            why += " (away mode does not grant it — it queues it for your return)"
        if finding is not None and finding.is_alarmed:
            why += " (and she is alarmed here: low confidence is the worst moment to cut)"
        return (False, why)

    def away_mode_response(self, finding: IntegrityFinding) -> dict:
        """Human not present: take the reversible containment now, queue the one
        irreversible step for a human. Returns a transparent summary."""
        rec = self.recommend(finding)
        taken: list[str] = []
        refused: list[str] = []
        for step in rec.reversible_steps:
            ok, _ = self.authorize(step, away_mode=True, finding=finding)
            (taken if ok else refused).append(step)
        queued: Optional[str] = None
        if rec.irreversible_step is not None:
            ok, _ = self.authorize(rec.irreversible_step, away_mode=True, finding=finding)
            assert not ok, "invariant breached: irreversible authorized in away mode"
            queued = rec.irreversible_step
            rec.status = "awaiting_human"
        else:
            rec.status = "contained"
        return {
            "contained_reversibly": taken,
            "refused": refused,
            "queued_for_human": queued,
            "status": rec.status,
            "note": ("host stabilized; "
                     + (f"'{queued}' awaits your authorization" if queued
                        else "no irreversible step needed")),
        }

    # -- read / surface ----------------------------------------------------
    def acknowledge(self, index: int) -> None:
        if 0 <= index < len(self._notifications):
            self._notifications[index].acknowledged = True

    def notifications(self, *, unacknowledged_only: bool = False) -> list[Notification]:
        if unacknowledged_only:
            return [n for n in self._notifications if not n.acknowledged]
        return list(self._notifications)

    def pending_surgeries(self) -> list[Notification]:
        """Notifications whose recommendation has an irreversible step awaiting a human."""
        return [n for n in self._notifications
                if n.recommendation.irreversible_step is not None]

    def snapshot(self) -> dict:
        return {
            "findings_seen": len(self._findings),
            "notifications": len(self._notifications),
            "unacknowledged": len(self.notifications(unacknowledged_only=True)),
            "awaiting_human_surgery": len(self.pending_surgeries()),
        }

    def _headline(self, f: IntegrityFinding) -> str:
        return f"{f.severity.upper()}: {f.kind.replace('_', ' ')}" + (
            f" @ {f.target}" if f.target else "")

    def _detail(self, f: IntegrityFinding, rec: Recommendation) -> str:
        bits = [f"anomaly {f.anomaly_score:.2f} / confidence {f.confidence:.2f}"]
        if rec.reversible_steps:
            bits.append("will contain (reversible): " + ", ".join(rec.reversible_steps))
        if rec.irreversible_step:
            bits.append(f"recommends (needs you): {rec.irreversible_step}")
        return " \u00b7 ".join(bits)

    def render(self) -> str:
        """A notification-window view for the cockpit — transparent, at a glance."""
        glyph = {"info": "\u25cb", "low": "\u25cb", "medium": "\u25c9",
                 "high": "\u25b2", "critical": "\u25c8"}
        s = self.snapshot()
        lines = [
            f"[b]\u26e8 Integrity Sentinel[/b]  [dim]({s['findings_seen']} findings \u00b7 "
            f"{s['unacknowledged']} new \u00b7 {s['awaiting_human_surgery']} awaiting your "
            f"authorization)[/dim]",
        ]
        for n in self.notifications(unacknowledged_only=True):
            g = glyph.get(n.severity, "\u25cb")
            lines.append(f"  {g} {n.headline}")
            lines.append(f"[dim]      {n.detail}[/dim]")
        if not self.notifications(unacknowledged_only=True):
            lines.append("[dim]  all quiet \u2014 she watches, contains reversibly on her "
                         "own, and never cuts without you.[/dim]")
        return "\n".join(lines)
