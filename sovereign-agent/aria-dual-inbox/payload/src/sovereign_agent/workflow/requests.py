"""
╔══════════════════════════════════════════════════════════════════════════╗
║  requests.py — the collaboration inbox  📬                                 ║
║                                                                            ║
║  A two-way work queue between Aria and her human. Aria posts the things    ║
║  she needs to move forward and the human answers. Nothing is logged        ║
║  without meaning: every request can carry the WHAT (title + body), the     ║
║  WHY (rationale), the WHEN (revisit_when / revisit_at), a priority, an      ║
║  estimate, and any number of tags — so when you see a task, a label, and   ║
║  an id, you also see what it is, why it's here, and when to act on it.     ║
║                                                                            ║
║  Items move open → answered → resolved, and can also be parked as          ║
║  deferred ⏸️ / revisit 🔖 / needs_attention ⚠️ — each carrying the context  ║
║  for why it was parked and when to come back. Re-addressing parked work is ║
║  one command: `parked`, `due`, `reopen`.                                   ║
║                                                                            ║
║  Pairs with the authority gate: a paused run files a request here.         ║
║  Collaboration, not control — asks and answers between two people, logged. ║
║                                                                            ║
║  `direction` (v0.2.39.0, Workstream O): every request flows ONE way,       ║
║  `to_human` (Aria → Kevin, the original and default meaning of every row   ║
║  ever written before this field existed) or `to_aria` (Kevin → Aria, new — ║
║  a durable note she reads at a safe checkpoint, not mid-conversation).     ║
║  Two inboxes, one store: filter by direction instead of duplicating        ║
║  infrastructure.                                                          ║
║                                                                            ║
║  v0.2.39.0                                                                 ║
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
    "celebrate": "🎉", "research": "📚",
}
STATUS_EMOJI = {
    "open": "🟡", "answered": "🟢", "resolved": "✅", "cancelled": "⚪",
    "deferred": "⏸️", "needs_attention": "⚠️", "revisit": "🔖",
}
PRIORITY_EMOJI = {
    "low": "🔽", "normal": "▪️", "high": "🔼", "urgent": "🔴",
}
# Higher number = more urgent (used for ordering the open queue).
PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2, "urgent": 3}

VALID_KINDS = frozenset(KIND_EMOJI)
VALID_STATUS = frozenset(STATUS_EMOJI)
VALID_PRIORITY = frozenset(PRIORITY_EMOJI)

# Statuses that mean "parked — come back to this later".
PARKED_STATUSES = ("deferred", "revisit", "needs_attention")

# Who a request flows TO. Every row ever written before this field existed
# means "Aria posted this for the human" — so "to_human" is the default,
# preserving every existing row's meaning exactly (a migration, not a
# breaking change).
DIRECTION_TO_HUMAN = "to_human"
DIRECTION_TO_ARIA = "to_aria"
VALID_DIRECTIONS = frozenset({DIRECTION_TO_HUMAN, DIRECTION_TO_ARIA})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    try:
        from ulid import ULID
        return str(ULID())
    except Exception:  # noqa: BLE001
        import uuid
        return uuid.uuid4().hex


def _parse_dt(s: str) -> Optional[datetime]:
    """Best-effort ISO-8601 parse. Returns None on anything unparseable so a
    bad date never crashes scheduling."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


