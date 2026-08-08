"""checkpoint_chunks — Workstream P: god-tier conversation checkpoint chunks,
an anti-compression system.

Kevin's ask: Aria should be able to save conversation segments as
addressable "checkpoint chunks" she can call on when she needs them, so
that lossy compression is needed a lot less than typical AI systems require.
She can still compress whenever she wants — the point is that she shouldn't
*have to*, because full-fidelity detail stays reachable another way.

Composes existing patterns rather than inventing new architecture:
  - the atomic-write NDJSON idiom from ApplyQueueStore/EpistemicLedger
    (Workstreams C/H3) — ChunkStore.
  - palace.py's Closet (topic -> pointer list) indirection, generalized
    into ChunkIndex.
  - the RetrieveMemoryTool/MemorySearchTool tool-exposure pattern — the
    template for RecallChunkTool, just pointed at chunks instead of atoms.

Three pieces:
  store.py     — ChunkStore: seals bounded, non-lossy chunks of raw turns.
  index.py     — ChunkIndex: topic/keyword lookup over sealed chunks.
  recorder.py  — ChunkRecorder: buffers turns, auto-seals every N turns.
"""
from __future__ import annotations

from .index import ChunkIndex
from .recorder import ChunkRecorder, DEFAULT_CHUNK_SIZE
from .store import ChunkRecord, ChunkStore, Turn

__all__ = [
    "ChunkStore",
    "ChunkRecord",
    "Turn",
    "ChunkIndex",
    "ChunkRecorder",
    "DEFAULT_CHUNK_SIZE",
]
