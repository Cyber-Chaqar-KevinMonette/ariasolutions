"""
╔══════════════════════════════════════════════════════════════════════════╗
║  requests.py — the collaboration inbox  📬                                 ║
║                                                                            ║
║  A two-way work queue between Aria and her human. Aria posts the things    ║
║  she needs to move forward — a question, a batch of files to look at, a    ║
║  suggestion, an approval, a decision — and the human answers. Items move   ║
║  open → answered → resolved, and everything is logged so you can look      ║
║  back at how a piece of work actually got done.                            ║
║                                                                            ║
║  This pairs with the authority gate: when a run pauses for review, that    ║
║  pause is filed here as a request you can answer, rather than vanishing.   ║
║                                                                            ║
║  It is collaboration, not control — these are asks and answers between     ║
║  two people working together, logged honestly.                            ║
║                                                                            ║
║  v0.2.36.0                                                                 ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sovereign_agent.persistence.store import ErebloStore

logger = logging.getLogger(__name__)


# A little warmth in the cockpit. 🌱
KIND_EMOJI = {
    "question": "❓", "scan_files": "📂", "suggestion": "💡",
    "approval": "🛂", "decision": "🧭", "blocker": "🚧", "note": "📝",
    "celebrate": "🎉",
}
STATUS_EMOJI = {
    "open": "🟡", "answered": "🟢", "resolved": "✅", "cancelled": "⚪",
    "deferred": "⏸️", "needs_attention": "⚠️", "revisit": "🔖",
}
VALID_KINDS = frozenset(KIND_EMOJI)
VALID_STATUS = frozenset(STATUS_EMOJI)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    try:
        from ulid import ULID
        return str(ULID())
    except Exception:  # noqa: BLE001
        import uuid
        return uuid.uuid4().hex


def _emit(flag: str, *, trace_id: str, payload: Optional[dict[str, Any]] = None) -> None:
    try:
        from sovereign_agent.events import emit_event
        emit_event(flag, plane="control", trace_id=trace_id, payload=payload or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("request event %s failed: %r", flag, exc)


@dataclass
class HumanRequest:
    request_id: str
    kind: str
    title: str
    body: str = ""
    status: str = "open"
    created_at: str = ""
    answered_at: str = ""
    answer: str = ""
    workflow_id: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def emoji(self) -> str:
        return KIND_EMOJI.get(self.kind, "📨")

    @property
    def status_emoji(self) -> str:
        return STATUS_EMOJI.get(self.status, "•")

    def one_line(self) -> str:
        sid = self.request_id[-6:]
        return f"{self.status_emoji} {self.emoji} [{sid}] {self.title}"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS human_requests (
    request_id   TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    title        TEXT NOT NULL,
    body         TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'open',
    created_at   TEXT NOT NULL,
    answered_at  TEXT NOT NULL DEFAULT '',
    answer       TEXT NOT NULL DEFAULT '',
    workflow_id  TEXT NOT NULL DEFAULT '',
    tags_json    TEXT NOT NULL DEFAULT '[]'
);
"""


def _row_to_request(row: Any) -> HumanRequest:
    return HumanRequest(
        request_id=row["request_id"], kind=row["kind"], title=row["title"],
        body=row["body"], status=row["status"], created_at=row["created_at"],
        answered_at=row["answered_at"], answer=row["answer"],
        workflow_id=row["workflow_id"],
        tags=json.loads(row["tags_json"] or "[]"),
    )


