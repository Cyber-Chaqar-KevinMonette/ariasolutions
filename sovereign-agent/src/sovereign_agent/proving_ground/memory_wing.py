"""proving_ground/memory_wing.py — the memory wing of the proving ground.
(FABLE II · M4 · memory-proof-d)

Five scored tasks for the faculties FABLE II hardens — the stick before
M2's tuning, as always. Same discipline as the v1 suite: real machinery,
mechanical scorers, no LLM judge; a task crash is a FAIL, never a run
crash (the runner guarantees that).

  cross-restart-recall   sealed conversation survives a store restart
  lesson-roundtrip       a lesson lands in the retrain corpus
  journal-once-only      the daily witness writes exactly once
  one-truth-clean        the consistency sentinel is clean on a healthy tree
  compaction-recall      compaction keeps every record reachable
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _iso(days_ago: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ")


async def _task_cross_restart_recall() -> tuple[bool, str]:
    """The thread survives a restart: seal through one store instance,
    recall through a FRESH one — only what disk holds counts."""
    from sovereign_agent.checkpoint_chunks import ChunkRecorder, ChunkStore
    from sovereign_agent.thread_identity import thread_id

    tid = thread_id()
    beacon = f"the cross-restart beacon shines ({_iso()[:19]})"
    rec = ChunkRecorder(tid, chunk_size=2)
    rec.record_turn("you", beacon)
    rec.record_turn("aria", "i will find it after the restart")

    fresh = ChunkStore()   # a new instance = a restart, for a file-backed store
    found = any(
        beacon in turn.get("content", "")
        for chunk in fresh.all_chunks(session_id=tid)
        for turn in chunk.raw_turns
    )
    return found, "verbatim recall through a fresh store instance"


async def _task_lesson_roundtrip() -> tuple[bool, str]:
    """lesson → atoms.db → retrain corpus, round trip. The synthetic row is
    scaffolding and is removed after the check so her real corpus stays hers."""
    from ulid import ULID

    from sovereign_agent.aria_lm.retrain_trigger import gather_lesson_text
    from sovereign_agent.db import open_atoms_db

    lid = str(ULID())
    rule = f"proving-ground round-trip beacon {lid[:8]}"
    conn = open_atoms_db()
    try:
        conn.execute(
            "INSERT INTO lessons (lesson_id, ts, trigger, context, "
            "failure_mode, correction, rule, evidence_refs, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (lid, _iso(), "prove-d:roundtrip", "proving-ground memory wing",
             None, "n/a", rule, "[]", 0.9),
        )
        conn.commit()
        ok = rule in gather_lesson_text(limit=100)
        conn.execute("DELETE FROM lessons WHERE lesson_id = ?", (lid,))
        conn.commit()
    finally:
        conn.close()
    return ok, "lesson lands in the retrain corpus (scaffolding row removed)"


async def _task_journal_once_only() -> tuple[bool, str]:
    """The daily witness writes exactly ONE journal entry per day, even when
    the model is unreachable (mechanical fallback, never a wake blocker)."""
    import os

    from sovereign_agent.self_witness import MIN_EVENTS, _yesterday, witness_yesterday

    if os.environ.get("SOV_NO_JOURNAL"):
        return True, "journal kill-switched by operator — nothing to score"

    class _Offline:
        async def chat(self, **kw):
            raise RuntimeError("model offline — fallback must carry the day")

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        day = _yesterday()
        events = base / "events"
        events.mkdir(parents=True)
        with open(events / f"events-{day}.jsonl", "w", encoding="utf-8") as fh:
            for i in range(MIN_EVENTS + 2):
                fh.write(json.dumps({"ts": f"{day}T04:0{i % 10}:00.000000Z",
                                     "flag": "settle-d"}) + "\n")
        first = await witness_yesterday(client=_Offline(), data_dir=base)
        journal = base / "journal"
        after_first = sorted(p.name for p in journal.glob("*.md"))
        second = await witness_yesterday(client=_Offline(), data_dir=base)
        after_second = sorted(p.name for p in journal.glob("*.md"))
        ok = (first is not None and second is None
              and after_first == after_second == [f"{day}.md"])
    return ok, "the daily witness writes exactly once"


async def _task_one_truth_clean() -> tuple[bool, str]:
    """The consistency sentinel reports every join agreeing on a healthy
    (small but populated) tree — no wolf-crying."""
    from sovereign_agent.consistency import run_all

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / "thread_id").write_text("aria-main\n", encoding="utf-8")
        cc = base / "checkpoint_chunks"
        cc.mkdir()
        (cc / "chunks.ndjson").write_text(json.dumps({
            "chunk_id": "c1", "session_id": "aria-main", "turn_start": 0,
            "turn_end": 0, "sealed_at": _iso(), "topic_tags": [],
            "raw_turns": [{"role": "you", "content": "hi", "ts": _iso()}],
        }) + "\n", encoding="utf-8")
        sessions = base / "sessions"
        sessions.mkdir()
        (sessions / "s1.json").write_text(json.dumps({
            "session_id": "s1", "goal": "g", "mode": "oneshot",
            "status": "complete", "updated_at": _iso()}), encoding="utf-8")
        (sessions / "s1.scope.json").write_text('{"goal": "g"}', encoding="utf-8")
        results = run_all(base)
        clean = all(r.ok for r in results)
    return clean and len(results) == 8, "every join agrees on a healthy tree"


async def _task_compaction_preserves_recall() -> tuple[bool, str]:
    """Compaction NEVER loses meaning: recent reads stay identical, old
    records stay reachable verbatim through the cold pointer."""
    from sovereign_agent.curiosity import recent_qas
    from sovereign_agent.memory_compact import iter_cold_records
    from sovereign_agent.memory_compact import run as compact_run

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        qa_dir = base / "qa"
        qa_dir.mkdir(parents=True)
        old_ids = {f"old-{i}" for i in range(4)}
        new_ids = {f"new-{i}" for i in range(2)}
        with open(qa_dir / "qa.ndjson", "w", encoding="utf-8") as fh:
            for i in range(4):
                fh.write(json.dumps({"qa_id": f"old-{i}", "asked_at": _iso(400),
                                     "seed_kind": "self", "seed": "s",
                                     "question": "q", "answer": "a",
                                     "confidence": 0.5}) + "\n")
            for i in range(2):
                fh.write(json.dumps({"qa_id": f"new-{i}", "asked_at": _iso(1),
                                     "seed_kind": "self", "seed": "s",
                                     "question": "q", "answer": "a",
                                     "confidence": 0.9}) + "\n")
        result = compact_run("qa", before_days=180, data_dir=base)
        hot = {q.qa_id for q in recent_qas(50, data_dir=base)}
        cold = {r.get("qa_id") for r in iter_cold_records("qa", qa_dir)}
        ok = result.moved == 4 and hot == new_ids and cold == old_ids
    return ok, "hot reads unchanged; cold records reachable verbatim"


MEMORY_TASKS = {
    "cross-restart-recall": _task_cross_restart_recall,
    "lesson-roundtrip": _task_lesson_roundtrip,
    "journal-once-only": _task_journal_once_only,
    "one-truth-clean": _task_one_truth_clean,
    "compaction-recall": _task_compaction_preserves_recall,
}
