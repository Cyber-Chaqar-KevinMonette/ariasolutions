"""Tests for training_data — curate + harden a fine-tuning dataset from
Aria's own real history (atoms.db, SessionStore).

Kevin, 2026-07-21: "we can fine tune if you want or we can build one. go
ahead and harden our curated data." Part of the fine-tuning project.
"""
from __future__ import annotations

import json

import pytest


# ── extract_atom_examples ───────────────────────────────────────────────


def test_extract_atom_examples_on_missing_db_is_empty(tmp_path):
    from sovereign_agent.training_data import extract_atom_examples

    assert extract_atom_examples(tmp_path) == []


def test_extract_atom_examples_reads_real_inline_atoms(tmp_path):
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.db import open_atoms_db
    from sovereign_agent.memory import Atom, write_atom
    from sovereign_agent.training_data import extract_atom_examples

    # isolated_paths (conftest, autouse) already points SETTINGS.paths at
    # a tmp dir -- use that same data_dir so open_atoms_db() and
    # extract_atom_examples() agree on where atoms.db is.
    data_dir = SETTINGS.paths.data_dir
    conn = open_atoms_db()
    try:
        write_atom(conn, Atom(
            type="observation", summary="a real curated fact",
            content_ref={"kind": "inline", "content": "the actual atom content"},
            claims=[], parents=["evt_1"], confidence=0.9,
            created_by={"actor": "agent", "model": "test", "version": "0.2.1"},
        ))
        conn.commit()
    finally:
        conn.close()

    examples = extract_atom_examples(data_dir)
    assert len(examples) == 1
    assert examples[0].output == "the actual atom content"
    assert "a real curated fact" in examples[0].instruction
    assert examples[0].source == "atom"


def test_extract_atom_examples_skips_non_inline_content(tmp_path):
    """blob/file-backed content needs a separate resolve pass -- must be
    skipped cleanly here, never crash on a KeyError."""
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.db import open_atoms_db
    from sovereign_agent.memory import Atom, write_atom
    from sovereign_agent.training_data import extract_atom_examples

    data_dir = SETTINGS.paths.data_dir
    conn = open_atoms_db()
    try:
        write_atom(conn, Atom(
            type="doc", summary="a blob-backed atom",
            content_ref={"kind": "blob", "hash": "deadbeef"},
            claims=[], parents=["evt_1"], confidence=0.9,
            created_by={"actor": "agent", "model": "test", "version": "0.2.1"},
        ))
        conn.commit()
    finally:
        conn.close()

    assert extract_atom_examples(data_dir) == []


def test_extract_atom_examples_skips_superseded_atoms(tmp_path):
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.db import open_atoms_db
    from sovereign_agent.memory import Atom, extend_atom, write_atom
    from sovereign_agent.training_data import extract_atom_examples

    data_dir = SETTINGS.paths.data_dir
    conn = open_atoms_db()
    try:
        old_id = write_atom(conn, Atom(
            type="observation", summary="the old version",
            content_ref={"kind": "inline", "content": "old content"},
            claims=[], parents=["evt_1"], confidence=0.9,
            created_by={"actor": "agent", "model": "test", "version": "0.2.1"},
        ))
        conn.commit()
        extend_atom(conn, parent_atom_id=old_id, summary="the new version",
                   content_ref={"kind": "inline", "content": "new content"},
                   claims=[], parents=["evt_2"], confidence=0.95,
                   created_by={"actor": "agent", "model": "test", "version": "0.2.1"})
        conn.commit()
    finally:
        conn.close()

    examples = extract_atom_examples(data_dir)
    assert len(examples) == 1
    assert examples[0].output == "new content"  # only the head of the chain


# ── extract_session_examples ────────────────────────────────────────────


def test_extract_session_examples_only_includes_done_subtasks(tmp_path):
    from sovereign_agent.agent_session import Subtask, SessionStore, SessionState
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.training_data import extract_session_examples

    store = SessionStore(SETTINGS.paths.data_dir / "sessions")
    state = SessionState(
        session_id="sess_test1", goal="a real goal", mode="busy",
        subtasks=[
            Subtask(id="st_a", description="a completed step",
                    status="done", result_summary="did the thing successfully"),
            Subtask(id="st_b", description="a blocked step",
                    status="blocked", result_summary="blocked: budget", error="budget"),
            Subtask(id="st_c", description="a pending step", status="pending"),
        ],
    )
    store.save(state)

    examples = extract_session_examples(SETTINGS.paths.data_dir)
    assert len(examples) == 1
    assert examples[0].instruction == "a completed step"
    assert examples[0].output == "did the thing successfully"
    assert examples[0].source_id == "sess_test1:st_a"


