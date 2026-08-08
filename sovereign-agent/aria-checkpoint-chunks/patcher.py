"""patcher.py — anchored, idempotent patches for Workstream P (checkpoint
chunks / anti-compression). Three targets, all span replacements against
the CURRENT live text — same discipline as O/M's patchers.
"""
from __future__ import annotations

MARK = "checkpoint-chunks-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. tools/__init__.py: import + __all__ (both in one patch, per the ────
#    lesson from L/H4 that a missing __all__ entry is a real bug class) ────

TOOLS_IMPORT_ANCHOR = 'from .inbox_tools import SendToHumanTool, ReadInboxTool  # dual-inbox-d\n'
TOOLS_ALL_ANCHOR = '    "ReadInboxTool",\n'


def patch_tools_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    if TOOLS_IMPORT_ANCHOR not in text:
        raise PatchError("tools/__init__.py: dual-inbox import anchor not found verbatim")
    if TOOLS_ALL_ANCHOR not in text:
        raise PatchError("tools/__init__.py: dual-inbox __all__ anchor not found verbatim")
    text = text.replace(
        TOOLS_IMPORT_ANCHOR,
        TOOLS_IMPORT_ANCHOR + f"from .recall_chunk_tool import RecallChunkTool  # {MARK}\n",
        1,
    )
    text = text.replace(
        TOOLS_ALL_ANCHOR,
        TOOLS_ALL_ANCHOR + f'    "RecallChunkTool",  # {MARK}\n',
        1,
    )
    return text, True


# ── 2. loop.py: retune the compression-oracle hint ──────────────────────────

ORACLE_ANCHOR = (
    "═══ COMPRESSION ORACLE ═══  # compression-oracle-d\n"
    "When a session grows long (>50 events or budget < 30%), check first:\n"
    "  context_stats()         → event count, opportunity score, tokens estimate (T0)\n"
    "If compression_opportunity > 0.6: call compress_context(). It preserves\n"
    "all decisions, commits, and lessons while compressing noise. The summary\n"
    "is written as an atom and surfaces on the next read_session() call.\n"
    "  read_compressed_context() → retrieve latest summary (T0)\n"
    "Compression is love: it keeps what matters and makes room for more work.\n"
    "No events are deleted — compression is additive, never destructive.\n"
)

ORACLE_NEW = (
    f"═══ COMPRESSION ORACLE ═══  # compression-oracle-d  # {MARK}\n"
    "When a session grows long (>50 events or budget < 30%), check first:\n"
    "  context_stats()         → event count, opportunity score, tokens estimate (T0)\n"
    "Sealed checkpoint chunks already exist for older turns — non-lossy,\n"
    "addressable, full fidelity. TRY RECALL FIRST:\n"
    "  recall_chunk(keyword)   → verbatim original text of matching turns (T0)\n"
    "Only fall back to compress_context() if no chunk is granular enough, or\n"
    "you genuinely want a permanent condensed digest — compression remains\n"
    "available whenever you want it, it's just the second resort now, not\n"
    "the default one. If compression_opportunity > 0.6: call compress_context().\n"
    "It preserves all decisions, commits, and lessons while compressing noise.\n"
    "The summary is written as an atom and surfaces on the next\n"
    "read_session() call.\n"
    "  read_compressed_context() → retrieve latest summary (T0)\n"
    "Compression is love: it keeps what matters and makes room for more work.\n"
    "No events are deleted — compression is additive, never destructive.\n"
)


