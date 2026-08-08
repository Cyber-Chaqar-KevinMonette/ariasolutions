"""
checkpoint.py — Pre-action checkpoint store for deep resume (M42).

Before every T2/T3 action: write a "pending" checkpoint atom.
After success: resolve it. On process death mid-action: checkpoint stays pending.
On next session start: session_resume_audit() surfaces pending checkpoints → tell Kevin.

Design:
  - Backed by atoms DB with scope_tags=['checkpoint']
  - Append-only (never deletes atoms)
  - "pending" checkpoints with no corresponding "resolved" marker = incomplete action
  - pre_state_hash: quick hash of relevant path/args state before action
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from ulid import ULID


Status = Literal["pending", "resolved", "abandoned"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class ActionCheckpoint:
    checkpoint_id: str
    session_id: str
    tool_name: str
    args_summary: str      # first 500 chars of args JSON
    pre_state_hash: str    # quick hash of relevant state before action
    tier: int
    created_at: str
    status: Status = "pending"
    resolved_at: str | None = None
    abandon_reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "checkpoint_id": self.checkpoint_id,
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "args_summary": self.args_summary,
            "pre_state_hash": self.pre_state_hash,
            "tier": self.tier,
            "status": self.status,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "abandon_reason": self.abandon_reason,
        }


def _hash_args(args: dict) -> str:
    raw = json.dumps(args, sort_keys=True, default=str)[:2000]
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class CheckpointStore:
    """Pre-action checkpoint store backed by atoms DB. Append-only."""

    def write_pre(
        self,
        tool_name: str,
        args: dict,
        tier: int,
        session_id: str,
    ) -> ActionCheckpoint:
        ckpt = ActionCheckpoint(
            checkpoint_id=str(ULID()),
            session_id=session_id,
            tool_name=tool_name,
            args_summary=json.dumps(args, default=str)[:500],
            pre_state_hash=_hash_args(args),
            tier=tier,
            created_at=_utc_now(),
            status="pending",
        )
        _write_checkpoint_atom(ckpt)
        return ckpt

    def resolve(self, checkpoint_id: str) -> None:
        _update_checkpoint_status(checkpoint_id, "resolved", _utc_now(), None)

    def abandon(self, checkpoint_id: str, reason: str) -> None:
        _update_checkpoint_status(checkpoint_id, "abandoned", None, reason)

    def pending_for_session(self, session_id: str) -> list[ActionCheckpoint]:
        return _load_pending_checkpoints(session_id)

    def all_pending(self, limit: int = 20) -> list[ActionCheckpoint]:
        return _load_all_pending(limit)


# Module-level singleton
_checkpoint_store = CheckpointStore()


def get_checkpoint_store() -> CheckpointStore:
    return _checkpoint_store


# ── DB helpers ────────────────────────────────────────────────────────────────


def _write_checkpoint_atom(ckpt: ActionCheckpoint) -> None:
    from sovereign_agent.db import open_atoms_db
    from sovereign_agent.memory import Atom, write_atom

    atom = Atom(
        type="action-checkpoint",
        summary=f"[T{ckpt.tier}/pending] {ckpt.tool_name}: {ckpt.args_summary[:120]}",
        content_ref={"kind": "inline", "content": json.dumps(ckpt.as_dict())},
        claims=[],
        parents=[ckpt.session_id],
        confidence=1.0,
        created_by={"actor": "resume-crown", "version": "M42"},
        scope_tags=["checkpoint"],
        atom_id=ckpt.checkpoint_id,
    )
    conn = open_atoms_db()
    try:
        write_atom(conn, atom)
        conn.commit()
    finally:
        conn.close()


def _update_checkpoint_status(
    checkpoint_id: str,
    status: str,
    resolved_at: str | None,
    abandon_reason: str | None,
) -> None:
    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        cur = conn.execute(
            "SELECT content_ref FROM atoms WHERE atom_id = ?", (checkpoint_id,)
        )
        row = cur.fetchone()
        if row is None:
            return
        content = json.loads(row[0]) if row[0] else {}
        data = content.get("content", {})
        if isinstance(data, str):
            data = json.loads(data)
        data["status"] = status
        if resolved_at:
            data["resolved_at"] = resolved_at
        if abandon_reason:
            data["abandon_reason"] = abandon_reason
        conn.execute(
            "UPDATE atoms SET content_ref = ?, summary = ? WHERE atom_id = ?",
            (
                json.dumps({"kind": "inline", "content": json.dumps(data)}),
                f"[T{data.get('tier', '?')}/{status}] {data.get('tool_name', '?')}: {data.get('args_summary', '')[:120]}",
                checkpoint_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _load_pending_checkpoints(session_id: str) -> list[ActionCheckpoint]:
    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        cur = conn.execute(
            "SELECT atom_id, content_ref, created_at FROM atoms "
            "WHERE type='action-checkpoint' "
            "ORDER BY created_at DESC LIMIT 100",
        )
        rows = cur.fetchall()
        checkpoints: list[ActionCheckpoint] = []
        for atom_id, content_ref_json, created_at in rows:
            try:
                content = json.loads(content_ref_json) if content_ref_json else {}
                data = content.get("content", {})
                if isinstance(data, str):
                    data = json.loads(data)
                if data.get("status") != "pending":
                    continue
                if session_id and data.get("session_id") != session_id:
                    continue
                checkpoints.append(ActionCheckpoint(
                    checkpoint_id=data.get("checkpoint_id", atom_id),
                    session_id=data.get("session_id", ""),
                    tool_name=data.get("tool_name", ""),
                    args_summary=data.get("args_summary", ""),
                    pre_state_hash=data.get("pre_state_hash", ""),
                    tier=data.get("tier", 2),
                    created_at=created_at,
                    status="pending",
                ))
            except Exception:  # noqa: BLE001
                continue
        return checkpoints
    finally:
        conn.close()


def _load_all_pending(limit: int) -> list[ActionCheckpoint]:
    from sovereign_agent.db import open_atoms_db
    conn = open_atoms_db()
    try:
        cur = conn.execute(
            "SELECT atom_id, content_ref, created_at FROM atoms "
            "WHERE type='action-checkpoint' "
            "ORDER BY created_at DESC LIMIT ?",
            (limit * 5,),
        )
        rows = cur.fetchall()
        checkpoints: list[ActionCheckpoint] = []
        for atom_id, content_ref_json, created_at in rows:
            try:
                content = json.loads(content_ref_json) if content_ref_json else {}
                data = content.get("content", {})
                if isinstance(data, str):
                    data = json.loads(data)
                if data.get("status") != "pending":
                    continue
                checkpoints.append(ActionCheckpoint(
                    checkpoint_id=data.get("checkpoint_id", atom_id),
                    session_id=data.get("session_id", ""),
                    tool_name=data.get("tool_name", ""),
                    args_summary=data.get("args_summary", ""),
                    pre_state_hash=data.get("pre_state_hash", ""),
                    tier=data.get("tier", 2),
                    created_at=created_at,
                    status="pending",
                ))
                if len(checkpoints) >= limit:
                    break
            except Exception:  # noqa: BLE001
                continue
        return checkpoints
    finally:
        conn.close()


__all__ = ["ActionCheckpoint", "CheckpointStore", "get_checkpoint_store"]
