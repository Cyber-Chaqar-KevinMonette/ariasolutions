"""
╔══════════════════════════════════════════════════════════════════════════╗
║  channels/reasoning.py — durable chain-of-thought traces                 ║
║  v0.2.18.0 · MOS Authority Tier 1                                         ║
║                                                                           ║
║  WHY                                                                     ║
║                                                                           ║
║    Insights are syntheses Aria publishes. Tasks are work she does.      ║
║    Recalls are curated artifacts she gives the operator. None of       ║
║    these is the THOUGHT PROCESS itself — the working-out from "I       ║
║    notice something" through "I hypothesize" to "the evidence says"   ║
║    to "I conclude with confidence C, leaving these uncertainties."   ║
║                                                                           ║
║    The reasoning channel is that. Each trace is one question; each    ║
║    step is one move (observation, hypothesis, evidence, counter-    ║
║    evidence, revision, note). The trace closes with a conclusion and ║
║    a calibrated confidence.                                            ║
║                                                                           ║
║  WHY THIS MATTERS                                                       ║
║                                                                           ║
║    Aria's epistemics become inspectable. The operator can read her    ║
║    reasoning, disagree with steps, and add counter-evidence. The      ║
║    constitutional "calibrated uncertainty" commitment gets teeth:    ║
║    confident assertions either have a reasoning trace behind them    ║
║    or they don't, and the operator can tell which.                   ║
║                                                                           ║
║  WHY NOT JUST USE ATOMS                                                  ║
║                                                                           ║
║    Atoms are atomic — one assertion, one event. Reasoning is          ║
║    multi-step and has structure (kind of move, ordering, branching). ║
║    Encoding that structure inside atom claims would lose readability  ║
║    and make traces hard to follow. A dedicated table costs little    ║
║    and gives the right shape.                                        ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from ..channels import ChannelSpec, MemoryChannel, register_channel


StepKind = Literal[
    "observation",       # I notice X
    "hypothesis",        # X might be because Y
    "evidence",          # supporting data for a hypothesis
    "counter_evidence",  # data against a hypothesis
    "revision",          # I now think Z instead
    "note",              # any other annotation
]

VALID_STEP_KINDS = frozenset({"observation", "hypothesis", "evidence",
                               "counter_evidence", "revision", "note"})


@dataclass(frozen=True)
class ReasoningStep:
    step_id: str
    trace_id: str
    step_number: int
    step_kind: str
    content: str
    confidence: float
    sources: list[str]
    created_at: str

    def render(self) -> str:
        glyph = {
            "observation":      "◯",
            "hypothesis":       "?",
            "evidence":         "+",
            "counter_evidence": "−",
            "revision":         "↺",
            "note":             "·",
        }.get(self.step_kind, "·")
        return (f"  {glyph} [{self.step_kind:<16}] "
                f"({self.confidence:.2f}) {self.content.strip()[:120]}")


@dataclass(frozen=True)
class ReasoningTrace:
    trace_id: str
    title: str
    opened_at: str
    closed_at: str | None
    status: str
    conclusion: str | None
    confidence: float
    related_task_id: str | None
    parent_trace_id: str | None
    steps: list[ReasoningStep] = field(default_factory=list)

    def render(self) -> str:
        glyph = {
            "open":       "◯",
            "concluded":  "●",
            "abandoned":  "↩",
            "redacted":   "▨",
        }.get(self.status, "?")
        head = f"{glyph}  {self.title}  [{self.status}]"
        bar = "─" * min(72, len(head))
        lines = [head, bar]
        lines.append(f"opened {self.opened_at[:19]}"
                     + (f" · closed {self.closed_at[:19]}" if self.closed_at else ""))
        lines.append("")
        if self.steps:
            for s in self.steps:
                lines.append(s.render())
            lines.append("")
        if self.conclusion:
            lines.append(f"⇒ conclusion ({self.confidence:.2f}): "
                         + self.conclusion.strip())
        elif self.status == "open":
            lines.append("⇒ (still open)")
        return "\n".join(lines)


@dataclass(frozen=True)
class ReasoningAudit:
    total: int
    open: int
    concluded: int
    abandoned: int
    long_open: int          # open > 7 days
    high_confidence_no_evidence: int    # conclusions with confidence >= 0.9 but no evidence steps

    @property
    def ok(self) -> bool:
        return self.high_confidence_no_evidence == 0


# ─── Schema bootstrap ─────────────────────────────────────────────────────


def ensure_reasoning_schema(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).parent.parent.parent.parent / "sql" / "009_reasoning.sql"
    if not schema_path.is_file():
        alt = Path(__file__).parent.parent / "sql" / "009_reasoning.sql"
        if alt.is_file():
            schema_path = alt
        else:
            raise FileNotFoundError(
                f"009_reasoning.sql not found; looked at {schema_path} and {alt}"
            )
    conn.executescript(schema_path.read_text())
    conn.commit()


# ─── Errors ────────────────────────────────────────────────────────────────


class TraceNotFoundError(KeyError):
    pass


class TraceStateError(ValueError):
    pass


# ─── Channel ──────────────────────────────────────────────────────────────


class ReasoningChannel(MemoryChannel):
    """Durable chain-of-thought traces. Tier 1. Append-only steps."""

    spec = ChannelSpec(
        name="reasoning",
        description=(
            "Aria's working thought-trace. Each trace is one question with "
            "ordered steps: observations, hypotheses, evidence, counter-"
            "evidence, revisions, notes. Traces close with a conclusion "
            "and a calibrated confidence. Append-only steps mean the "
            "operator can read Aria's reasoning history honestly."
        ),
        authority_tier=1,
        default_confidence=0.6,
        requires_idempotency=True,
        introduced_in="0.2.18.0",
        voice="Working-out, not pronouncement. Honest about uncertainty.",
    )

    def __init__(self, conn: sqlite3.Connection):
        super().__init__(conn)
        ensure_reasoning_schema(conn)

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
    def _hash_id(prefix: str, seed: str) -> str:
        return f"{prefix}-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # ── Open trace ───────────────────────────────────────────────────

    def open(
        self,
        *,
        title: str,
        idempotency_id: str,
        related_task_id: str | None = None,
        parent_trace_id: str | None = None,
    ) -> ReasoningTrace:
        if not title.strip():
            raise ValueError("title must be non-empty")
        trace_id = self._hash_id("rt", idempotency_id)
        now = self._utc_now()
        with self._writer_tx():
            existing = self.conn.execute(
                "SELECT trace_id FROM reasoning_traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
            if existing:
                return self.get(trace_id)
            atom_id = self.write_atom(
                summary=f"reasoning opened: {title}",
                content={"trace_id": trace_id, "title": title,
                          "related_task_id": related_task_id},
                actor="reasoning-channel",
                idempotency_id=idempotency_id,
                confidence=self.spec.default_confidence,
            )
            self.conn.execute(
                """
                INSERT INTO reasoning_traces (
                    trace_id, title, opened_at, status, confidence,
                    related_task_id, parent_trace_id, idempotency_id, atom_id
                ) VALUES (?, ?, ?, 'open', 0.5, ?, ?, ?, ?)
                """,
                (trace_id, title, now, related_task_id, parent_trace_id,
                 idempotency_id, atom_id),
            )
        return self.get(trace_id)

    # ── Add step ────────────────────────────────────────────────────

    def add_step(
        self,
        trace_id: str,
        *,
        step_kind: StepKind,
        content: str,
        confidence: float = 0.5,
        sources: list[str] | None = None,
    ) -> ReasoningStep:
        if step_kind not in VALID_STEP_KINDS:
            raise ValueError(f"invalid step_kind: {step_kind}; "
                             f"one of {sorted(VALID_STEP_KINDS)}")
        if not content.strip():
            raise ValueError("step content must be non-empty")
        confidence = max(0.0, min(1.0, float(confidence)))
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT status FROM reasoning_traces WHERE trace_id = ? "
                "AND redacted_at IS NULL",
                (trace_id,),
            ).fetchone()
            if row is None:
                raise TraceNotFoundError(f"trace not found: {trace_id}")
            if row[0] != "open":
                raise TraceStateError(
                    f"cannot add step to a {row[0]} trace; revise via new step in a new trace"
                )
            # Next step number
            n_row = self.conn.execute(
                "SELECT COALESCE(MAX(step_number), 0) + 1 "
                "FROM reasoning_steps WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
            step_number = int(n_row[0])
            now = self._utc_now()
            step_id = self._hash_id("rs", f"{trace_id}::{step_number}::{content[:64]}")
            self.conn.execute(
                """
                INSERT INTO reasoning_steps (
                    step_id, trace_id, step_number, step_kind, content,
                    confidence, sources, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (step_id, trace_id, step_number, step_kind, content,
                 confidence, json.dumps(sources or []), now),
            )
            return ReasoningStep(
                step_id=step_id, trace_id=trace_id, step_number=step_number,
                step_kind=step_kind, content=content, confidence=confidence,
                sources=list(sources or []), created_at=now,
            )

    # ── Conclude ────────────────────────────────────────────────────

    def conclude(
        self,
        trace_id: str,
        *,
        conclusion: str,
        confidence: float,
        idempotency_id: str | None = None,
    ) -> ReasoningTrace:
        confidence = max(0.0, min(1.0, float(confidence)))
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT status FROM reasoning_traces WHERE trace_id = ? "
                "AND redacted_at IS NULL",
                (trace_id,),
            ).fetchone()
            if row is None:
                raise TraceNotFoundError(f"trace not found: {trace_id}")
            if row[0] != "open":
                return self.get(trace_id)
            now = self._utc_now()
            self.conn.execute(
                "UPDATE reasoning_traces SET status = 'concluded', "
                "closed_at = ?, conclusion = ?, confidence = ? "
                "WHERE trace_id = ?",
                (now, conclusion, confidence, trace_id),
            )
            self.write_atom(
                summary=f"reasoning concluded: {self.get(trace_id).title}",
                content={"trace_id": trace_id, "conclusion": conclusion,
                          "confidence": confidence},
                actor="reasoning-channel",
                idempotency_id=f"conclude::{trace_id}::{idempotency_id or now}",
                confidence=confidence,
            )
        return self.get(trace_id)

    def abandon(self, trace_id: str, *, reason: str | None = None) -> ReasoningTrace:
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT status FROM reasoning_traces WHERE trace_id = ? "
                "AND redacted_at IS NULL",
                (trace_id,),
            ).fetchone()
            if row is None:
                raise TraceNotFoundError(f"trace not found: {trace_id}")
            if row[0] != "open":
                return self.get(trace_id)
            now = self._utc_now()
            self.conn.execute(
                "UPDATE reasoning_traces SET status = 'abandoned', closed_at = ? "
                "WHERE trace_id = ?",
                (now, trace_id),
            )
        return self.get(trace_id)

    def redact(self, trace_id: str, *, idempotency_id: str,
               reason: str | None = None) -> None:
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT redacted_at FROM reasoning_traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
            if row is None:
                raise TraceNotFoundError(f"trace not found: {trace_id}")
            if row[0]:
                return
            now = self._utc_now()
            self.conn.execute(
                "UPDATE reasoning_traces SET status = 'redacted', redacted_at = ? "
                "WHERE trace_id = ?",
                (now, trace_id),
            )

    # ── Read ────────────────────────────────────────────────────────

    def get(self, trace_id: str, *, include_redacted: bool = False) -> ReasoningTrace:
        row = self.conn.execute(
            """
            SELECT trace_id, title, opened_at, closed_at, status,
                   conclusion, confidence, related_task_id, parent_trace_id
            FROM reasoning_traces WHERE trace_id = ?
            """,
            (trace_id,),
        ).fetchone()
        if row is None:
            raise TraceNotFoundError(f"trace not found: {trace_id}")
        if row[4] == "redacted" and not include_redacted:
            raise TraceNotFoundError(f"trace redacted: {trace_id}")
        steps_rows = self.conn.execute(
            "SELECT step_id, trace_id, step_number, step_kind, content, "
            "confidence, sources, created_at FROM reasoning_steps "
            "WHERE trace_id = ? ORDER BY step_number",
            (trace_id,),
        ).fetchall()
        steps = [
            ReasoningStep(
                step_id=r[0], trace_id=r[1], step_number=r[2],
                step_kind=r[3], content=r[4], confidence=r[5],
                sources=json.loads(r[6] or "[]"), created_at=r[7],
            )
            for r in steps_rows
        ]
        return ReasoningTrace(
            trace_id=row[0], title=row[1], opened_at=row[2],
            closed_at=row[3], status=row[4], conclusion=row[5],
            confidence=row[6], related_task_id=row[7],
            parent_trace_id=row[8], steps=steps,
        )

    def list_traces(
        self,
        *,
        status: str | None = None,
        limit: int = 30,
    ) -> list[ReasoningTrace]:
        clauses = ["redacted_at IS NULL"]
        params: list = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        sql = (
            "SELECT trace_id FROM reasoning_traces WHERE " +
            " AND ".join(clauses) + " ORDER BY opened_at DESC LIMIT ?"
        )
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [self.get(r[0]) for r in rows]

    def search(self, query: str, *, limit: int = 20) -> list[ReasoningTrace]:
        if not query.strip():
            return []
        safe = query.replace('"', " ")
        sql = """
            SELECT t.trace_id FROM reasoning_traces_fts
            JOIN reasoning_traces t ON t.rowid = reasoning_traces_fts.rowid
            WHERE reasoning_traces_fts MATCH ? AND t.redacted_at IS NULL
            ORDER BY rank LIMIT ?
        """
        try:
            rows = self.conn.execute(sql, (safe, limit)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [self.get(r[0]) for r in rows]

    def audit(self) -> ReasoningAudit:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) FROM reasoning_traces "
            "WHERE redacted_at IS NULL GROUP BY status"
        ).fetchall()
        by_status = {s: n for s, n in rows}
        total = sum(by_status.values())
        long_open = self.conn.execute(
            "SELECT COUNT(*) FROM reasoning_traces "
            "WHERE status = 'open' AND redacted_at IS NULL "
            "AND opened_at < datetime('now', '-7 days')"
        ).fetchone()[0]
        # High-confidence conclusions without evidence steps
        hi_no_ev = self.conn.execute(
            """
            SELECT COUNT(*) FROM reasoning_traces t
            WHERE t.status = 'concluded'
              AND t.confidence >= 0.9
              AND t.redacted_at IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM reasoning_steps s
                WHERE s.trace_id = t.trace_id AND s.step_kind = 'evidence'
              )
            """
        ).fetchone()[0]
        return ReasoningAudit(
            total=total,
            open=by_status.get("open", 0),
            concluded=by_status.get("concluded", 0),
            abandoned=by_status.get("abandoned", 0),
            long_open=long_open,
            high_confidence_no_evidence=hi_no_ev,
        )


register_channel(ReasoningChannel)


__all__ = [
    "ReasoningChannel", "ReasoningTrace", "ReasoningStep", "ReasoningAudit",
    "TraceNotFoundError", "TraceStateError", "VALID_STEP_KINDS",
    "ensure_reasoning_schema",
]
