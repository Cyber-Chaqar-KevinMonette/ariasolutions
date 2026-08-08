"""aria-one-truth — the joins, checked. (FABLE II · M1)

Every test builds its stores in tmp_path and passes data_dir explicitly —
no reliance on ambient SETTINGS, so the file behaves identically staged
(module conftest) and promoted (live suite, isolated_paths autouse).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _now_iso(hours_ago: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ")


def _ndjson(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def _healthy_tree(base: Path) -> None:
    """A data dir where every join agrees."""
    base.mkdir(parents=True, exist_ok=True)
    (base / "thread_id").write_text("aria-main\n", encoding="utf-8")
    _ndjson(base / "checkpoint_chunks" / "chunks.ndjson", [
        {"chunk_id": "chunk-1", "session_id": "aria-main", "turn_start": 0,
         "turn_end": 1, "sealed_at": _now_iso(), "topic_tags": [],
         "raw_turns": [{"role": "you", "content": "hi", "ts": _now_iso()}]},
    ])
    sessions = base / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / "sess_a.json").write_text(json.dumps({
        "session_id": "sess_a", "goal": "g", "mode": "oneshot",
        "status": "complete", "updated_at": _now_iso()}), encoding="utf-8")
    (sessions / "sess_a.scope.json").write_text(json.dumps({"goal": "g"}),
                                                encoding="utf-8")
    # lessons + marker (marker lags reality — consistent)
    conn = sqlite3.connect(str(base / "atoms.db"))
    conn.execute("CREATE TABLE lessons (ts TEXT, trigger TEXT, rule TEXT, "
                 "context TEXT, correction TEXT)")
    conn.executemany("INSERT INTO lessons VALUES (?,?,?,?,?)",
                     [(_now_iso(), "t", f"rule {i}", "c", "") for i in range(3)])
    conn.commit()
    conn.close()
    (base / "aria_lm").mkdir(parents=True, exist_ok=True)
    (base / "aria_lm" / "last_retrain.json").write_text(json.dumps(
        {"lesson_count_at_last_retrain": 2, "last_retrain_ts": _now_iso()}),
        encoding="utf-8")
    # qa + uncertainty: the low-confidence wonder opened its uncertainty
    _ndjson(base / "epistemic" / "uncertainties.ndjson", [
        {"uncertainty_id": "unc-1", "domain": "curiosity",
         "question": "why does the garden hold?", "why_unknown": "w",
         "opened_at": _now_iso(), "closed_at": None, "resolution": ""},
    ])
    _ndjson(base / "qa" / "qa.ndjson", [
        {"qa_id": "qa-1", "asked_at": _now_iso(), "seed_kind": "self",
         "seed": "s", "question": "what is whole?", "answer": "a",
         "confidence": 0.9, "next_check": "", "topic": ""},
        {"qa_id": "qa-2", "asked_at": _now_iso(), "seed_kind": "self",
         "seed": "s", "question": "why does the garden hold?", "answer": "a",
         "confidence": 0.2, "next_check": "", "topic": ""},
    ])
    _ndjson(base / "proving_ground" / "results.ndjson", [
        {"run_id": "r1", "ts": _now_iso(), "suite": "v1", "kind": "offline",
         "tasks": {}, "score": 1.0},
    ])
    # dispositions: a live symbol + the honest exception (RETIRED then deleted)
    _ndjson(base / "loose_threads" / "ledger.ndjson", [
        {"symbol": "sovereign_agent.scope.load_scope", "verdict": "WIRED",
         "reason": "", "at": _now_iso()},
        {"symbol": "sovereign_agent.gone.never_was", "verdict": "RETIRED",
         "reason": "removed", "at": _now_iso()},
    ])


# ─── the healthy tree agrees everywhere ──────────────────────────────────


def test_healthy_tree_all_joins_agree(tmp_path):
    from sovereign_agent.consistency import run_all

    _healthy_tree(tmp_path / "d")
    results = run_all(tmp_path / "d")
    assert len(results) == 8
    disagreements = [f for r in results for f in r.findings]
    assert disagreements == [], disagreements


def test_empty_data_dir_is_honest_absence_not_findings(tmp_path):
    from sovereign_agent.consistency import run_all

    results = run_all(tmp_path / "empty")
    assert all(r.ok for r in results)


# ─── each join, broken on purpose ────────────────────────────────────────


def test_thread_chunks_flags_foreign_session(tmp_path):
    from sovereign_agent.consistency.checks import check_thread_chunks

    base = tmp_path / "d"
    _healthy_tree(base)
    with open(base / "checkpoint_chunks" / "chunks.ndjson", "a",
              encoding="utf-8") as fh:
        fh.write(json.dumps({"chunk_id": "chunk-9",
                             "session_id": "cockpit-deadbeef",
                             "turn_start": 0, "turn_end": 0,
                             "sealed_at": _now_iso(), "topic_tags": [],
                             "raw_turns": []}) + "\n")
    r = check_thread_chunks(base)
    assert not r.ok
    assert r.findings[0].subject == "cockpit-deadbeef"
    assert "merge" in r.findings[0].proposal


def test_sessions_scope_flags_orphan_contract(tmp_path):
    from sovereign_agent.consistency.checks import check_sessions_scope

    base = tmp_path / "d"
    _healthy_tree(base)
    (base / "sessions" / "sess_ghost.scope.json").write_text("{}",
                                                             encoding="utf-8")
    r = check_sessions_scope(base)
    assert not r.ok
    assert "sess_ghost" in r.findings[0].problem


def test_active_corpse_is_flagged_and_fresh_active_is_not(tmp_path):
    from sovereign_agent.consistency.checks import check_active_corpses

    base = tmp_path / "d"
    _healthy_tree(base)
    (base / "sessions" / "sess_corpse.json").write_text(json.dumps({
        "session_id": "sess_corpse", "status": "active",
        "updated_at": _now_iso(hours_ago=48)}), encoding="utf-8")
    (base / "sessions" / "sess_live.json").write_text(json.dumps({
        "session_id": "sess_live", "status": "active",
        "updated_at": _now_iso()}), encoding="utf-8")
    r = check_active_corpses(base)
    assert [f.subject for f in r.findings] == ["sess_corpse"]
    assert "sov session halt" in r.findings[0].proposal


def test_rest_point_orphan_and_stale_bookmark(tmp_path):
    from sovereign_agent.consistency.checks import check_rest_point

    base = tmp_path / "d"
    _healthy_tree(base)
    # names a session that does not exist
    (base / "resume_point.json").write_text(json.dumps(
        {"session_id": "sess_ghost", "goal": "g"}), encoding="utf-8")
    assert not check_rest_point(base).ok
    # names a COMPLETE session — stale bookmark
    (base / "resume_point.json").write_text(json.dumps(
        {"session_id": "sess_a", "goal": "g"}), encoding="utf-8")
    r = check_rest_point(base)
    assert not r.ok and "complete" in r.findings[0].problem
    # goal-only bookmark is legitimate
    (base / "resume_point.json").write_text(json.dumps(
        {"session_id": "", "goal": "g"}), encoding="utf-8")
    assert check_rest_point(base).ok


def test_lessons_marker_ahead_of_reality_is_flagged(tmp_path):
    from sovereign_agent.consistency.checks import check_lessons_retrain

    base = tmp_path / "d"
    _healthy_tree(base)
    (base / "aria_lm" / "last_retrain.json").write_text(json.dumps(
        {"lesson_count_at_last_retrain": 99}), encoding="utf-8")
    r = check_lessons_retrain(base)
    assert not r.ok
    assert "ahead of reality" in r.findings[0].problem


def test_qa_uncertainty_broken_links(tmp_path):
    from sovereign_agent.consistency.checks import check_qa_uncertainty

    base = tmp_path / "d"
    _healthy_tree(base)
    # a dangling close (no open event for its id)
    with open(base / "epistemic" / "uncertainties.ndjson", "a",
              encoding="utf-8") as fh:
        fh.write(json.dumps({"uncertainty_id": "unc-ghost", "domain": "x",
                             "question": "q", "why_unknown": "w",
                             "opened_at": _now_iso(),
                             "closed_at": _now_iso(),
                             "resolution": "answered"}) + "\n")
    # a low-confidence QA that never opened its uncertainty
    with open(base / "qa" / "qa.ndjson", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"qa_id": "qa-3", "asked_at": _now_iso(),
                             "seed_kind": "self", "seed": "s",
                             "question": "unfulfilled promise?", "answer": "a",
                             "confidence": 0.1, "next_check": "",
                             "topic": ""}) + "\n")
    r = check_qa_uncertainty(base)
    subjects = {f.subject for f in r.findings}
    assert subjects == {"unc-ghost", "qa-3"}


def test_proving_result_without_suite_version_is_flagged(tmp_path):
    from sovereign_agent.consistency.checks import check_proving_suite

    base = tmp_path / "d"
    _healthy_tree(base)
    with open(base / "proving_ground" / "results.ndjson", "a",
              encoding="utf-8") as fh:
        fh.write(json.dumps({"run_id": "r2", "ts": _now_iso(), "suite": "",
                             "kind": "offline", "tasks": {}}) + "\n")
    r = check_proving_suite(base)
    assert not r.ok and r.findings[0].subject == "r2"


def test_stale_disposition_flagged_but_retired_deleted_is_consistent(tmp_path):
    from sovereign_agent.consistency.checks import check_dispositions

    base = tmp_path / "d"
    _healthy_tree(base)
    with open(base / "loose_threads" / "ledger.ndjson", "a",
              encoding="utf-8") as fh:
        fh.write(json.dumps({"symbol": "sovereign_agent.gone.was_accepted",
                             "verdict": "ACCEPTED", "reason": "r",
                             "at": _now_iso()}) + "\n")
    r = check_dispositions(base)
    assert [f.subject for f in r.findings] == ["sovereign_agent.gone.was_accepted"]
    assert "RETIRED" in r.findings[0].proposal


def test_symbol_exists_resolves_real_and_fake(tmp_path):
    import sovereign_agent
    from sovereign_agent.consistency import symbol_exists

    src_root = Path(sovereign_agent.__file__).parent
    assert symbol_exists("sovereign_agent.scope.load_scope", src_root)
    assert symbol_exists("sovereign_agent.scope.ScopeContract", src_root)
    assert not symbol_exists("sovereign_agent.scope.never_defined", src_root)
    assert not symbol_exists("sovereign_agent.no_such_module.f", src_root)


def test_corrupt_lines_never_wedge_a_check(tmp_path):
    from sovereign_agent.consistency import run_all

    base = tmp_path / "d"
    _healthy_tree(base)
    for rel in ("checkpoint_chunks/chunks.ndjson", "qa/qa.ndjson",
                "proving_ground/results.ndjson", "loose_threads/ledger.ndjson",
                "epistemic/uncertainties.ndjson"):
        with open(base / rel, "a", encoding="utf-8") as fh:
            fh.write("{corrupt json\n\x00garbage\n")
    results = run_all(base)   # must not raise
    assert len(results) == 8


def test_findings_are_capped_but_count_stays_honest(tmp_path):
    from sovereign_agent.consistency.checks import MAX_LISTED, check_sessions_scope

    base = tmp_path / "d"
    sessions = base / "sessions"
    sessions.mkdir(parents=True)
    for i in range(MAX_LISTED + 10):
        (sessions / f"s{i:03}.scope.json").write_text("{}", encoding="utf-8")
    r = check_sessions_scope(base)
    assert len(r.findings) == MAX_LISTED
    assert r.checked == MAX_LISTED + 10


# ─── the sentinel ────────────────────────────────────────────────────────


def test_sentinel_registered():
    import sovereign_agent.consistency.sentinel  # noqa: F401
    from sovereign_agent.stewardship import registry

    assert "one-truth" in registry.registered_ids()


def test_sentinel_scan_clean_then_warn(tmp_path, monkeypatch):
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.consistency.sentinel import ConsistencySentinel

    base = tmp_path / "d"
    _healthy_tree(base)
    # the sentinel scans SETTINGS-adjacent stores via run_all(self._data_dir)
    sentinel = ConsistencySentinel(base)
    monkeypatch.delenv("SOV_NO_SENTINELS", raising=False)
    assert sentinel.is_enabled()

    report = sentinel.scan()
    assert report.findings_count == 0
    assert sentinel.health_status().level == "ok"

    (base / "sessions" / "ghost.scope.json").write_text("{}", encoding="utf-8")
    report = sentinel.scan()
    assert report.findings_count == 1
    health = sentinel.health_status()
    assert health.level == "warning"
    assert "disagreement" in health.summary
    # proposals surface, never repair — the orphan is still on disk
    props = sentinel.proposals(report)
    assert props and all(p["proposal"] for p in props)
    assert (base / "sessions" / "ghost.scope.json").exists()


def test_sentinel_kill_switch(tmp_path, monkeypatch):
    from sovereign_agent.consistency.sentinel import ConsistencySentinel

    sentinel = ConsistencySentinel(tmp_path)
    monkeypatch.setenv("SOV_NO_ONE_TRUTH_SENTINEL", "1")
    assert not sentinel.is_enabled()


# ─── the CLI surface ─────────────────────────────────────────────────────


def test_render_results_reads_plainly(tmp_path):
    from sovereign_agent.consistency import run_all
    from sovereign_agent.consistency.__main__ import render_results

    base = tmp_path / "d"
    _healthy_tree(base)
    (base / "sessions" / "ghost.scope.json").write_text("{}", encoding="utf-8")
    text = render_results(run_all(base))
    assert "sessions-scope" in text
    assert "propose:" in text
    assert "nothing repaired" in text
