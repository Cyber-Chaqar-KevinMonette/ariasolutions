"""index.py — ChunkIndex: a topic/keyword index over sealed chunks.

Generalizes palace.py's Closet pattern (topic -> pointer list of atom_ids)
into "topic/keyword -> pointer list of chunk_ids" — the literal mechanism
for "call on those chunks when it is required of her." Deliberately
self-contained (no dependency on Palace's SQLite Room/Entity/Triple
machinery) so chunk storage stays lightweight and independently testable;
the pattern is reused, not the implementation.
"""
from __future__ import annotations

from .store import ChunkRecord, ChunkStore


class ChunkIndex:
    """Read-side lookup over a ChunkStore. Builds nothing new on disk —
    it's a query layer over chunks.ndjson, always current."""

    def __init__(self, store: ChunkStore | None = None) -> None:
        self.store = store or ChunkStore()

    def find_by_topic(self, tag: str) -> list[ChunkRecord]:
        """Chunks explicitly tagged with this topic."""
        tag = tag.strip().lstrip("#").lower()
        return [
            c for c in self.store.all_chunks()
            if tag in (t.lower() for t in c.topic_tags)
        ]

    def find_by_keyword(self, keyword: str, *, session_id: str | None = None) -> list[ChunkRecord]:
        """Chunks whose raw turn content contains this keyword
        (case-insensitive substring match) — the actual "call on this chunk
        when you know you need it" mechanism. Precision-first, like D's
        path_scan: a plain substring match never invents a false positive
        the way a fuzzy/semantic match could."""
        keyword = keyword.strip().lower()
        if not keyword:
            return []
        out = []
        for c in self.store.all_chunks(session_id=session_id):
            if any(keyword in turn.get("content", "").lower() for turn in c.raw_turns):
                out.append(c)
        return out

    def find_by_turn(self, session_id: str, turn_number: int) -> ChunkRecord | None:
        """Which chunk (if any) covers a given turn number in a session."""
        for c in self.store.all_chunks(session_id=session_id):
            if c.turn_start <= turn_number <= c.turn_end:
                return c
        return None
