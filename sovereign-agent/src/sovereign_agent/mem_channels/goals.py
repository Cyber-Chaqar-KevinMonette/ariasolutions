"""
goals.py — Declared goals with timeframes & status.

Goals are durable. They are written rarely and reread often. Each goal
has a timeframe (3-month / 12-month / 3-year / 7th-generation per MOS
canon §6.5) and a status (active | paused | achieved | abandoned).

MOS Authority Tier 2 — persistent change, logged, not blocking.
"""
from __future__ import annotations

import sqlite3
from typing import Literal

from ..channels import ChannelSpec, MemoryChannel, register_channel


GoalTimeframe = Literal["3-month", "12-month", "3-year", "7th-generation"]
GoalStatus = Literal["active", "paused", "achieved", "abandoned"]


@register_channel
class GoalsChannel(MemoryChannel):
    spec = ChannelSpec(
        name="goals",
        description=(
            "Declared goals with timeframes (3-month / 12-month / 3-year / "
            "7th-generation per MOS canon §6.5) and status. Slow-moving."
        ),
        authority_tier=2,
        default_confidence=0.85,
        introduced_in="0.2.14",
        voice="Patient, structured, future-aware. The compass, not the map.",
    )

    def declare(
        self,
        *,
        goal: str,
        timeframe: GoalTimeframe = "12-month",
        rationale: str = "",
        project: str | None = None,
        idempotency_id: str | None = None,
    ) -> str:
        """Declare a new goal. Returns atom_id."""
        if timeframe not in ("3-month", "12-month", "3-year", "7th-generation"):
            raise ValueError(f"invalid timeframe: {timeframe!r}")
        extra: dict = {}
        if project:
            extra["projects"] = [project]
        return self.write_atom(
            summary=f"GOAL[{timeframe}]: {goal}",
            content={
                "goal": goal, "timeframe": timeframe,
                "rationale": rationale, "status": "active",
            },
            idempotency_id=idempotency_id,
            extra_scope=extra,
            actor="goals-channel",
        )

    def update_status(
        self,
        *,
        original_atom_id: str,
        new_status: GoalStatus,
        note: str = "",
    ) -> str:
        """Update a goal's status by writing a new atom that supersedes
        the old one. Returns the new atom_id.

        Append-only: the original atom remains in the history.
        """
        if new_status not in ("active", "paused", "achieved", "abandoned"):
            raise ValueError(f"invalid status: {new_status!r}")

        # Read original
        row = self.conn.execute(
            "SELECT summary, content_ref FROM atoms WHERE atom_id = ?",
            (original_atom_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"no such goal atom: {original_atom_id}")

        import json
        try:
            content_ref = json.loads(row[1])
            data = content_ref.get("data", {}) if isinstance(content_ref, dict) else {}
        except json.JSONDecodeError:
            data = {}
        data["status"] = new_status
        if note:
            data["status_note"] = note

        new_atom_id = self.write_atom(
            summary=f"{row[0]} [→ {new_status}]",
            content=data,
            parents=[original_atom_id],
            actor="goals-channel",
        )

        # Mark original as superseded
        self.conn.execute(
            "UPDATE atoms SET superseded_at = ?, superseded_by = ? "
            "WHERE atom_id = ?",
            (
                __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc,
                ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                new_atom_id,
                original_atom_id,
            ),
        )
        self.conn.commit()
        return new_atom_id

    def list_active(self, *, timeframe: GoalTimeframe | None = None) -> list[dict]:
        """All currently active goals, optionally filtered by timeframe."""
        all_atoms = self.list_atoms(limit=200)
        active = []
        for a in all_atoms:
            content = self.hydrate(a["atom_id"])
            if content.get("status") != "active":
                continue
            if timeframe and content.get("timeframe") != timeframe:
                continue
            a["content"] = content
            active.append(a)
        return active


__all__ = ["GoalsChannel", "GoalStatus", "GoalTimeframe"]
