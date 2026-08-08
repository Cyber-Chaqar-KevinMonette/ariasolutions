"""aria-read-repair — corruption honesty at every read path. (FABLE II · M3)

Unit tests + Hypothesis property tests for the shared tolerant reader.
The reader-integration tests exercise the PATCHED stores end-to-end once
applied; before apply they exercise the same behavior through the staged
path extension.
"""
from __future__ import annotations

import json
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ─── unit: the helper itself ─────────────────────────────────────────────


def test_missing_file_is_honest_absence(tmp_path):
    from sovereign_agent.read_repair import read_ndjson_tolerant

    r = read_ndjson_tolerant(tmp_path / "never.ndjson", store="x")
    assert r.records == [] and r.total_lines == 0 and r.skipped == 0 and r.ok


def test_counts_and_order(tmp_path):
    from sovereign_agent.read_repair import read_ndjson_tolerant

    p = tmp_path / "s.ndjson"
    p.write_text('{"a": 1}\n\n{broken\n42\n"just a string"\n{"a": 2}\n\x00\n',
                 encoding="utf-8")
    r = read_ndjson_tolerant(p, store="x", emit=False)
    assert [rec["a"] for rec in r.records] == [1, 2]
    assert r.total_lines == 6 and r.skipped == 4
    assert not r.ok


def test_binary_garbage_never_raises(tmp_path):
    from sovereign_agent.read_repair import read_ndjson_tolerant

    p = tmp_path / "s.ndjson"
    p.write_bytes(bytes(range(256)) + b'\n{"ok": true}\n' + b"\xff\xfe\x00" * 50)
    r = read_ndjson_tolerant(p, store="x", emit=False)
    assert any(rec.get("ok") is True for rec in r.records)


def test_corrupt_lines_event_emitted_once_per_read(tmp_path, monkeypatch):
    import sovereign_agent.events as events_mod
    from sovereign_agent.read_repair import read_ndjson_tolerant

    seen: list[tuple] = []
    monkeypatch.setattr(events_mod, "emit_event",
                        lambda flag, **kw: seen.append((flag, kw)))
    p = tmp_path / "s.ndjson"
    p.write_text('{"a": 1}\n{broken\n', encoding="utf-8")
    read_ndjson_tolerant(p, store="qa")
    assert len(seen) == 1
    flag, kw = seen[0]
    assert flag == "corrupt-lines-d"
    assert kw["payload"] == {"store": "qa", "file": "s.ndjson",
                             "skipped": 1, "total_lines": 2}
    # a clean read emits nothing
    seen.clear()
    p.write_text('{"a": 1}\n', encoding="utf-8")
    read_ndjson_tolerant(p, store="qa")
    assert seen == []


# ─── property: any interleaving, counts add up, order kept, no crash ─────

_GARBAGE = st.sampled_from([
    "{", "not json", "[1, 2", "42", '"a string"', "[]", "null", "true",
    "\x00\x01\x02", "{'single': 'quotes'}", "}{",
])
_RECORD = st.dictionaries(
    st.text(st.characters(codec="utf-8", exclude_characters="\n\r"),
            min_size=1, max_size=8),
    st.one_of(st.integers(), st.booleans(),
              st.text(st.characters(codec="utf-8",
                                    exclude_characters="\n\r"), max_size=20)),
    max_size=4,
)


# function_scoped_fixture suppressed deliberately: the live suite's autouse
# isolated_paths fixture resets per TEST (not per example), which is fine —
# this test only touches its own per-example mktemp dirs, never SETTINGS.
@settings(max_examples=60, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.lists(st.one_of(_RECORD, _GARBAGE), max_size=40))
def test_property_counts_add_up_and_order_survives(tmp_path_factory, items):
    from sovereign_agent.read_repair import read_ndjson_tolerant

    tmp = tmp_path_factory.mktemp("prop")
    p = tmp / "s.ndjson"
    expected: list[dict] = []
    garbage = 0
    with open(p, "w", encoding="utf-8") as fh:
        for item in items:
            if isinstance(item, dict):
                fh.write(json.dumps(item) + "\n")
                expected.append(item)
            else:
                fh.write(item + "\n")
                garbage += 1
    r = read_ndjson_tolerant(p, store="prop", emit=False)
    assert r.records == expected            # order + content survive
    assert r.skipped == garbage             # every loss is counted
    assert r.total_lines == len(expected) + garbage


# ─── the patched read paths (post-apply these run against live src) ──────


