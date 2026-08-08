"""
╔══════════════════════════════════════════════════════════════════════════╗
║  persistence/sessions.py — chat sessions as first-class objects         ║
║  v0.2.37 — skeleton drop                                                  ║
║                                                                           ║
║  Every chat gets a chat_id. The UI sidebar shows them. Aria reads        ║
║  history from them. Workflows reference them. Timers can bind to them.  ║
║                                                                           ║
║  Operations                                                              ║
║                                                                           ║
║    new_chat(title, project_id?)        — fresh chat, returns chat_id    ║
║    list_chats(status?)                  — sidebar query                  ║
║    open_chat(chat_id)                   — full record                   ║
║    append_message(chat_id, role, content, tags?, project_id?)           ║
║    recent_messages(chat_id, k)          — last K turns                  ║
║    summarize_chat(chat_id, summary)     — operator sets summary        ║
║    archive_chat(chat_id)                — status=archived               ║
║    rename_chat(chat_id, title)                                          ║
║    bind_to_project(chat_id, project_id) — link chat to a project       ║
║                                                                           ║
║  No magic. No LLM calls in this module. The "memory daemon" that         ║
║  auto-summarizes is a separate concern (queued for v0.2.38+); this     ║
║  module just provides honest CRUD for sessions.                        ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from ulid import ULID

from sovereign_agent.persistence.store import ErebloStore, _iso_now


ChatStatus = Literal["active", "archived"]
Role = Literal["user", "assistant", "system", "tool"]


# ─── Records ─────────────────────────────────────────────────────────────


@dataclass
class Chat:
    chat_id: str
    title: str
    project_id: Optional[str]
    status: ChatStatus
    summary: str
    created_at: str
    updated_at: str


@dataclass
class Message:
    message_id: str
    chat_id: str
    project_id: Optional[str]
    role: Role
    content: str
    tags: str
    created_at: str


# ─── Manager ─────────────────────────────────────────────────────────────


class ChatSessionsManager:
    """Owns the chats + messages tables. Construct once; share."""

    def __init__(self, store: ErebloStore):
        self._store = store

    # ─── Create / list / open ───────────────────────────────────────────

    def new_chat(self, title: str, project_id: Optional[str] = None) -> str:
        chat_id = str(ULID())
        now = _iso_now()
        self._store.execute(
            "INSERT INTO chats(chat_id, title, project_id, status, "
            "summary, created_at, updated_at) "
            "VALUES (?, ?, ?, 'active', '', ?, ?)",
            (chat_id, title, project_id, now, now),
        )
        return chat_id

    def list_chats(
        self,
        status: Optional[ChatStatus] = "active",
        project_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[Chat]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._store.query_all(
            f"SELECT * FROM chats {where} "
            f"ORDER BY updated_at DESC LIMIT ?",
            tuple(params + [limit]),
        )
        return [Chat(**dict(r)) for r in rows]

    def open_chat(self, chat_id: str) -> Optional[Chat]:
        row = self._store.query_one(
            "SELECT * FROM chats WHERE chat_id = ?", (chat_id,)
        )
        return Chat(**dict(row)) if row else None

    # ─── Mutations ──────────────────────────────────────────────────────

    def rename_chat(self, chat_id: str, new_title: str) -> None:
        self._store.execute(
            "UPDATE chats SET title = ?, updated_at = ? WHERE chat_id = ?",
            (new_title, _iso_now(), chat_id),
        )

    def summarize_chat(self, chat_id: str, summary: str) -> None:
        self._store.execute(
            "UPDATE chats SET summary = ?, updated_at = ? WHERE chat_id = ?",
            (summary, _iso_now(), chat_id),
        )

    def archive_chat(self, chat_id: str) -> None:
        self._store.execute(
            "UPDATE chats SET status = 'archived', updated_at = ? "
            "WHERE chat_id = ?",
            (_iso_now(), chat_id),
        )

    def reactivate_chat(self, chat_id: str) -> None:
        self._store.execute(
            "UPDATE chats SET status = 'active', updated_at = ? "
            "WHERE chat_id = ?",
            (_iso_now(), chat_id),
        )

    def bind_to_project(self, chat_id: str, project_id: Optional[str]) -> None:
        self._store.execute(
            "UPDATE chats SET project_id = ?, updated_at = ? WHERE chat_id = ?",
            (project_id, _iso_now(), chat_id),
        )

    # ─── Messages ───────────────────────────────────────────────────────

    def append_message(
        self,
        chat_id: str,
        role: Role,
        content: str,
        tags: str = "",
        project_id: Optional[str] = None,
    ) -> str:
        message_id = str(ULID())
        now = _iso_now()
        # If project_id wasn't passed but the chat is bound to a project,
        # propagate that to the message for cheaper project-scoped queries.
        if project_id is None:
            chat = self.open_chat(chat_id)
            project_id = chat.project_id if chat else None
        self._store.execute(
            "INSERT INTO messages(message_id, chat_id, project_id, role, "
            "content, tags, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (message_id, chat_id, project_id, role, content, tags, now),
        )
        # Bump chat updated_at so list_chats sorts correctly.
        self._store.execute(
            "UPDATE chats SET updated_at = ? WHERE chat_id = ?",
            (now, chat_id),
        )
        return message_id

    def recent_messages(self, chat_id: str, k: int = 20) -> list[Message]:
        """Last K messages in this chat, chronological (oldest first)."""
        rows = self._store.query_all(
            "SELECT * FROM messages WHERE chat_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (chat_id, k),
        )
        return list(reversed([Message(**dict(r)) for r in rows]))

    def all_messages(self, chat_id: str) -> list[Message]:
        rows = self._store.query_all(
            "SELECT * FROM messages WHERE chat_id = ? "
            "ORDER BY created_at ASC",
            (chat_id,),
        )
        return [Message(**dict(r)) for r in rows]

    def message_count(self, chat_id: str) -> int:
        row = self._store.query_one(
            "SELECT COUNT(*) AS n FROM messages WHERE chat_id = ?", (chat_id,)
        )
        return int(row["n"]) if row else 0


__all__ = ["ChatSessionsManager", "Chat", "Message", "ChatStatus", "Role"]