def patch_loop(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    new_text = _replace_once(text, ORACLE_ANCHOR, ORACLE_NEW, label="compression oracle anchor")
    return new_text, True


# ── 3. cockpit/app.py: wire ChunkRecorder into _record() ───────────────────

INIT_ANCHOR = (
    "        self._transcript: list[tuple[str, str]] = []\n"
    "        self._transcript_path: Path | None = None\n"
)
INIT_NEW = (
    INIT_ANCHOR
    + f"\n        # {MARK} — every chat line also flows into a ChunkRecorder,\n"
    + "        # which buffers turns and auto-seals a non-lossy, addressable\n"
    + "        # chunk every 20 turns. Lazy-built on first use so a cockpit\n"
    + "        # launch never pays this cost if checkpoint_chunks isn't applied.\n"
    + "        import uuid as _uuid_ccd\n"
    + "        self._chunk_session_id = f\"cockpit-{_uuid_ccd.uuid4().hex[:12]}\"\n"
    + "        self._chunk_recorder = None\n"
)

RECORD_ANCHOR = (
    '    def _record(self, speaker: str, text: str) -> None:\n'
    '        """Append one chat line to the in-memory buffer and the disk\n'
    "        transcript. Both are best-effort — a failed disk write must\n"
    "        not break the cockpit's UI flow.\n"
    "\n"
    "        v0.2.20.1: this was added after a soul-poured introduction\n"
    "        was visible on screen yet effectively unrecoverable because\n"
    "        the RichLog widget doesn't support text selection and no\n"
    "        transcript existed on disk.\n"
    '        """\n'
    "        self._transcript.append((speaker, text))\n"
    "        # Bound the in-memory buffer so a long-running session doesn't\n"
    "        # accumulate forever. 2000 lines is a comfortable upper bound\n"
    "        # for /copy-all to be useful.\n"
    "        if len(self._transcript) > 2000:\n"
    "            self._transcript = self._transcript[-2000:]\n"
    "        try:\n"
    "            path = self._resolve_transcript_path()\n"
    "            ts = _now_short()\n"
    '            line = f"[{ts}] {speaker}: {text}\\n"\n'
    '            with path.open("a", encoding="utf-8") as f:\n'
    "                f.write(line)\n"
    "        except OSError:\n"
    "            # Disk full, permission denied, etc. — the in-memory copy\n"
    "            # still exists for /copy this session; nothing to surface.\n"
    "            pass\n"
)

RECORD_NEW = (
    '    def _record(self, speaker: str, text: str) -> None:\n'
    '        """Append one chat line to the in-memory buffer and the disk\n'
    "        transcript. Both are best-effort — a failed disk write must\n"
    "        not break the cockpit's UI flow.\n"
    "\n"
    "        v0.2.20.1: this was added after a soul-poured introduction\n"
    "        was visible on screen yet effectively unrecoverable because\n"
    "        the RichLog widget doesn't support text selection and no\n"
    "        transcript existed on disk.\n"
    '        """\n'
    "        self._transcript.append((speaker, text))\n"
    "        # Bound the in-memory buffer so a long-running session doesn't\n"
    "        # accumulate forever. 2000 lines is a comfortable upper bound\n"
    "        # for /copy-all to be useful.\n"
    "        if len(self._transcript) > 2000:\n"
    "            self._transcript = self._transcript[-2000:]\n"
    "        try:\n"
    "            path = self._resolve_transcript_path()\n"
    "            ts = _now_short()\n"
    '            line = f"[{ts}] {speaker}: {text}\\n"\n'
    '            with path.open("a", encoding="utf-8") as f:\n'
    "                f.write(line)\n"
    "        except OSError:\n"
    "            # Disk full, permission denied, etc. — the in-memory copy\n"
    "            # still exists for /copy this session; nothing to surface.\n"
    "            pass\n"
    f"        # {MARK} — feed the same turn into ChunkRecorder (non-lossy,\n"
    "        # addressable checkpoint chunks — Workstream P). Best-effort:\n"
    "        # never blocks the cockpit's UI flow, matches the disk-write\n"
    "        # try/except right above.\n"
    "        try:\n"
    "            if self._chunk_recorder is None:\n"
    "                from sovereign_agent.checkpoint_chunks import ChunkRecorder\n"
    "                self._chunk_recorder = ChunkRecorder(self._chunk_session_id)\n"
    "            self._chunk_recorder.record_turn(speaker, text)\n"
    "        except Exception:  # noqa: BLE001\n"
    "            pass\n"
)


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, INIT_ANCHOR, INIT_NEW, label="init anchor")
    text = _replace_once(text, RECORD_ANCHOR, RECORD_NEW, label="_record anchor")
    return text, True
