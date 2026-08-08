"""
objective_map.py — Objective Map for safe BTW/interjection system (M37).

Objectives are durable intent atoms. They let Kevin (or Aria) inject secondary
goals, BTW notes, or background tasks without interrupting active work.

Lifecycle: add → active → (complete | deferred | cancelled)

Backed by atoms DB with scope_tags=['objective']. Never deletes atoms.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from ulid import ULID


Priority = Literal["primary", "secondary", "background"]
Scope = Literal["this_session", "persistent", "this_workflow"]
Status = Literal["active", "complete", "deferred", "cancelled"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass
class Objective:
    """One tracked objective."""
    id: str
    text: str
    priority: Priority
    scope: Scope
    status: Status
    relate_to: str | None
    created_at: str
    completed_at: str | None = None
    note: str | None = None  # for BTW notes (lightweight, no action required)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "priority": self.priority,
            "scope": self.scope,
            "status": self.status,
            "relate_to": self.relate_to,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "note": self.note,
        }


# ─── In-memory store (session-scoped; atoms DB is the durable backing) ──────

_objectives: list[Objective] = []


def _load_from_db(conn: sqlite3.Connection) -> list[Objective]:
    """Read objective atoms from DB. Returns list sorted by created_at."""
    cur = conn.execute(
        "SELECT content_ref, created_at FROM atoms "
        "WHERE json_extract(scope_tags, '$[0]') = 'objective' "
        "  AND (superseded_at IS NULL OR superseded_at = '') "
        "ORDER BY created_at DESC "
        "LIMIT 200",
    )
    rows = cur.fetchall()
    objectives = []
    for content_ref_json, created_at in rows:
        try:
            content = json.loads(content_ref_json) if content_ref_json else {}
            data = content.get("content", {})
            if isinstance(data, str):
                data = json.loads(data)
            obj = Objective(
                id=data["id"],
                text=data["text"],
                priority=data.get("priority", "secondary"),
                scope=data.get("scope", "this_session"),
                status=data.get("status", "active"),
                relate_to=data.get("relate_to"),
                created_at=created_at,
                completed_at=data.get("completed_at"),
                note=data.get("note"),
            )
            objectives.append(obj)
        except Exception:  # noqa: BLE001
            continue
    return objectives


class ObjectiveMap:
    """Objective store backed by atoms DB. Session-local list for speed."""

    def add(
        self,
        text: str,
        priority: Priority = "secondary",
        scope: Scope = "this_session",
        relate_to: str | None = None,
    ) -> Objective:
        obj = Objective(
            id=str(ULID()),
            text=text,
            priority=priority,
            scope=scope,
            status="active",
            relate_to=relate_to,
            created_at=_utc_now(),
        )
        _objectives.append(obj)
        return obj

    def add_btw(
        self,
        text: str,
        relates_to: str | None = None,
    ) -> Objective:
        obj = Objective(
            id=str(ULID()),
            text=text,
            priority="background",
            scope="this_session",
            status="active",
            relate_to=relates_to,
            created_at=_utc_now(),
            note="btw",
        )
        _objectives.append(obj)
        return obj

    def list_active(self, include_completed: bool = False) -> list[Objective]:
        if include_completed:
            return list(_objectives)
        return [o for o in _objectives if o.status == "active"]

    def get(self, objective_id: str) -> Objective | None:
        for o in _objectives:
            if o.id == objective_id:
                return o
        return None

    def complete(self, objective_id: str) -> Objective | None:
        obj = self.get(objective_id)
        if obj is None:
            return None
        obj.status = "complete"
        obj.completed_at = _utc_now()
        return obj

    def cancel(self, objective_id: str) -> Objective | None:
        obj = self.get(objective_id)
        if obj is None:
            return None
        obj.status = "cancelled"
        return obj

    def by_priority(self) -> list[Objective]:
        """Return active objectives sorted: primary > secondary > background."""
        order = {"primary": 0, "secondary": 1, "background": 2}
        return sorted(
            [o for o in _objectives if o.status == "active"],
            key=lambda o: order.get(o.priority, 99),
        )

    def load_from_db(self, conn: sqlite3.Connection) -> int:
        """Populate in-memory store from atoms DB. Returns count loaded."""
        loaded = _load_from_db(conn)
        existing_ids = {o.id for o in _objectives}
        added = 0
        for obj in loaded:
            if obj.id not in existing_ids:
                _objectives.append(obj)
                added += 1
        return added


# Module-level singleton
_objective_map = ObjectiveMap()


def get_objective_map() -> ObjectiveMap:
    return _objective_map


__all__ = ["Objective", "ObjectiveMap", "get_objective_map", "Priority", "Scope", "Status"]
