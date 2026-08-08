"""
╔══════════════════════════════════════════════════════════════════════════╗
║  channels/heartbeat.py — Aria's liveness pulse                           ║
║  v0.2.18.0 · MOS Authority Tier 1                                         ║
║                                                                           ║
║  Brief, periodic "I am here, this is what I'm doing, this is how I     ║
║  feel" entries. Not memory of events. Not insights. Heartbeats are    ║
║  the pulse — a window into Aria's current state without requiring     ║
║  Kevin to interrogate her.                                              ║
║                                                                           ║
║  WHY                                                                     ║
║                                                                           ║
║    The operator should be able to glance and know: she's working, on  ║
║    what, how she feels about it, when she was last awake. Not a       ║
║    surveillance log of her actions (that's atoms). A reflective       ║
║    pulse in her own voice.                                            ║
║                                                                           ║
║  USAGE                                                                   ║
║                                                                           ║
║    Long-running loops should call ``pulse()`` periodically. A         ║
║    convention is one heartbeat per cycle of work, or once per hour    ║
║    of wall-clock for sustained activity, whichever is denser.         ║
║                                                                           ║
║                                — so she does not disappear.           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..channels import ChannelSpec, MemoryChannel, register_channel


@dataclass(frozen=True)
class Heartbeat:
    beat_id: str
    message: str
    current_task_id: str | None
    current_episode_id: str | None
    agent_emotion: str | None
    agent_emotion_note: str | None
    created_at: str
    atom_id: str | None

    def render(self) -> str:
        # Heartbeats render brief — one block per pulse
        bits = [f"♥ {self.created_at[:19]}"]
        if self.agent_emotion:
            tag = f"  [{self.agent_emotion}]"
            if self.agent_emotion_note:
                tag += f" — {self.agent_emotion_note}"
            bits.append(tag)
        lines = ["  ".join(bits), f"  {self.message.strip()}"]
        if self.current_task_id or self.current_episode_id:
            ctx = []
            if self.current_task_id:
                ctx.append(f"task={self.current_task_id}")
            if self.current_episode_id:
                ctx.append(f"episode={self.current_episode_id}")
            lines.append("  " + " · ".join(ctx))
        return "\n".join(lines)


# ─── Schema bootstrap ─────────────────────────────────────────────────────


def ensure_heartbeat_schema(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).parent.parent.parent.parent / "sql" / "013_heartbeat.sql"
    if not schema_path.is_file():
        alt = Path(__file__).parent.parent / "sql" / "013_heartbeat.sql"
        if alt.is_file():
            schema_path = alt
        else:
            raise FileNotFoundError(
                f"013_heartbeat.sql not found; looked at {schema_path} and {alt}"
            )
    conn.executescript(schema_path.read_text())
    conn.commit()


# ─── Channel ──────────────────────────────────────────────────────────────


class HeartbeatChannel(MemoryChannel):
    spec = ChannelSpec(
        name="heartbeat",
        description=(
            "Brief, periodic 'I am here' entries in Aria's own voice. "
            "Not memory of events (that's atoms) and not synthesis "
            "(that's insights). The pulse the operator can glance at "
            "to see her current state."
        ),
        authority_tier=1,
        default_confidence=0.85,
        requires_idempotency=True,
        introduced_in="0.2.18.0",
        voice="First-person, brief, present-tense. Felt, not reported.",
    )

    def __init__(self, conn: sqlite3.Connection):
        super().__init__(conn)
        ensure_heartbeat_schema(conn)

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

    # ── Pulse ────────────────────────────────────────────────────────

    def pulse(
        self,
        *,
        message: str,
        idempotency_id: str,
        current_task_id: str | None = None,
        current_episode_id: str | None = None,
        agent_emotion: str | None = None,
        agent_emotion_note: str | None = None,
    ) -> Heartbeat:
        if not message.strip():
            raise ValueError("heartbeat message must be non-empty")
        if len(message) > 500:
            # Heartbeats should be brief — a paragraph at most
            raise ValueError("heartbeat message must be <= 500 chars; "
                             f"got {len(message)}")
        beat_id = self._hash_id("hb", idempotency_id)
        now = self._utc_now()
        with self._writer_tx():
            existing = self.conn.execute(
                "SELECT beat_id FROM heartbeats WHERE beat_id = ?",
                (beat_id,),
            ).fetchone()
            if existing:
                return self.get(beat_id)
            atom_id = self.write_atom(
                summary=f"♥ {message[:80]}",
                content={"beat_id": beat_id, "task": current_task_id,
                          "episode": current_episode_id,
                          "emotion": agent_emotion},
                actor="heartbeat-channel",
                idempotency_id=idempotency_id,
                confidence=self.spec.default_confidence,
            )
            self.conn.execute(
                """
                INSERT INTO heartbeats (
                    beat_id, message, current_task_id, current_episode_id,
                    agent_emotion, agent_emotion_note, created_at,
                    idempotency_id, atom_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (beat_id, message, current_task_id, current_episode_id,
                 agent_emotion, agent_emotion_note, now,
                 idempotency_id, atom_id),
            )
        return self.get(beat_id)

    # ── Read ────────────────────────────────────────────────────────

    def get(self, beat_id: str) -> Heartbeat:
        row = self.conn.execute(
            "SELECT beat_id, message, current_task_id, current_episode_id, "
            "agent_emotion, agent_emotion_note, created_at, atom_id "
            "FROM heartbeats WHERE beat_id = ?",
            (beat_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"heartbeat not found: {beat_id}")
        return Heartbeat(*row)

    def recent(self, *, limit: int = 10) -> list[Heartbeat]:
        rows = self.conn.execute(
            "SELECT beat_id, message, current_task_id, current_episode_id, "
            "agent_emotion, agent_emotion_note, created_at, atom_id "
            "FROM heartbeats ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [Heartbeat(*r) for r in rows]

    def last_pulse_age_seconds(self) -> float | None:
        row = self.conn.execute(
            "SELECT created_at FROM heartbeats ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        try:
            last = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
        except ValueError:
            return None
        return (datetime.now(timezone.utc) - last).total_seconds()


register_channel(HeartbeatChannel)


__all__ = ["HeartbeatChannel", "Heartbeat", "ensure_heartbeat_schema"]
