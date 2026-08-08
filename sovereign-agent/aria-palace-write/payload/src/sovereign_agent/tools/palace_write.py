"""
palace_write.py — Tier 1: write rooms, closets, and triples into palace.db

Palace is Aria's structured long-term memory: rooms → closets → triples.
The PalaceSearchTool (T0) already lets Aria read it. This module adds write
access so Aria can place what she discovers into the palace herself.

Three tools:
  palace_write_room    (T1) — create a themed container (room)
  palace_write_closet  (T1) — create a topic index inside a room
  palace_write_triple  (T1) — assert a typed fact about named entities

IDs follow the palace_mining convention: slugified names + content hashes.
Subject/object entities are upserted automatically — no manual entity setup.

Design invariants:
  - No embedding computed here (no Ollama dep); closets are keyword-only
  - INSERT OR REPLACE so re-runs are idempotent
  - close() palace after every operation (WAL-safe; no long-held locks)
  - Never edit existing triples: use invalidate_triple for corrections
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


# ─── helpers ────────────────────────────────────────────────────────────────


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _slugify(text: str, max_len: int = 48) -> str:
    norm = re.sub(r"\s+", "-", text.strip().lower())
    norm = re.sub(r"[^a-z0-9\-]", "", norm)
    return norm[:max_len] or "unnamed"


def _entity_id(name: str) -> str:
    norm = _slugify(name, 40)
    suffix = hashlib.sha256(name.encode()).hexdigest()[:6]
    return f"entity-{norm}-{suffix}"


def _triple_id(subject_id: str, predicate: str, object_repr: str) -> str:
    raw = f"{subject_id}|{predicate}|{object_repr}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"triple-{h}"


def _closet_id(room_id: str, topic: str) -> str:
    h = hashlib.sha256(f"{room_id}|{topic}".encode()).hexdigest()[:12]
    return f"closet-tool-{h}"


def _open_palace():
    from sovereign_agent.palace import open_palace
    return open_palace()


# ─── PalaceWriteRoomTool ─────────────────────────────────────────────────────


class PalaceWriteRoomTool(Tool):
    """Create a new palace room (themed container for closets and triples).

    A room is a namespace for related knowledge — e.g. 'projects', 'code',
    'research', 'kevin', 'calendar'. If a room with this name already exists
    (same slugified id), the call is idempotent and returns ok=True.

    Args:
      name        — human-readable room name (e.g. "Kevin's Projects")
      description — what this room holds (optional but helpful for search)
      room_id     — override the auto-generated slug (advanced; optional)

    FAILURE MODES: palace_unavailable, room_already_exists (non-fatal),
      invalid_name, db_error.
    """

    name = "palace_write_room"
    tier = 1
    description = (
        "Create a new palace room (a named container for structured knowledge). "
        "Args: name (str), description (str, optional), room_id (str slug, optional). "
        "Idempotent — if the room already exists, returns ok=True with existing id. "
        "FAILURE MODES: palace_unavailable, invalid_name, db_error."
    )
    failure_modes = ("palace_unavailable", "invalid_name", "db_error")

    class Args(BaseModel):
        name: str = Field(description="Human-readable room name.")
        description: str = Field(default="", description="What this room holds.")
        room_id: str = Field(
            default="",
            description="Optional slug override. Auto-generated from name if empty.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        if not args.name.strip():
            return ToolResult(ok=False, error="name must not be empty")

        rid = args.room_id.strip() or f"room-{_slugify(args.name)}"

        try:
            palace = _open_palace()
        except Exception as exc:
            return ToolResult(ok=False, error=f"palace unavailable: {exc!r}")

        try:
            # Check if already exists
            try:
                existing = palace.get_room(rid)
                palace.close()
                return ToolResult(
                    ok=True,
                    output=f"Room already exists: {existing.id!r} — {existing.name}",
                    metadata={"room_id": existing.id, "existed": True},
                )
            except Exception:
                pass  # RoomNotFound — proceed to create

            room = palace.create_room(
                room_id=rid,
                name=args.name,
                description=args.description,
            )
            return ToolResult(
                ok=True,
                output=f"Room created: {room.id!r}\n  name: {room.name}\n  description: {room.description or '(none)'}",
                metadata={"room_id": room.id, "existed": False},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"db error: {exc!r}")
        finally:
            palace.close()


# ─── PalaceWriteClosetTool ───────────────────────────────────────────────────


class PalaceWriteClosetTool(Tool):
    """Create a topic index closet inside a palace room.

    A closet groups a topic with related entity names. It serves as a fast
    keyword index that points to deeper atoms. No embedding is computed here
    (keyword-only). The closet is idempotent via INSERT OR REPLACE.

    Args:
      room_id  — the room this closet belongs to (must exist)
      topic    — one-sentence topic descriptor (e.g. "Kevin's core values")
      entities — list of named entities this closet references (optional)

    FAILURE MODES: palace_unavailable, room_not_found, invalid_topic, db_error.
    """

    name = "palace_write_closet"
    tier = 1
    description = (
        "Create a topic-index closet inside an existing palace room. "
        "Args: room_id (str), topic (str), entities (list[str], optional). "
        "Idempotent. FAILURE MODES: palace_unavailable, room_not_found, invalid_topic, db_error."
    )
    failure_modes = ("palace_unavailable", "room_not_found", "invalid_topic", "db_error")

    class Args(BaseModel):
        room_id: str = Field(description="Palace room slug (e.g. 'room-projects').")
        topic: str = Field(description="One-sentence topic for this closet.")
        entities: list[str] = Field(
            default_factory=list,
            description="Named entities referenced by this closet.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        if not args.room_id.strip():
            return ToolResult(ok=False, error="room_id must not be empty")
        if not args.topic.strip():
            return ToolResult(ok=False, error="topic must not be empty")

        try:
            palace = _open_palace()
        except Exception as exc:
            return ToolResult(ok=False, error=f"palace unavailable: {exc!r}")

        try:
            from sovereign_agent.palace import RoomNotFound

            # Validate room exists
            try:
                palace.get_room(args.room_id)
            except RoomNotFound:
                return ToolResult(
                    ok=False,
                    error=f"room {args.room_id!r} not found — call palace_write_room first",
                )

            closet_id = _closet_id(args.room_id, args.topic)

            from sovereign_agent.palace import Closet
            closet = Closet(
                id=closet_id,
                room_id=args.room_id,
                topic=args.topic,
                entities=list(args.entities),
            )
            palace.add_closet(closet)

            ent_list = ", ".join(args.entities) if args.entities else "(none)"
            return ToolResult(
                ok=True,
                output=(
                    f"Closet written: {closet_id}\n"
                    f"  room: {args.room_id}\n"
                    f"  topic: {args.topic}\n"
                    f"  entities: {ent_list}"
                ),
                metadata={"closet_id": closet_id, "room_id": args.room_id},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"db error: {exc!r}")
        finally:
            palace.close()


# ─── PalaceWriteTripleTool ───────────────────────────────────────────────────


class PalaceWriteTripleTool(Tool):
    """Assert a typed fact (triple) into the palace knowledge graph.

    A triple is: subject → predicate → object, where subject and object are
    named entities (or object can be a literal string value). Both subject and
    object entities are upserted automatically — you don't need to pre-create
    them.

    Use object_entity for links between named things:
      subject="Aria", predicate="maintained_by", object_entity="Kevin"

    Use object_literal for attribute-style facts:
      subject="Aria", predicate="kernel", object_literal="Safety·Love·Flourishing"

    Triple IDs are content-addressed (subject+predicate+object) so the same
    fact is idempotent. To correct a triple, write a new one and set valid_to
    on the old one via sov palace invalidate.

    Args:
      subject        — name of the subject entity
      predicate      — relationship or attribute name
      object_entity  — name of the object entity (use when object is a thing)
      object_literal — literal value string (use when object is a value)
      subject_type   — entity type for subject (default: 'unknown')
      object_type    — entity type for object entity (default: 'unknown')
      confidence     — 0.0–1.0 (default: 1.0)
      valid_from     — ISO date when this fact became true (optional)

    FAILURE MODES: palace_unavailable, constraint_error, db_error.
    """

    name = "palace_write_triple"
    tier = 1
    description = (
        "Assert a typed fact (subject → predicate → object) into the palace knowledge graph. "
        "Args: subject (str), predicate (str), object_entity (str, optional) OR "
        "object_literal (str, optional) — exactly one required. "
        "subject_type, object_type, confidence (float 0-1), valid_from (ISO date). "
        "Entities are auto-created. Idempotent. "
        "FAILURE MODES: palace_unavailable, constraint_error, db_error."
    )
    failure_modes = ("palace_unavailable", "constraint_error", "db_error")

    class Args(BaseModel):
        subject: str = Field(description="Name of the subject entity.")
        predicate: str = Field(description="Relationship or attribute (snake_case recommended).")
        object_entity: str = Field(
            default="",
            description="Name of object entity (use when object is a named thing).",
        )
        object_literal: str = Field(
            default="",
            description="Literal string value (use when object is a value, not a thing).",
        )
        subject_type: str = Field(default="unknown", description="Entity type for subject.")
        object_type: str = Field(default="unknown", description="Entity type for object entity.")
        confidence: float = Field(default=1.0, ge=0.0, le=1.0)
        valid_from: str = Field(default="", description="ISO date when fact became true (optional).")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        has_entity = bool(args.object_entity.strip())
        has_literal = bool(args.object_literal.strip())

        if has_entity == has_literal:
            return ToolResult(
                ok=False,
                error="exactly one of object_entity or object_literal must be set",
            )
        if not args.subject.strip():
            return ToolResult(ok=False, error="subject must not be empty")
        if not args.predicate.strip():
            return ToolResult(ok=False, error="predicate must not be empty")

        try:
            palace = _open_palace()
        except Exception as exc:
            return ToolResult(ok=False, error=f"palace unavailable: {exc!r}")

        try:
            from sovereign_agent.palace import Entity, Triple

            now = _utc_now()

            # Upsert subject entity
            subj_id = _entity_id(args.subject)
            palace.upsert_entity(Entity(
                id=subj_id,
                name=args.subject,
                type=args.subject_type,
                first_seen=now,
                last_seen=now,
            ))

            # Upsert object entity if needed
            obj_id: str | None = None
            obj_literal: str | None = None

            if has_entity:
                obj_id = _entity_id(args.object_entity)
                palace.upsert_entity(Entity(
                    id=obj_id,
                    name=args.object_entity,
                    type=args.object_type,
                    first_seen=now,
                    last_seen=now,
                ))
                object_repr = args.object_entity
            else:
                obj_literal = args.object_literal
                object_repr = args.object_literal

            triple_id = _triple_id(subj_id, args.predicate, object_repr)

            triple = Triple(
                id=triple_id,
                subject_id=subj_id,
                predicate=args.predicate,
                object_id=obj_id,
                object_literal=obj_literal,
                confidence=args.confidence,
                valid_from=args.valid_from or None,
                source_atom_ids=[],
                created_at=now,
            )
            palace.add_triple(triple)

            obj_desc = (
                f"→ entity: {args.object_entity}" if has_entity
                else f"= {args.object_literal!r}"
            )
            conf_pct = f"{args.confidence * 100:.0f}%"

            return ToolResult(
                ok=True,
                output=(
                    f"Triple written: {triple_id}\n"
                    f"  {args.subject} — {args.predicate} — {obj_desc}\n"
                    f"  confidence: {conf_pct}"
                    + (f"\n  valid from: {args.valid_from}" if args.valid_from else "")
                ),
                metadata={
                    "triple_id": triple_id,
                    "subject_id": subj_id,
                    "object_id": obj_id,
                    "predicate": args.predicate,
                },
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"db error: {exc!r}")
        finally:
            palace.close()
