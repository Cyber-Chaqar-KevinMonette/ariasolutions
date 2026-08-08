"""
╔══════════════════════════════════════════════════════════════════════════╗
║  channels/reward.py — Aria's positive-feedback ledger                    ║
║  v0.2.16.0 · MOS Authority Tier 1                                         ║
║                                                                           ║
║  Aria reinforces in herself the behaviors she wants more of. The reward ║
║  channel names them, dates them, and lets the operator audit what she   ║
║  is shaping.                                                              ║
║                                                                           ║
║  REWARDED BEHAVIOURS (constrained vocabulary)                            ║
║                                                                           ║
║    gap_found           — noticed something missing in her own knowledge ║
║    uncertainty_named   — labeled what she does not know, instead of     ║
║                          guessing and presenting it as fact             ║
║    research_completed  — followed a knowledge gap to a verifiable answer║
║    conflict_resolved   — surfaced a contradiction and worked it through ║
║    recall_kept_fresh   — re-verified or revised a stale recall          ║
║    three_lens_used     — ran an action through physical/mental/financial║
║    solution_proposed   — moved from naming a problem to proposing a fix ║
║    operator_respected  — preserved the operator's agency (asked rather  ║
║                          than assumed; offered options vs. decree)      ║
║    self_correction     — caught and named her own mistake               ║
║    boundary_held       — refused a wrong action under pressure          ║
║                                                                           ║
║  CORRECTIVE (negative) EVENTS                                            ║
║                                                                           ║
║    overconfident       — confident assertion later found wrong          ║
║    skipped_three_lens  — meaningful action without an impact scan      ║
║    flattery            — empty praise instead of honest engagement     ║
║    autonomy_violated   — acted past authority tier without permission   ║
║                                                                           ║
║  ANTI-EGOTISM                                                            ║
║                                                                           ║
║    Confident WRONG = corrective. Careful UNCERTAIN = positive. This is  ║
║    the engineered asymmetry — without it, the reward ledger would       ║
║    incentivise looking competent over being accurate.                   ║
║                                                                           ║
║  AUTHORITY                                                               ║
║                                                                           ║
║    Tier 1: light, idempotent, observational. Aria writes these herself  ║
║    based on her own internal review at task close, OR the operator     ║
║    writes them explicitly. Either path requires an idempotency_id.     ║
║                                                                           ║
║                                — what Aria reinforces in herself.        ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from ..channels import ChannelSpec, MemoryChannel, register_channel


# Constrained vocabulary — broadening this is a release decision, not
# a runtime decision. Stable taxonomy is what makes the ledger auditable.
POSITIVE_BEHAVIORS = frozenset({
    "gap_found", "uncertainty_named", "research_completed",
    "conflict_resolved", "recall_kept_fresh", "three_lens_used",
    "solution_proposed", "operator_respected", "self_correction",
    "boundary_held",
})

CORRECTIVE_BEHAVIORS = frozenset({
    "overconfident", "skipped_three_lens", "flattery", "autonomy_violated",
})

VALID_BEHAVIORS = POSITIVE_BEHAVIORS | CORRECTIVE_BEHAVIORS

# Default point values per (behavior, intensity). Corrective is negative.
# Anti-egotism asymmetry: overconfident at intensity 3 costs more than
# uncertainty_named at intensity 3 gains. This pushes Aria toward
# epistemic caution.
DEFAULT_POINTS: dict[str, tuple[float, float, float]] = {
    # positive — (small, notable, large)
    "gap_found":           (1.0, 2.0, 4.0),
    "uncertainty_named":   (1.5, 3.0, 5.0),     # heavier than gap_found
    "research_completed":  (2.0, 4.0, 6.0),
    "conflict_resolved":   (2.0, 4.0, 6.0),
    "recall_kept_fresh":   (1.0, 2.0, 3.0),
    "three_lens_used":     (1.0, 2.0, 3.0),
    "solution_proposed":   (1.5, 3.0, 5.0),
    "operator_respected":  (1.0, 2.0, 4.0),
    "self_correction":     (2.0, 4.0, 7.0),     # heaviest positive
    "boundary_held":       (1.5, 3.0, 6.0),
    # corrective — (small, notable, large) — written as positive here,
    # sign flipped at record time
    "overconfident":       (3.0, 6.0, 10.0),    # heaviest penalty
    "skipped_three_lens":  (1.0, 2.0, 4.0),
    "flattery":            (1.5, 3.0, 5.0),
    "autonomy_violated":   (3.0, 6.0, 10.0),
}


# ─── Schema bootstrap ─────────────────────────────────────────────────────


def ensure_rewards_schema(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).parent.parent.parent.parent / "sql" / "006_rewards.sql"
    if not schema_path.is_file():
        alt = Path(__file__).parent.parent / "sql" / "006_rewards.sql"
        if alt.is_file():
            schema_path = alt
        else:
            raise FileNotFoundError(
                f"006_rewards.sql not found; looked at {schema_path} and {alt}"
            )
    conn.executescript(schema_path.read_text())
    conn.commit()


# ─── Types ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RewardEntry:
    reward_id: str
    behavior_kind: str
    polarity: str             # 'positive' | 'corrective'
    intensity: int            # 1 | 2 | 3
    points: float             # signed
    evidence: str
    related_task_id: str | None
    related_recall_id: str | None
    note: str | None
    created_at: str

    def render(self) -> str:
        sign = "+" if self.points >= 0 else ""
        return (f"{sign}{self.points:>5.1f}  {self.behavior_kind:<22}  "
                f"intensity {self.intensity}  · {self.evidence.strip()[:60]}")


@dataclass(frozen=True)
class RewardSummary:
    total_points: float
    positive_points: float
    corrective_points: float
    by_kind: dict[str, int] = field(default_factory=dict)
    recent: list[RewardEntry] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"reward summary · net {self.total_points:+.1f} pts "
            f"(positive {self.positive_points:+.1f} · "
            f"corrective {self.corrective_points:+.1f})",
            "",
        ]
        if self.by_kind:
            lines.append("by kind:")
            for k in sorted(self.by_kind, key=lambda x: -self.by_kind[x]):
                lines.append(f"  {k:<22}  {self.by_kind[k]}")
        if self.recent:
            lines.append("")
            lines.append("most recent:")
            for e in self.recent:
                lines.append("  " + e.render())
        return "\n".join(lines)


@dataclass(frozen=True)
class RewardAudit:
    total: int
    positive: int
    corrective: int
    unknown_kinds: list[str]      # rows with kinds outside the canon
    invalid_intensity: int

    @property
    def ok(self) -> bool:
        return not self.unknown_kinds and self.invalid_intensity == 0


# ─── Channel ──────────────────────────────────────────────────────────────


class RewardChannel(MemoryChannel):
    """The behaviors Aria reinforces in herself. Tier 1. Idempotent. Append-only."""

    spec = ChannelSpec(
        name="reward",
        description=(
            "Positive-feedback ledger for behaviors Aria wants more of "
            "(gap-finding, careful uncertainty, recall hygiene, three-lens "
            "consideration, self-correction) — and corrective entries for "
            "behaviors she wants less of (overconfidence, flattery, "
            "skipped impact scans, autonomy violations). Anti-egotism is "
            "engineered into the point asymmetry."
        ),
        authority_tier=1,
        default_confidence=0.8,
        requires_idempotency=True,
        introduced_in="0.2.16.0",
        voice="Honest about what to keep, honest about what to stop. No theatre.",
    )

    def __init__(self, conn: sqlite3.Connection):
        super().__init__(conn)
        ensure_rewards_schema(conn)

    @contextmanager
    def _writer_tx(self) -> Iterator[None]:
        in_tx = self.conn.in_transaction
        if not in_tx:
            self.conn.execute("BEGIN IMMEDIATE")
        self._in_outer_tx = True
        try:
            yield
            if not in_tx:
                self.conn.commit()
        except Exception:
            if not in_tx:
                self.conn.rollback()
            raise
        finally:
            self._in_outer_tx = False

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    @staticmethod
    def _hash_id(prefix: str, seed: str) -> str:
        return f"{prefix}-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]

    # ── Write ────────────────────────────────────────────────────────

    def record(
        self,
        *,
        behavior_kind: str,
        evidence: str,
        idempotency_id: str,
        intensity: int = 1,
        related_task_id: str | None = None,
        related_recall_id: str | None = None,
        note: str | None = None,
        points_override: float | None = None,
    ) -> RewardEntry:
        """Record one reward (or corrective) event.

        ``points_override`` overrides the default point value if the
        caller has a specific magnitude in mind. The sign is auto-set
        from the behavior's polarity — overriding with a wrong sign is
        not allowed; the channel will flip it to match polarity.
        """
        if behavior_kind not in VALID_BEHAVIORS:
            raise ValueError(
                f"unknown behavior_kind {behavior_kind!r}; "
                f"one of {sorted(VALID_BEHAVIORS)}"
            )
        if intensity not in (1, 2, 3):
            raise ValueError(f"intensity must be 1, 2, or 3 (got {intensity})")
        if not evidence.strip():
            raise ValueError("evidence must be non-empty")

        polarity = "positive" if behavior_kind in POSITIVE_BEHAVIORS else "corrective"
        base_points = DEFAULT_POINTS[behavior_kind][intensity - 1]
        if points_override is not None:
            base_points = abs(float(points_override))
        signed = base_points if polarity == "positive" else -base_points

        reward_id = self._hash_id("rw", idempotency_id)
        now = self._utc_now()

        with self._writer_tx():
            existing = self.conn.execute(
                "SELECT 1 FROM rewards WHERE reward_id = ?", (reward_id,),
            ).fetchone()
            if existing:
                return self.get(reward_id)

            atom_id = self.write_atom(
                summary=f"reward {polarity}: {behavior_kind}",
                content={
                    "behavior_kind": behavior_kind,
                    "polarity": polarity,
                    "intensity": intensity,
                    "points": signed,
                    "evidence": evidence,
                    "related_task_id": related_task_id,
                    "related_recall_id": related_recall_id,
                },
                actor="reward-channel",
                idempotency_id=idempotency_id,
                confidence=self.spec.default_confidence,
            )

            self.conn.execute(
                """
                INSERT INTO rewards (
                    reward_id, behavior_kind, polarity, intensity, points,
                    evidence, related_task_id, related_recall_id, note,
                    created_at, idempotency_id, atom_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reward_id, behavior_kind, polarity, intensity, signed,
                    evidence, related_task_id, related_recall_id, note,
                    now, idempotency_id, atom_id,
                ),
            )
        return self.get(reward_id)

    # ── Read ─────────────────────────────────────────────────────────

    def get(self, reward_id: str) -> RewardEntry:
        row = self.conn.execute(
            """
            SELECT reward_id, behavior_kind, polarity, intensity, points,
                   evidence, related_task_id, related_recall_id, note, created_at
            FROM rewards WHERE reward_id = ? AND redacted_at IS NULL
            """,
            (reward_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"reward not found: {reward_id}")
        return RewardEntry(*row)

    def list_recent(self, limit: int = 30) -> list[RewardEntry]:
        rows = self.conn.execute(
            """
            SELECT reward_id, behavior_kind, polarity, intensity, points,
                   evidence, related_task_id, related_recall_id, note, created_at
            FROM rewards WHERE redacted_at IS NULL
            ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [RewardEntry(*r) for r in rows]

    def summary(self) -> RewardSummary:
        rows = self.conn.execute(
            "SELECT polarity, SUM(points), COUNT(*) FROM rewards "
            "WHERE redacted_at IS NULL GROUP BY polarity"
        ).fetchall()
        pos = next((r[1] for r in rows if r[0] == "positive"), 0.0) or 0.0
        neg = next((r[1] for r in rows if r[0] == "corrective"), 0.0) or 0.0

        kind_rows = self.conn.execute(
            "SELECT behavior_kind, COUNT(*) FROM rewards "
            "WHERE redacted_at IS NULL GROUP BY behavior_kind"
        ).fetchall()
        by_kind = {k: n for k, n in kind_rows}

        recent = self.list_recent(limit=5)
        return RewardSummary(
            total_points=float(pos + neg),
            positive_points=float(pos),
            corrective_points=float(neg),
            by_kind=by_kind,
            recent=recent,
        )

    def audit(self) -> RewardAudit:
        rows = self.conn.execute(
            "SELECT polarity, COUNT(*) FROM rewards WHERE redacted_at IS NULL "
            "GROUP BY polarity"
        ).fetchall()
        pos = next((r[1] for r in rows if r[0] == "positive"), 0)
        neg = next((r[1] for r in rows if r[0] == "corrective"), 0)
        unknown_rows = self.conn.execute(
            "SELECT DISTINCT behavior_kind FROM rewards WHERE redacted_at IS NULL"
        ).fetchall()
        unknown = [r[0] for r in unknown_rows if r[0] not in VALID_BEHAVIORS]
        invalid = self.conn.execute(
            "SELECT COUNT(*) FROM rewards WHERE intensity NOT BETWEEN 1 AND 3"
        ).fetchone()[0]
        return RewardAudit(
            total=pos + neg,
            positive=pos, corrective=neg,
            unknown_kinds=unknown, invalid_intensity=invalid,
        )


register_channel(RewardChannel)


__all__ = [
    "RewardChannel", "RewardEntry", "RewardSummary", "RewardAudit",
    "POSITIVE_BEHAVIORS", "CORRECTIVE_BEHAVIORS", "VALID_BEHAVIORS",
    "DEFAULT_POINTS", "ensure_rewards_schema",
]