class RequestStore:
    """Durable home for the collaboration inbox. Creates its own table; does
    not touch the core schema."""

    def __init__(self, store: ErebloStore):
        self._store = store
        self._store.execute(_SCHEMA)

    # ── create ───────────────────────────────────────────────────────────
    def open(self, kind: str, title: str, *, body: str = "",
             workflow_id: str = "", tags: Optional[list[str]] = None) -> HumanRequest:
        if kind not in VALID_KINDS:
            kind = "note"
        req = HumanRequest(request_id=_new_id(), kind=kind, title=title,
                           body=body, status="open", created_at=_now(),
                           workflow_id=workflow_id, tags=tags or [])
        self._store.execute(
            "INSERT INTO human_requests(request_id, kind, title, body, status, "
            "created_at, answered_at, answer, workflow_id, tags_json) "
            "VALUES (?, ?, ?, ?, 'open', ?, '', '', ?, ?)",
            (req.request_id, req.kind, req.title, req.body, req.created_at,
             req.workflow_id, json.dumps(req.tags)))
        _emit("request-open-d", trace_id=req.request_id,
              payload={"kind": kind, "title": title, "emoji": req.emoji,
                       "workflow_id": workflow_id})
        return req

    # ── read ─────────────────────────────────────────────────────────────
    def get(self, request_id: str) -> Optional[HumanRequest]:
        # accept short ids (last 6 chars) for convenience
        row = self._store.query_one(
            "SELECT * FROM human_requests WHERE request_id = ?", (request_id,))
        if row is None and len(request_id) < 26:
            row = self._store.query_one(
                "SELECT * FROM human_requests WHERE request_id LIKE ? "
                "ORDER BY created_at DESC LIMIT 1", (f"%{request_id}",))
        return _row_to_request(row) if row else None

    def list(self, *, status: Optional[str] = None, limit: int = 100) -> list[HumanRequest]:
        if status:
            rows = self._store.query_all(
                "SELECT * FROM human_requests WHERE status = ? "
                "ORDER BY created_at DESC LIMIT ?", (status, limit))
        else:
            rows = self._store.query_all(
                "SELECT * FROM human_requests ORDER BY created_at DESC LIMIT ?",
                (limit,))
        return [_row_to_request(r) for r in rows]

    def list_open(self) -> list[HumanRequest]:
        return self.list(status="open")

    def open_count(self) -> int:
        row = self._store.query_one(
            "SELECT COUNT(*) AS n FROM human_requests WHERE status = 'open'")
        return int(row["n"]) if row else 0

    # ── transitions ──────────────────────────────────────────────────────
    def answer(self, request_id: str, text: str) -> Optional[HumanRequest]:
        req = self.get(request_id)
        if req is None:
            return None
        self._store.execute(
            "UPDATE human_requests SET status='answered', answer=?, answered_at=? "
            "WHERE request_id=?", (text, _now(), req.request_id))
        _emit("request-answered-d", trace_id=req.request_id,
              payload={"kind": req.kind, "title": req.title})
        return self.get(req.request_id)

    def resolve(self, request_id: str) -> Optional[HumanRequest]:
        req = self.get(request_id)
        if req is None:
            return None
        self._store.execute(
            "UPDATE human_requests SET status='resolved' WHERE request_id=?",
            (req.request_id,))
        _emit("request-resolved-d", trace_id=req.request_id,
              payload={"kind": req.kind, "title": req.title})
        return self.get(req.request_id)

    def cancel(self, request_id: str) -> Optional[HumanRequest]:
        req = self.get(request_id)
        if req is None:
            return None
        self._store.execute(
            "UPDATE human_requests SET status='cancelled' WHERE request_id=?",
            (req.request_id,))
        return self.get(req.request_id)

    def set_status(self, request_id: str, status: str) -> Optional[HumanRequest]:
        """Set an arbitrary (valid) status. Used by the named helpers below."""
        if status not in VALID_STATUS:
            raise ValueError(f"unknown status: {status!r}")
        req = self.get(request_id)
        if req is None:
            return None
        self._store.execute(
            "UPDATE human_requests SET status=? WHERE request_id=?",
            (status, req.request_id))
        _emit("request-status-d", trace_id=req.request_id,
              payload={"status": status, "title": req.title})
        return self.get(req.request_id)

    def defer(self, request_id: str) -> Optional[HumanRequest]:
        """Set aside for now (still on the board, not urgent). ⏸️"""
        return self.set_status(request_id, "deferred")

    def flag(self, request_id: str) -> Optional[HumanRequest]:
        """Flag as needing more attention. ⚠️"""
        return self.set_status(request_id, "needs_attention")

    def revisit(self, request_id: str) -> Optional[HumanRequest]:
        """Mark to come back to after more in-depth development. 🔖"""
        return self.set_status(request_id, "revisit")

    def reopen(self, request_id: str) -> Optional[HumanRequest]:
        """Return an item to the open queue."""
        return self.set_status(request_id, "open")


__all__ = ["HumanRequest", "RequestStore", "KIND_EMOJI", "STATUS_EMOJI",
           "VALID_KINDS", "VALID_STATUS"]
