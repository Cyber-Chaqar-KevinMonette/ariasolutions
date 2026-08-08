"""recorder.py — ChunkRecorder: buffers live turns and auto-seals a chunk
every N turns (or on explicit request). This is the piece that actually
wires a real conversation surface (the cockpit's chat, or any other
per-turn hook) into ChunkStore — every turn is captured verbatim as it
happens, sealed in bounded groups rather than kept only in a live,
eventually-truncated scrollback.
"""
from __future__ import annotations

from .store import ChunkRecord, ChunkStore, Turn

DEFAULT_CHUNK_SIZE = 20  # turns per sealed chunk


class ChunkRecorder:
    """One recorder per live session. Call `record_turn()` for every turn;
    it auto-seals into the backing ChunkStore every `chunk_size` turns."""

    def __init__(
        self, session_id: str, *, store: ChunkStore | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        self.session_id = session_id
        self.store = store or ChunkStore()
        self.chunk_size = max(1, chunk_size)
        self._buffer: list[Turn] = []
        self._turn_count = 0

    def record_turn(self, role: str, content: str) -> ChunkRecord | None:
        """Record one turn. Returns the sealed ChunkRecord if this turn
        triggered an auto-seal, else None."""
        self._buffer.append(Turn(role=role, content=content))
        self._turn_count += 1
        if len(self._buffer) >= self.chunk_size:
            return self.seal_now()
        return None

    def seal_now(self, *, topic_tags: list[str] | None = None) -> ChunkRecord | None:
        """Force-seal whatever is currently buffered (even if under
        chunk_size) — used for an explicit checkpoint request, or to flush
        a partial buffer at session end so nothing is silently lost."""
        if not self._buffer:
            return None
        turn_start = self._turn_count - len(self._buffer) + 1
        turn_end = self._turn_count
        record = self.store.seal_chunk(
            self.session_id, list(self._buffer), turn_start, turn_end,
            topic_tags=topic_tags,
        )
        self._buffer.clear()
        return record

    @property
    def pending_turn_count(self) -> int:
        return len(self._buffer)
