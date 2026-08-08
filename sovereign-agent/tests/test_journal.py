"""Tests for j-space-d — the J-Space: Aria's reflective, two-way journal."""
from __future__ import annotations

import pytest

from sovereign_agent.journal import (
    AUTHOR_ARIA,
    AUTHOR_HUMAN,
    add_entry,
    is_journal_read_query,
    is_journal_write_command,
    journal_path,
    recent_entries,
    render_journal,
)


# ── store ────────────────────────────────────────────────────────────────
def test_add_and_read_round_trip(tmp_path):
    add_entry("a quiet reflection", author=AUTHOR_ARIA, mood="calm",
              tags=["evening"], data_dir=tmp_path)
    entries = recent_entries(data_dir=tmp_path)
    assert len(entries) == 1
    e = entries[0]
    assert e["text"] == "a quiet reflection"
    assert e["author"] == "aria" and e["mood"] == "calm" and e["tags"] == ["evening"]
    assert "id" in e and "ts" in e


def test_two_way_authors_preserved(tmp_path):
    add_entry("her thought", author=AUTHOR_ARIA, data_dir=tmp_path)
    add_entry("his note", author=AUTHOR_HUMAN, data_dir=tmp_path)
    authors = [e["author"] for e in recent_entries(data_dir=tmp_path)]
    assert authors == ["aria", "kevin"]


def test_recent_entries_is_chronological_and_limited(tmp_path):
    for i in range(10):
        add_entry(f"entry {i}", data_dir=tmp_path)
    got = recent_entries(limit=3, data_dir=tmp_path)
    assert [e["text"] for e in got] == ["entry 7", "entry 8", "entry 9"]


def test_missing_journal_reads_empty(tmp_path):
    assert recent_entries(data_dir=tmp_path) == []


def test_corrupt_line_is_skipped_not_fatal(tmp_path):
    add_entry("good one", data_dir=tmp_path)
    with open(journal_path(tmp_path), "a", encoding="utf-8") as fh:
        fh.write("{ not valid json\n")
    add_entry("another good one", data_dir=tmp_path)
    texts = [e["text"] for e in recent_entries(data_dir=tmp_path)]
    assert texts == ["good one", "another good one"]


# ── render ───────────────────────────────────────────────────────────────
def test_render_marks_each_author_and_shows_text(tmp_path):
    add_entry("her reflection", author=AUTHOR_ARIA, mood="grateful", data_dir=tmp_path)
    add_entry("his reply", author=AUTHOR_HUMAN, data_dir=tmp_path)
    r = render_journal(recent_entries(data_dir=tmp_path))
    assert "her reflection" in r and "his reply" in r
    assert "aria" in r and "kevin" in r
    assert "grateful" in r


def test_render_empty_invites_writing():
    r = render_journal([])
    assert "empty" in r.lower() and "/journal" in r


# ── detection ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("q", [
    "read your journal", "show me your journal", "what's in your journal",
    "open your journal",
])
def test_read_queries_detected(q):
    assert is_journal_read_query(q) is True


def test_ordinary_message_not_a_read_query():
    assert is_journal_read_query("how are you") is False


@pytest.mark.parametrize("cmd,expected", [
    ("write in your journal: I am proud of you", "I am proud of you"),
    ("journal this: today was good", "today was good"),
    ("journal: a small note", "a small note"),
])
def test_write_command_parsed(cmd, expected):
    ok, body = is_journal_write_command(cmd)
    assert ok is True and body == expected


def test_non_write_message_is_not_a_write_command():
    ok, body = is_journal_write_command("what did you do today")
    assert ok is False and body == ""


# ── converse() integration ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_converse_writes_and_reads_journal(tmp_path, monkeypatch):
    # point the journal at a temp file (SETTINGS.paths is frozen)
    import sovereign_agent.journal as jmod
    monkeypatch.setattr(jmod, "journal_path",
                        lambda data_dir=None: tmp_path / "journal.ndjson")
    from sovereign_agent.conversation import converse

    w = await converse("write in your journal: I trust you", allow_llm=False)
    assert w.kind == "journal-write"

    r = await converse("read your journal", allow_llm=False)
    assert r.kind == "journal-read"
    assert "I trust you" in " ".join(r.messages)