def test_extract_session_examples_on_no_sessions_is_empty(tmp_path):
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.training_data import extract_session_examples

    assert extract_session_examples(SETTINGS.paths.data_dir) == []


# ── harden_dataset ───────────────────────────────────────────────────────


def _ex(instruction, output, source="session_subtask", source_id="s:1"):
    from sovereign_agent.training_data import TrainingExample
    return TrainingExample(instruction=instruction, output=output,
                           source=source, source_id=source_id)


def test_harden_dataset_redacts_a_stored_secret(tmp_path, monkeypatch):
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.credentials import set_secret
    from sovereign_agent.training_data import harden_dataset

    set_secret("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123/supersecrettoken")
    examples = [_ex(
        "remember this webhook",
        "the webhook is https://discord.com/api/webhooks/123/supersecrettoken",
    )]
    cleaned, report = harden_dataset(examples)
    assert report.redacted_count == 1
    assert "supersecrettoken" not in cleaned[0].output


def test_harden_dataset_drops_exact_duplicates():
    from sovereign_agent.training_data import harden_dataset

    examples = [
        _ex("do the thing", "did the thing", source_id="s:1"),
        _ex("do the thing", "did the thing", source_id="s:2"),
    ]
    cleaned, report = harden_dataset(examples)
    assert len(cleaned) == 1
    assert report.dropped_duplicate == 1
    assert report.input_count == 2
    assert report.output_count == 1


def test_harden_dataset_drops_too_short_examples():
    from sovereign_agent.training_data import harden_dataset

    examples = [_ex("hi", "ok")]  # both under the length floor
    cleaned, report = harden_dataset(examples)
    assert cleaned == []
    assert report.dropped_too_short == 1


def test_harden_dataset_drops_too_long_examples():
    from sovereign_agent.training_data import _MAX_LEN, harden_dataset

    examples = [_ex("a" * (_MAX_LEN + 1), "a real output that is fine")]
    cleaned, report = harden_dataset(examples)
    assert cleaned == []
    assert report.dropped_too_long == 1


def test_harden_dataset_report_accounts_for_every_input():
    """The report must never let counts silently not add up -- every
    input example is exactly one of: kept, duplicate, too short, too
    long."""
    from sovereign_agent.training_data import harden_dataset

    examples = [
        _ex("a genuinely fine instruction", "a genuinely fine output", source_id="s:1"),
        _ex("a genuinely fine instruction", "a genuinely fine output", source_id="s:2"),  # dup
        _ex("hi", "ok", source_id="s:3"),  # too short
    ]
    cleaned, report = harden_dataset(examples)
    accounted = (report.dropped_duplicate + report.dropped_too_short
                + report.dropped_too_long + report.output_count)
    assert accounted == report.input_count == 3


def test_harden_dataset_empty_input_is_empty_output():
    from sovereign_agent.training_data import harden_dataset

    cleaned, report = harden_dataset([])
    assert cleaned == [] and report.input_count == 0 and report.output_count == 0


# ── build_training_dataset (the end-to-end entry point) ────────────────


def test_build_training_dataset_writes_real_jsonl(tmp_path):
    from sovereign_agent.agent_session import Subtask, SessionStore, SessionState
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.training_data import build_training_dataset

    store = SessionStore(SETTINGS.paths.data_dir / "sessions")
    store.save(SessionState(
        session_id="sess_e2e", goal="g", mode="busy",
        subtasks=[Subtask(id="st_a", description="a real completed subtask",
                          status="done", result_summary="a real result summary")],
    ))

    out_path = tmp_path / "dataset.jsonl"
    report = build_training_dataset(SETTINGS.paths.data_dir, out_path)

    assert out_path.exists()
    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == report.output_count == 1
    row = json.loads(lines[0])
    assert row["instruction"] == "a real completed subtask"
    assert row["output"] == "a real result summary"
    assert row["source"] == "session_subtask"


def test_build_training_dataset_on_no_data_writes_empty_file(tmp_path):
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.training_data import build_training_dataset

    out_path = tmp_path / "dataset.jsonl"
    report = build_training_dataset(SETTINGS.paths.data_dir, out_path)
    assert out_path.exists()
    assert out_path.read_text(encoding="utf-8") == ""
    assert report.output_count == 0
