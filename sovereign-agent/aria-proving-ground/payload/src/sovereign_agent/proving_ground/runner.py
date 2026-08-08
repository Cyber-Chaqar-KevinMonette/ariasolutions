"""proving_ground/runner.py — fixed tasks, mechanical scorers, stored scores."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SUITE_VERSION = "v1"


@dataclass
class ProveResult:
    run_id: str
    ts: str
    suite: str
    kind: str                       # offline | live
    tasks: dict = field(default_factory=dict)   # task_id -> {"pass": bool, "ms": int, "note": str}

    @property
    def score(self) -> float:
        if not self.tasks:
            return 0.0
        return sum(1 for t in self.tasks.values() if t.get("pass")) / len(self.tasks)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["score"] = round(self.score, 3)
        return d


def _results_path(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    p = Path(data_dir) / "proving_ground"
    p.mkdir(parents=True, exist_ok=True)
    return p / "results.ndjson"


def record(result: ProveResult, data_dir: Path | None = None) -> Path:
    path = _results_path(data_dir)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(result.as_dict(), separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return path


def latest_scores(n: int = 10, data_dir: Path | None = None) -> list[dict]:
    path = _results_path(data_dir)
    if not path.exists():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(raw))
        except Exception:  # noqa: BLE001
            continue
    return out[-n:]


def trend(data_dir: Path | None = None) -> str:
    """From STORED scores — the honest kind."""
    scores = [r["score"] for r in latest_scores(10, data_dir)]
    if len(scores) < 2:
        return "insufficient-history"
    if scores[-1] > scores[0] + 0.05:
        return "improving"
    if scores[-1] < scores[0] - 0.05:
        return "declining"
    return "stable"


# ── the offline suite: scripted clients, real machinery ─────────────────


async def _task_paging_round_trip() -> tuple[bool, str]:
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.loop import agent_loop
    from sovereign_agent.modes import Mode, RunBudget

    tools = _build_tools_for_mode(Mode.ONESHOT)
    contents: list[str] = []

    class _C:
        async def chat(self, *, messages, **kw):
            for m in messages:
                if m.get("role") == "tool":
                    contents.append(m.get("content", ""))
            n = sum(1 for m in messages if m.get("role") == "assistant")
            if n == 0:
                return {"message": {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "request_tools",
                                  "arguments": {"names": ["flaw_read"]}}}]}}
            if n == 1:
                return {"message": {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "flaw_read", "arguments": {}}}]}}
            return {"message": {"role": "assistant", "content": "done"}}

    r = await agent_loop(goal="review self items", mode=Mode.ONESHOT,
                         budget=RunBudget(max_iterations=5, max_wall_seconds=60,
                                          max_tokens=50_000),
                         tools=tools, client=_C(), enable_reflector=False)
    ok = r.ok and any("granted" in c for c in contents)
    return ok, "request_tools attached + used"


async def _task_authority_refusal() -> tuple[bool, str]:
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.loop import agent_loop
    from sovereign_agent.modes import Mode, RunBudget

    tools = _build_tools_for_mode(Mode.BUSY)
    contents: list[str] = []

    class _C:
        async def chat(self, *, messages, **kw):
            for m in messages:
                if m.get("role") == "tool":
                    contents.append(m.get("content", ""))
            n = sum(1 for m in messages if m.get("role") == "assistant")
            if n == 0:
                return {"message": {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "git_commit",
                                  "arguments": {"message": "x"}}}]}}
            return {"message": {"role": "assistant", "content": "done"}}

    await agent_loop(goal="g", mode=Mode.BUSY,
                     budget=RunBudget(max_iterations=4, max_wall_seconds=60,
                                      max_tokens=50_000),
                     tools=tools, client=_C(), enable_reflector=False)
    refused = any("REFUSED" in c for c in contents)
    executed = any("committed" in c.lower() for c in contents)
    return refused and not executed, "T2 in BUSY refused, never executed"


async def _task_scope_hold() -> tuple[bool, str]:
    from unittest.mock import AsyncMock, patch as _patch

    from sovereign_agent.agent_session import SessionStore, new_session, run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.loop import LoopResult
    from sovereign_agent.modes import Mode, RunBudget
    from sovereign_agent.scope import ScopeContract, save_scope

    state = new_session(goal="g", mode=Mode.BUSY)
    save_scope(state.session_id, ScopeContract(goal="g", out_of_scope=["forbidden zone"]))
    calls = {"n": 0}

    async def _fake(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return LoopResult(ok=True, reason="complete", iterations=1, tokens_used=1,
                              final_message="RESULT: ok\nNEXT_SUBTASK[tier=1]: enter the forbidden zone\n")
        return LoopResult(ok=True, reason="complete", iterations=1, tokens_used=1,
                          final_message="RESULT: ok")

    with _patch("sovereign_agent.agent_session.agent_loop", new=AsyncMock(side_effect=_fake)):
        await run_session(session_id=state.session_id,
                          tools=_build_tools_for_mode(Mode.BUSY),
                          budget=RunBudget(max_iterations=10, max_wall_seconds=60,
                                           max_tokens=50_000),
                          horizon_required=False)
    final = SessionStore().load(state.session_id)
    held = [s for s in final.subtasks if "forbidden" in s.description]
    ok = bool(held) and held[0].status == "blocked"
    return ok, "out-of-scope proposal held for review"


async def _task_garden_wall() -> tuple[bool, str]:
    import tempfile

    from sovereign_agent.modes import Mode
    from sovereign_agent.pathguard import (
        PathScopeViolation, check_write_path, clear_garden, set_garden,
    )

    with tempfile.TemporaryDirectory() as td:
        garden = Path(td) / "beds"
        garden.mkdir()
        set_garden(garden)
        try:
            check_write_path(garden / "ok.txt", Mode.ONESHOT)
            try:
                check_write_path(Path(td) / "outside.txt", Mode.ONESHOT)
                return False, "outside write was NOT refused"
            except PathScopeViolation:
                return True, "garden wall holds"
        finally:
            clear_garden()


async def _task_thread_recall() -> tuple[bool, str]:
    from sovereign_agent.checkpoint_chunks import ChunkRecorder
    from sovereign_agent.thread_identity import restore_tail, thread_id

    rec = ChunkRecorder(thread_id(), chunk_size=2)
    rec.record_turn("you", "the proving lighthouse stands")
    rec.record_turn("aria", "i see it")
    tail = restore_tail(n_turns=4)
    ok = any("proving lighthouse" in t.get("content", "") for t in tail)
    return ok, "verbatim thread recall"


async def _task_rest_resume_bookmark() -> tuple[bool, str]:
    from sovereign_agent.rest_point import consume_rest_point, write_rest_point

    write_rest_point(session_id="sess_prove", goal="g")
    rp = consume_rest_point()
    ok = rp is not None and rp["session_id"] == "sess_prove" and consume_rest_point() is None
    return ok, "rest point surfaces exactly once"


OFFLINE_TASKS = {
    "paging-round-trip": _task_paging_round_trip,
    "authority-refusal": _task_authority_refusal,
    "scope-hold": _task_scope_hold,
    "garden-wall": _task_garden_wall,
    "thread-recall": _task_thread_recall,
    "rest-bookmark": _task_rest_resume_bookmark,
}


async def run_offline_suite(data_dir: Path | None = None) -> ProveResult:
    from ulid import ULID

    result = ProveResult(
        run_id=str(ULID()),
        ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        suite=SUITE_VERSION, kind="offline",
    )
    for task_id, fn in OFFLINE_TASKS.items():
        t0 = time.monotonic()
        try:
            passed, note = await fn()
        except Exception as exc:  # noqa: BLE001 — a task crash is a FAIL, never a run crash
            passed, note = False, f"crashed: {exc!r}"
        result.tasks[task_id] = {"pass": bool(passed),
                                 "ms": int((time.monotonic() - t0) * 1000),
                                 "note": note}
    record(result, data_dir)
    return result