def _emit(flag: str, *, trace_id: str, payload: Optional[dict[str, Any]] = None) -> None:
    try:
        from sovereign_agent.events import emit_event
        emit_event(flag, plane="control", trace_id=trace_id, payload=payload or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("request event %s failed: %r", flag, exc)


def _norm_tags(tags: Any) -> list[str]:
    """Coerce tags input into a clean list[str] of distinct, stripped tokens."""
    if not tags:
        return []
    if isinstance(tags, str):
        tags = [tags]
    out: list[str] = []
    for t in tags:
        t = str(t).strip().lstrip("#").strip()
        if t and t not in out:
            out.append(t)
    return out


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
    # ── context (the "why / when / foresight" the human asked for) ──
    rationale: str = ""        # WHY — the reasoning behind this request/decision
    revisit_when: str = ""     # WHEN — free text: a date, a phase, a condition
    revisit_at: str = ""       # optional ISO datetime → enables "due" surfacing
    priority: str = "normal"   # low | normal | high | urgent
    estimate: str = ""         # effort / prediction / estimation
    # ── direction (Workstream O) ──
    direction: str = DIRECTION_TO_HUMAN   # to_human | to_aria

    @property
    def emoji(self) -> str:
        return KIND_EMOJI.get(self.kind, "📨")

    @property
    def status_emoji(self) -> str:
        return STATUS_EMOJI.get(self.status, "•")

    @property
    def priority_emoji(self) -> str:
        return PRIORITY_EMOJI.get(self.priority, "")

    @property
    def short_id(self) -> str:
        return self.request_id[-6:]

    @property
    def is_parked(self) -> bool:
        return self.status in PARKED_STATUSES

    @property
    def is_due(self) -> bool:
        """True if parked with a revisit_at that has arrived."""
        if not self.is_parked:
            return False
        at = _parse_dt(self.revisit_at)
        return at is not None and at <= datetime.now(timezone.utc)

    def one_line(self) -> str:
        pri = f"{self.priority_emoji} " if self.priority != "normal" else ""
        return f"{self.status_emoji} {self.emoji} {pri}[{self.short_id}] {self.title}"

    def context_lines(self) -> list[str]:
        """Dim detail lines for rendering (what/why/when/estimate/tags)."""
        lines: list[str] = []
        if self.rationale:
            lines.append(f"why: {self.rationale}")
        if self.revisit_when:
            lines.append(f"when: {self.revisit_when}")
        if self.estimate:
            lines.append(f"estimate: {self.estimate}")
        if self.tags:
            lines.append("tags: " + " ".join(f"#{t}" for t in self.tags))
        return lines


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
    tags_json    TEXT NOT NULL DEFAULT '[]',
    rationale    TEXT NOT NULL DEFAULT '',
    revisit_when TEXT NOT NULL DEFAULT '',
    revisit_at   TEXT NOT NULL DEFAULT '',
    priority     TEXT NOT NULL DEFAULT 'normal',
    estimate     TEXT NOT NULL DEFAULT '',
    direction    TEXT NOT NULL DEFAULT 'to_human'
);
"""

# Columns added after v0.2.36.0 — migrated in on existing tables (ADD COLUMN).
_ADDED_COLUMNS = (
    ("rationale", "TEXT NOT NULL DEFAULT ''"),
    ("revisit_when", "TEXT NOT NULL DEFAULT ''"),
    ("revisit_at", "TEXT NOT NULL DEFAULT ''"),
    ("priority", "TEXT NOT NULL DEFAULT 'normal'"),
    ("estimate", "TEXT NOT NULL DEFAULT ''"),
    # v0.2.39.0 (Workstream O) — default 'to_human' preserves every existing
    # row's original meaning exactly (Aria posted it, human answers it).
    ("direction", "TEXT NOT NULL DEFAULT 'to_human'"),
)


def _col(row: Any, key: str, default: Any = "") -> Any:
    """Read a column with a default if the row predates it (defensive)."""
    try:
        return row[key] if key in row.keys() else default
    except Exception:  # noqa: BLE001
        try:
            return row[key]
        except Exception:  # noqa: BLE001
            return default


def _row_to_request(row: Any) -> HumanRequest:
    return HumanRequest(
        request_id=row["request_id"], kind=row["kind"], title=row["title"],
        body=row["body"], status=row["status"], created_at=row["created_at"],
        answered_at=row["answered_at"], answer=row["answer"],
        workflow_id=row["workflow_id"],
        tags=json.loads(_col(row, "tags_json", "[]") or "[]"),
        rationale=_col(row, "rationale", ""),
        revisit_when=_col(row, "revisit_when", ""),
        revisit_at=_col(row, "revisit_at", ""),
        priority=_col(row, "priority", "normal") or "normal",
        estimate=_col(row, "estimate", ""),
        direction=_col(row, "direction", "to_human") or "to_human",
    )


class RequestStore:
    """Durable home for the collaboration inbox. Creates its own table and
    migrates in new columns; never touches the core schema."""

    def __init__(self, store: ErebloStore):
        self._store = store
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        # Fresh DBs get the full table; existing ones get the no-op CREATE.
        self._store.execute(_SCHEMA)
        # Migrate older tables: add any column they're missing. Idempotent.
        try:
            cols = {r["name"] for r in
                    self._store.query_all("PRAGMA table_info(human_requests)")}
        except Exception as exc:  # noqa: BLE001
            logger.debug("table_info failed: %r", exc)
            return
        for name, decl in _ADDED_COLUMNS:
            if name not in cols:
                try:
                    self._store.execute(
                        f"ALTER TABLE human_requests ADD COLUMN {name} {decl}")
                except Exception as exc:  # noqa: BLE001
                    logger.debug("add column %s failed: %r", name, exc)

    # ── create ───────────────────────────────────────────────────────────
    def open(self, kind: str, title: str, *, body: str = "",
             workflow_id: str = "", tags: Optional[list[str]] = None,
             rationale: str = "", revisit_when: str = "", revisit_at: str = "",
             priority: str = "normal", estimate: str = "",
             direction: str = DIRECTION_TO_HUMAN) -> HumanRequest:
        if kind not in VALID_KINDS:
            kind = "note"
        if priority not in VALID_PRIORITY:
            priority = "normal"
        if direction not in VALID_DIRECTIONS:
            direction = DIRECTION_TO_HUMAN
        req = HumanRequest(
            request_id=_new_id(), kind=kind, title=title, body=body,
            status="open", created_at=_now(), workflow_id=workflow_id,
            tags=_norm_tags(tags), rationale=rationale,
            revisit_when=revisit_when, revisit_at=revisit_at,
            priority=priority, estimate=estimate, direction=direction)
        self._store.execute(
            "INSERT INTO human_requests(request_id, kind, title, body, status, "
            "created_at, answered_at, answer, workflow_id, tags_json, "
            "rationale, revisit_when, revisit_at, priority, estimate, direction) "
            "VALUES (?, ?, ?, ?, 'open', ?, '', '', ?, ?, ?, ?, ?, ?, ?, ?)",
            (req.request_id, req.kind, req.title, req.body, req.created_at,
             req.workflow_id, json.dumps(req.tags), req.rationale,
             req.revisit_when, req.revisit_at, req.priority, req.estimate,
             req.direction))
        _emit("request-open-d", trace_id=req.request_id,
              payload={"kind": kind, "title": title, "emoji": req.emoji,
                       "priority": priority, "tags": req.tags,
                       "workflow_id": workflow_id, "direction": direction})
        return req

    # ── read ─────────────────────────────────────────────────────────────
    def get(self, request_id: str) -> Optional[HumanRequest]:
        if not request_id:
            return None
        row = self._store.query_one(
            "SELECT * FROM human_requests WHERE request_id = ?", (request_id,))
        if row is None and len(request_id) < 26:
            row = self._store.query_one(
                "SELECT * FROM human_requests WHERE request_id LIKE ? "
                "ORDER BY created_at DESC LIMIT 1", (f"%{request_id}",))
        return _row_to_request(row) if row else None

    def list(self, *, status: Optional[str] = None, kind: Optional[str] = None,
             tag: Optional[str] = None, direction: Optional[str] = None,
             limit: int = 100) -> list[HumanRequest]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?"); params.append(status)
        if kind:
            clauses.append("kind = ?"); params.append(kind)
        if direction:
            clauses.append("direction = ?"); params.append(direction)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        # Over-fetch a little when tag-filtering since tags live in JSON.
        sql_limit = limit * 4 if tag else limit
        params.append(sql_limit)
        rows = self._store.query_all(
            f"SELECT * FROM human_requests{where} "
            f"ORDER BY created_at DESC LIMIT ?", tuple(params))
        items = [_row_to_request(r) for r in rows]
        if tag:
            tag = tag.strip().lstrip("#")
            items = [r for r in items if tag in r.tags][:limit]
        return items

    def list_open(self, *, direction: Optional[str] = None) -> list[HumanRequest]:
        """Open items, most-urgent first then oldest-first within a priority."""
        items = self.list(status="open", direction=direction, limit=500)
        items.sort(key=lambda r: (-PRIORITY_RANK.get(r.priority, 1), r.created_at))
        return items

    def open_count(self, *, direction: Optional[str] = None) -> int:
        if direction:
            row = self._store.query_one(
                "SELECT COUNT(*) AS n FROM human_requests "
                "WHERE status = 'open' AND direction = ?", (direction,))
        else:
            row = self._store.query_one(
                "SELECT COUNT(*) AS n FROM human_requests WHERE status = 'open'")
        return int(row["n"]) if row else 0

    def next_open(self) -> Optional[HumanRequest]:
        """The single most pressing open request (for `requests next`)."""
        items = self.list_open()
        return items[0] if items else None

    def parked(self) -> list[HumanRequest]:
        """Everything set aside to come back to: deferred, revisit, flagged.
        Due items (revisit_at reached) sort to the top."""
        items: list[HumanRequest] = []
        for st in PARKED_STATUSES:
            items.extend(self.list(status=st, limit=500))
        items.sort(key=lambda r: (not r.is_due, r.revisit_at or "~", r.created_at))
        return items

    def due(self, now: Optional[datetime] = None) -> list[HumanRequest]:
        """Parked items whose revisit_at has arrived — ready to readdress."""
        now = now or datetime.now(timezone.utc)
        out = []
        for r in self.parked():
            at = _parse_dt(r.revisit_at)
            if at is not None and at <= now:
                out.append(r)
        return out

    # ── context update ─────────────────────────────────────────────────────
    def update_context(self, request_id: str, *, rationale: Optional[str] = None,
                        revisit_when: Optional[str] = None,
                        revisit_at: Optional[str] = None,
                        priority: Optional[str] = None,
                        estimate: Optional[str] = None,
                        tags: Optional[list[str]] = None) -> Optional[HumanRequest]:
        """Update only the provided context fields (None = leave unchanged)."""
        req = self.get(request_id)
        if req is None:
            return None
        sets, params = [], []
        if rationale is not None:
            sets.append("rationale = ?"); params.append(rationale)
        if revisit_when is not None:
            sets.append("revisit_when = ?"); params.append(revisit_when)
        if revisit_at is not None:
            sets.append("revisit_at = ?"); params.append(revisit_at)
        if priority is not None:
            if priority not in VALID_PRIORITY:
                raise ValueError(f"unknown priority: {priority!r}")
            sets.append("priority = ?"); params.append(priority)
        if estimate is not None:
            sets.append("estimate = ?"); params.append(estimate)
        if tags is not None:
            sets.append("tags_json = ?"); params.append(json.dumps(_norm_tags(tags)))
        if not sets:
            return req
        params.append(req.request_id)
        self._store.execute(
            f"UPDATE human_requests SET {', '.join(sets)} WHERE request_id = ?",
            tuple(params))
        return self.get(req.request_id)

    def add_tags(self, request_id: str, tags: list[str]) -> Optional[HumanRequest]:
        req = self.get(request_id)
        if req is None:
            return None
        merged = _norm_tags(list(req.tags) + _norm_tags(tags))
        return self.update_context(request_id, tags=merged)

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

    def _park(self, request_id: str, status: str, why: Optional[str],
              when: Optional[str], when_at: Optional[str]) -> Optional[HumanRequest]:
        """Park an item with optional context captured at the same moment."""
        if self.get(request_id) is None:
            return None
        if why is not None or when is not None or when_at is not None:
            self.update_context(request_id, rationale=why, revisit_when=when,
                                 revisit_at=when_at)
        return self.set_status(request_id, status)

    def defer(self, request_id: str, *, why: Optional[str] = None,
              when: Optional[str] = None, when_at: Optional[str] = None) -> Optional[HumanRequest]:
        """Set aside for now, optionally with why + when to come back. ⏸️"""
        return self._park(request_id, "deferred", why, when, when_at)

    def flag(self, request_id: str, *, why: Optional[str] = None) -> Optional[HumanRequest]:
        """Flag as needing more attention, optionally with why. ⚠️"""
        return self._park(request_id, "needs_attention", why, None, None)

    def revisit(self, request_id: str, *, why: Optional[str] = None,
                when: Optional[str] = None, when_at: Optional[str] = None) -> Optional[HumanRequest]:
        """Come back after more development/research, with why + when. 🔖"""
        return self._park(request_id, "revisit", why, when, when_at)

    def reopen(self, request_id: str) -> Optional[HumanRequest]:
        """Return a parked item to the open queue — re-addressing made trivial."""
        return self.set_status(request_id, "open")

    # ── direction-scoped convenience (Workstream O) ─────────────────────────
    def send_to_human(self, title: str, *, kind: str = "note", body: str = "",
                       rationale: str = "", tags: Optional[list[str]] = None,
                       priority: str = "normal") -> HumanRequest:
        """Aria → Kevin. The original, default meaning of every request ever
        written — named explicitly now that a second direction exists."""
        return self.open(kind, title, body=body, rationale=rationale,
                          tags=tags, priority=priority, direction=DIRECTION_TO_HUMAN)

    def tell_aria(self, title: str, *, body: str = "", tags: Optional[list[str]] = None,
                  priority: str = "normal") -> HumanRequest:
        """Kevin → Aria. A durable note she reads at a safe checkpoint (session
        start, or right after an autonomy-interval resume-approval), never
        interrupting mid-task."""
        return self.open("note", title, body=body, tags=tags, priority=priority,
                          direction=DIRECTION_TO_ARIA)

    def list_for_aria(self) -> list[HumanRequest]:
        """Open notes Kevin left for Aria — what ReadInboxTool surfaces."""
        return self.list_open(direction=DIRECTION_TO_ARIA)


__all__ = ["HumanRequest", "RequestStore", "KIND_EMOJI", "STATUS_EMOJI",
           "PRIORITY_EMOJI", "VALID_KINDS", "VALID_STATUS", "VALID_PRIORITY",
           "PARKED_STATUSES", "DIRECTION_TO_HUMAN", "DIRECTION_TO_ARIA",
           "VALID_DIRECTIONS"]