def _corrupt(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{never valid\n42\n")


def test_chunks_reader_survives_corruption(tmp_path):
    from sovereign_agent.checkpoint_chunks import ChunkStore
    from sovereign_agent.checkpoint_chunks.store import Turn

    store = ChunkStore(tmp_path / "checkpoint_chunks")
    store.seal_chunk("aria-main", [Turn("you", "hello")], 0, 0)
    _corrupt(store.log)
    store.seal_chunk("aria-main", [Turn("aria", "still here")], 1, 1)
    chunks = store.all_chunks()
    assert len(chunks) == 2
    assert chunks[-1].raw_turns[0]["content"] == "still here"


def test_qa_reader_survives_corruption(tmp_path):
    from sovereign_agent.curiosity import QARecord, record_qa, recent_qas

    record_qa(QARecord(qa_id="1", asked_at="t", seed_kind="s", seed="s",
                       question="q1", answer="a", confidence=0.5),
              data_dir=tmp_path)
    _corrupt(tmp_path / "qa" / "qa.ndjson")
    record_qa(QARecord(qa_id="2", asked_at="t", seed_kind="s", seed="s",
                       question="q2", answer="a", confidence=0.5),
              data_dir=tmp_path)
    qas = recent_qas(10, data_dir=tmp_path)
    assert [q.qa_id for q in qas] == ["1", "2"]


def test_proving_reader_survives_corruption(tmp_path):
    import inspect

    import pytest

    from sovereign_agent.proving_ground.runner import ProveResult, latest_scores, record

    if "read-repair-d" not in inspect.getsource(latest_scores):
        pytest.skip("pre-apply: the unpatched reader lets non-dict JSON "
                    "through — the exact bug this module fixes")
    record(ProveResult(run_id="r1", ts="t", suite="v1", kind="offline"),
           data_dir=tmp_path)
    _corrupt(tmp_path / "proving_ground" / "results.ndjson")
    record(ProveResult(run_id="r2", ts="t", suite="v1", kind="offline"),
           data_dir=tmp_path)
    scores = latest_scores(10, data_dir=tmp_path)
    assert [s["run_id"] for s in scores] == ["r1", "r2"]


def test_dispositions_reader_survives_corruption(tmp_path):
    from sovereign_agent.loose_threads import DispositionLedger

    ledger = DispositionLedger(tmp_path / "loose_threads")
    ledger.disposition("mod.sym_a", "WIRED")
    _corrupt(ledger.path)
    ledger.disposition("mod.sym_b", "RETIRED")
    seen = ledger.dispositions()
    assert set(seen) == {"mod.sym_a", "mod.sym_b"}


def test_epistemic_readers_survive_corruption(tmp_path):
    from sovereign_agent.epistemic_ledger.ledger import (
        EpistemicLedger, UncertaintyRegistry,
    )

    led = EpistemicLedger(tmp_path / "epistemic")
    led.record("claim one", 0.8)
    _corrupt(led.log)
    led.record("claim two", 0.9)
    assert [b.claim for b in led.all_beliefs()] == ["claim one", "claim two"]

    reg = UncertaintyRegistry(tmp_path / "epistemic")
    u = reg.open("d", "q?", "w")
    _corrupt(reg.log)
    assert [x.uncertainty_id for x in reg.list_open()] == [u.uncertainty_id]


def test_field_notes_reader_survives_corruption(tmp_path):
    import inspect

    import pytest

    from sovereign_agent.stewardship.field_notes import (
        FieldNote, FieldNoteFlavor, FieldNotesChannel,
    )

    if "read-repair-d" not in inspect.getsource(FieldNotesChannel.iter_all):
        pytest.skip("pre-apply: the unpatched reader CRASHES on a non-dict "
                    "JSON line — the exact bug this module fixes")
    ch = FieldNotesChannel(tmp_path / "stewardship" / "field-notes.jsonl")
    ch.append(FieldNote(flavor=FieldNoteFlavor.OBSERVATION, text="one"))
    _corrupt(ch.path)
    ch.append(FieldNote(flavor=FieldNoteFlavor.OBSERVATION, text="two"))
    assert [n.text for n in ch.iter_all()] == ["one", "two"]


def test_sessions_listing_counts_corpses_and_skips_scopes(tmp_path, monkeypatch):
    import inspect

    import pytest

    from sovereign_agent import agent_session as sess_mod
    from sovereign_agent.agent_session import SessionStore, new_session
    from sovereign_agent.modes import Mode

    events: list = []
    monkeypatch.setattr(sess_mod, "emit_event",
                        lambda flag, **kw: events.append((flag, kw)))

    store = SessionStore(tmp_path / "sessions")
    state = new_session(goal="g", mode=Mode.ONESHOT, store=store)
    # a corrupt session file + a scope contract beside it
    (tmp_path / "sessions" / "broken.json").write_text("{never",
                                                       encoding="utf-8")
    (tmp_path / "sessions" / f"{state.session_id}.scope.json").write_text(
        "{}", encoding="utf-8")
    listed = store.list_all()
    assert [s.session_id for s in listed] == [state.session_id]
    if "read-repair-d" not in inspect.getsource(SessionStore.list_all):
        pytest.skip("pre-apply: sessions listing not yet patched "
                    "(the apply script re-runs this file after patching)")
    corrupt_events = [e for e in events if e[0] == "corrupt-lines-d"]
    assert len(corrupt_events) == 1
    assert corrupt_events[0][1]["payload"]["skipped"] == 1   # scope not counted
