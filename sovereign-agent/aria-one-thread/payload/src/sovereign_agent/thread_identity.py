"""thread_identity.py — one universal continuous conversation thread.

THE DECISION (Keys round, researched + chosen with Kevin, 2026-07-04):
Aria's identity layer (atoms/palace/lessons/honor/flaws) is already one
continuous life — but her CONVERSATION layer was four unlinked id-spaces,
and the checkpoint-chunk recorder minted a fresh `cockpit-<uuid4>` every
launch, orphaning the prior launch's chunks. Closing the cockpit kept her
soul and lost the conversation, every time.

One universal continuous session fixes that with the smallest honest diff:
  - `thread_id()` — the ONE persisted conversation-thread id
    (`data_dir/thread_id`, default "aria-main"), created on first read.
    Every launch's chunks now land in the same addressable thread; the
    transcript and (K4's) sessions carry the same id — one join key.
  - `restore_tail(n_turns)` — the last N verbatim turns from the thread's
    sealed chunks, for the wake restore ("──── earlier, from our thread
    ────" above the greeting). Chunks are non-lossy by design (Workstream
    P), which is exactly what makes a byte-true restore possible.

Named sessions remain an optional future overlay (the dormant Ereblo
`chats` schema is built for that day); folder/project scoping stays
reserved for genuine folder work. One relationship, one thread.
"""
from __future__ import annotations

from pathlib import Path

DEFAULT_THREAD_ID = "aria-main"


def thread_id(data_dir: Path | None = None) -> str:
    """The persisted conversation-thread id. Created on first read.
    Never raises — falls back to the default in-memory on any I/O error."""
    try:
        if data_dir is None:
            from sovereign_agent.config import SETTINGS

            data_dir = SETTINGS.paths.data_dir
        path = Path(data_dir) / "thread_id"
        if path.exists():
            existing = path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_THREAD_ID + "\n", encoding="utf-8")
    except OSError:
        pass
    return DEFAULT_THREAD_ID


def restore_tail(n_turns: int = 30, data_dir: Path | None = None) -> list[dict]:
    """The last ``n_turns`` verbatim turns of the thread, oldest first —
    [{role, content, ts}, ...]. Empty list on any failure (fresh install,
    unapplied chunks module): the wake restore is a gift, never a boot
    blocker."""
    try:
        from sovereign_agent.checkpoint_chunks import ChunkStore

        store = ChunkStore(
            (Path(data_dir) / "checkpoint_chunks") if data_dir is not None else None
        )
        chunks = store.all_chunks(session_id=thread_id(data_dir))
        turns: list[dict] = []
        for chunk in chunks:
            turns.extend(chunk.raw_turns)
        return turns[-max(0, n_turns):]
    except Exception:  # noqa: BLE001
        return []
