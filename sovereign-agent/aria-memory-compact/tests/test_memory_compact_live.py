"""aria-memory-compact — bounded growth with dignity. (FABLE II · M2)

Everything runs against explicit tmp data dirs; nothing ambient.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ")


def _write_qa(base: Path, *, old: int, new: int) -> Path:
    path = base / "qa" / "qa.ndjson"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for i in range(old):
        lines.append(json.dumps({"qa_id": f"old-{i}", "asked_at": _iso(400 + i),
                                 "seed_kind": "self", "seed": "s",
                                 "question": f"q{i}", "answer": "a",
                                 "confidence": 0.5}))
    for i in range(new):
        lines.append(json.dumps({"qa_id": f"new-{i}", "asked_at": _iso(1),
                                 "seed_kind": "self", "seed": "s",
                                 "question": f"nq{i}", "answer": "a",
                                 "confidence": 0.9}))
    path.write_text("".join(x + "\n" for x in lines), encoding="utf-8")
    return path


# ─── audit ───────────────────────────────────────────────────────────────


def test_audit_reports_sizes_and_growth(tmp_path):
    from sovereign_agent.memory_compact import audit_all

    _write_qa(tmp_path, old=3, new=2)
    audit = audit_all(tmp_path)
    qa = next(s for s in audit["stores"] if s["store_id"] == "qa")
    assert qa["exists"] and qa["records"] == 5
    assert qa["records_per_day"] > 0
    assert audit["total_records"] >= 5
    # absent stores are honest absences
    chunks = next(s for s in audit["stores"] if s["store_id"] == "chunks")
    assert not chunks["exists"] and chunks["records"] == 0


def test_audit_counts_corrupt_lines_without_crashing(tmp_path):
    from sovereign_agent.memory_compact import audit_store
    from sovereign_agent.memory_compact.stores import REGISTRY

    path = _write_qa(tmp_path, old=1, new=1)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{never valid\n")
    a = audit_store(REGISTRY["qa"], tmp_path)
    assert a.records == 2 and a.corrupt_lines == 1


def test_registry_names_the_audit_only_stores_honestly():
    from sovereign_agent.memory_compact import REGISTRY

    for sid in ("epistemic-beliefs", "uncertainties", "loose-threads"):
        assert not REGISTRY[sid].compactable
        assert REGISTRY[sid].reason   # a written why, always


# ─── preview ─────────────────────────────────────────────────────────────


def test_preview_moves_nothing_and_buckets_by_month(tmp_path):
    from sovereign_agent.memory_compact import preview

    path = _write_qa(tmp_path, old=4, new=3)
    before = path.read_text(encoding="utf-8")
    plan = preview("qa", before_days=180, data_dir=tmp_path)
    assert plan.total_records == 7 and plan.to_move == 4
    assert sum(plan.periods.values()) == 4
    assert path.read_text(encoding="utf-8") == before   # nothing moved


def test_preview_refuses_audit_only_store(tmp_path):
    import pytest

    from sovereign_agent.memory_compact import CompactError, preview

    with pytest.raises(CompactError, match="audit-only"):
        preview("uncertainties", data_dir=tmp_path)


# ─── run: nothing is ever lost ───────────────────────────────────────────


def test_run_moves_verbatim_and_loses_nothing(tmp_path):
    from sovereign_agent.memory_compact import iter_cold_records, load_index, run

    path = _write_qa(tmp_path, old=5, new=2)
    original_lines = set(path.read_text(encoding="utf-8").splitlines())

    result = run("qa", before_days=180, data_dir=tmp_path)
    assert result.moved == 5 and result.kept == 2

    hot_lines = set(path.read_text(encoding="utf-8").splitlines())
    cold_lines = set()
    for cold in result.cold_files:
        cold_lines |= set(Path(cold).read_text(encoding="utf-8").splitlines())
    # byte-for-byte: hot ∪ cold == original, disjoint
    assert hot_lines | cold_lines == original_lines
    assert not (hot_lines & cold_lines)
    # the backup preserves the pre-compact file exactly
    backup = Path(result.backup)
    assert backup.exists()
    assert set(backup.read_text(encoding="utf-8").splitlines()) == original_lines
    # the pointer index carries count + digest
    index = load_index("qa", tmp_path)
    assert sum(e["count"] for e in index["periods"].values()) == 5
    assert any("avg_confidence" in e for e in index["periods"].values())
    # cold records remain readable through the pointer
    got = list(iter_cold_records("qa", path.parent))
    assert len(got) == 5 and {r["qa_id"] for r in got} == {f"old-{i}" for i in range(5)}


def test_run_is_idempotent(tmp_path):
    from sovereign_agent.memory_compact import run

    _write_qa(tmp_path, old=3, new=1)
    first = run("qa", before_days=180, data_dir=tmp_path)
    assert first.moved == 3
    second = run("qa", before_days=180, data_dir=tmp_path)
    assert second.moved == 0 and second.kept == 1


def test_undatable_lines_never_move(tmp_path):
    from sovereign_agent.memory_compact import preview, run

    path = _write_qa(tmp_path, old=2, new=1)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"qa_id": "undated", "asked_at": "not-a-time"}) + "\n")
        fh.write("{corrupt\n")
    plan = preview("qa", before_days=180, data_dir=tmp_path)
    assert plan.unparseable_kept_hot == 2
    run("qa", before_days=180, data_dir=tmp_path)
    hot = path.read_text(encoding="utf-8")
    assert "undated" in hot and "{corrupt" in hot


def test_kill_switches(tmp_path, monkeypatch):
    import pytest

    from sovereign_agent.memory_compact import CompactError, run

    _write_qa(tmp_path, old=2, new=1)
    monkeypatch.setenv("SOV_NO_COMPACT_QA", "1")
    with pytest.raises(CompactError, match="kill switch"):
        run("qa", before_days=180, data_dir=tmp_path)
    monkeypatch.delenv("SOV_NO_COMPACT_QA")
    monkeypatch.setenv("SOV_NO_COMPACT", "1")
    with pytest.raises(CompactError, match="kill switch"):
        run("qa", before_days=180, data_dir=tmp_path)


def test_chunks_compact_and_stay_addressable(tmp_path):
    """The M2 promise on the store that matters most: a compacted chunk is
    still reachable by id through the cold fallback."""
    from sovereign_agent.checkpoint_chunks import ChunkStore
    from sovereign_agent.checkpoint_chunks.store import Turn
    from sovereign_agent.memory_compact import iter_cold_records, run

    root = tmp_path / "checkpoint_chunks"
    store = ChunkStore(root)
    old = store.seal_chunk("aria-main", [Turn("you", "the old lighthouse")], 0, 0)
    # age it: rewrite the line with an old sealed_at (append-only file)
    line = json.loads(root.joinpath("chunks.ndjson").read_text().splitlines()[0])
    line["sealed_at"] = _iso(400)
    root.joinpath("chunks.ndjson").write_text(json.dumps(line) + "\n",
                                              encoding="utf-8")
    store.seal_chunk("aria-main", [Turn("you", "the new day")], 1, 1)

    result = run("chunks", before_days=180, data_dir=tmp_path)
    assert result.moved == 1
    assert len(store.all_chunks()) == 1          # hot is lean
    cold = list(iter_cold_records("chunks", root))
    assert cold and cold[0]["chunk_id"] == old.chunk_id   # verbatim, cold
    # after apply, ChunkStore.get_chunk falls back to cold (patched); the
    # engine-level guarantee tested here is that the record is reachable.


def test_render_audit_reads_plainly(tmp_path):
    from sovereign_agent.memory_compact.__main__ import render_audit
    from sovereign_agent.memory_compact.stores import audit_all

    _write_qa(tmp_path, old=1, new=1)
    text = render_audit(audit_all(tmp_path))
    assert "qa" in text and "total" in text and "bounded by design" in text


# ─── sentinel ────────────────────────────────────────────────────────────


def test_sentinel_registered():
    import sovereign_agent.memory_compact.sentinel  # noqa: F401
    from sovereign_agent.stewardship import registry

    assert "memory-compact" in registry.registered_ids()


def test_sentinel_quiet_when_small_warns_when_grown(tmp_path, monkeypatch):
    from sovereign_agent.memory_compact.sentinel import MemoryCompactSentinel

    monkeypatch.delenv("SOV_NO_SENTINELS", raising=False)
    _write_qa(tmp_path, old=2, new=2)
    sentinel = MemoryCompactSentinel(tmp_path)
    report = sentinel.scan()
    assert report.findings_count == 0
    assert sentinel.health_status().level == "ok"

    # grow the store past the warn threshold (record count)
    from sovereign_agent.memory_compact.sentinel import WARN_RECORDS

    path = tmp_path / "qa" / "qa.ndjson"
    row = json.dumps({"qa_id": "x", "asked_at": _iso(1), "confidence": 0.5})
    with open(path, "a", encoding="utf-8") as fh:
        for _ in range(WARN_RECORDS + 1):
            fh.write(row + "\n")
    report = sentinel.scan()
    assert report.findings_count >= 1
    assert sentinel.health_status().level == "warning"
    props = sentinel.proposals(report)
    assert props and "sov compact" in props[0]["remediation"]
    # propose-only: the store was not touched
    assert path.stat().st_size > 0
