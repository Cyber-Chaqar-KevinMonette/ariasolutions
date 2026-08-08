"""store.py — ChunkStore: seals bounded, addressable, NON-LOSSY chunks of
raw conversation turns. Append-only NDJSON with atomic writes, mirroring
ApplyQueueStore's (Workstream C) and EpistemicLedger's (Workstream H3)
exact idiom: write a line, fsync, never rewrite history.

Sealing is the non-lossy analog of compressing: nothing is condensed or
summarized here — a chunk is moved out of live scrollback into a durable,
addressable record, verbatim. Compare with compression.py's
`compress_events()`, which produces a lossy summary; a chunk produces zero
information loss, just indirection.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class Turn:
    role: str
    content: str
    ts: str = field(default_factory=_now)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChunkRecord:
    chunk_id: str
    session_id: str
    turn_start: int
    turn_end: int
    sealed_at: str
    topic_tags: list[str] = field(default_factory=list)
    raw_turns: list[dict] = field(default_factory=list)  # [{role, content, ts}, ...]

    def as_dict(self) -> dict:
        return asdict(self)

    def text(self) -> str:
        """The verbatim, reconstructed text of every turn in this chunk —
        exactly what RecallChunkTool hands back, never a summary."""
        return "\n".join(f"[{t['role']}] {t['content']}" for t in self.raw_turns)


class ChunkStore:
    """Append-only NDJSON store of sealed chunks. Mirrors ApplyQueueStore's
    and EpistemicLedger's atomic-write discipline exactly."""

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            from sovereign_agent.config import SETTINGS
            root = SETTINGS.paths.data_dir / "checkpoint_chunks"
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.log = self.root / "chunks.ndjson"

    def _append(self, record: ChunkRecord) -> None:
        line = json.dumps(record.as_dict(), separators=(",", ":")) + "\n"
        with open(self.log, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def seal_chunk(
        self, session_id: str, turns: list[Turn], turn_start: int, turn_end: int,
        *, topic_tags: list[str] | None = None,
    ) -> ChunkRecord:
        """Seal a bounded span of raw turns into one addressable, non-lossy
        chunk. Nothing is condensed — every turn's full content is kept."""
        record = ChunkRecord(
            chunk_id=_new_id("chunk"), session_id=session_id,
            turn_start=turn_start, turn_end=turn_end, sealed_at=_now(),
            topic_tags=list(topic_tags or []),
            raw_turns=[t.as_dict() for t in turns],
        )
        self._append(record)
        return record

    def all_chunks(self, *, session_id: str | None = None) -> list[ChunkRecord]:
        """Every sealed chunk ever recorded, oldest first — full fidelity,
        nothing hidden."""
        out: list[ChunkRecord] = []
        if not self.log.exists():
            return out
        for raw in self.log.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                record = ChunkRecord(**json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue
            if session_id is not None and record.session_id != session_id:
                continue
            out.append(record)
        return out

    def get_chunk(self, chunk_id: str) -> ChunkRecord | None:
        for record in self.all_chunks():
            if record.chunk_id == chunk_id:
                return record
        return None
