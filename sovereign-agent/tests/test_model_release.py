"""Tests for model_release — the zombie-VRAM fix — and the [995BTM]
experience-tools threading fix."""
from __future__ import annotations

from sovereign_agent.model_release import (
    loaded_models,
    release_all,
    release_models,
    render_vram_report,
)

_PS = {"models": [
    {"name": "aria-fast:latest", "size_vram": 5_100_000_000,
     "expires_at": "2026-07-14T14:13:00Z"},
    {"name": "aria-orchestrator:latest", "size_vram": 2_000_000_000,
     "expires_at": ""},
]}


def test_loaded_models_reads_ps():
    models = loaded_models(getter=lambda url: _PS)
    assert [m["name"] for m in models] == ["aria-fast:latest",
                                           "aria-orchestrator:latest"]
    assert models[0]["size_mb"] == 4863            # 5.1GB → MB


def test_loaded_models_survives_no_ollama():
    def boom(url):
        raise ConnectionError("ollama down")
    assert loaded_models(getter=boom) == []
    assert "GPU is free" in render_vram_report(getter=boom)


def test_release_sends_keep_alive_zero_per_model():
    posts = []
    results = release_models(["aria-fast:latest"],
                             poster=lambda url, payload: posts.append((url, payload)))
    assert results == [("aria-fast:latest", True)]
    url, payload = posts[0]
    assert url.endswith("/api/generate")
    assert payload == {"model": "aria-fast:latest", "keep_alive": 0}


def test_release_all_frees_everything_and_reports_failures():
    posts = []

    def poster(url, payload):
        if "orchestrator" in payload["model"]:
            raise TimeoutError
        posts.append(payload["model"])

    results = release_all(getter=lambda url: _PS, poster=poster)
    assert ("aria-fast:latest", True) in results
    assert ("aria-orchestrator:latest", False) in results
    assert posts == ["aria-fast:latest"]


def test_report_names_models_and_the_command():
    text = render_vram_report(getter=lambda url: _PS)
    assert "aria-fast:latest" in text and "4863 MB" in text
    assert "sov vram free" in text


# ── [995BTM] the SQLite threading fix ────────────────────────────────────────
def test_experience_write_opens_and_writes_on_one_thread(monkeypatch, tmp_path):
    """The bug: conn opened on the event loop, written via to_thread →
    'SQLite objects created in a thread can only be used in that same
    thread'. The fix routes open→write→commit through ONE function on ONE
    thread — prove it end-to-end across a real thread boundary."""
    import asyncio
    import sqlite3

    import sovereign_agent.tools.experience_tools as et

    db = tmp_path / "atoms.db"

    def open_db():
        conn = sqlite3.connect(db)   # check_same_thread=True — the strict default
        conn.execute("CREATE TABLE IF NOT EXISTS atoms (summary TEXT)")
        return conn

    def write_atom(conn, atom):
        conn.execute("INSERT INTO atoms (summary) VALUES (?)", (atom["summary"],))
        return "atom-1"

    monkeypatch.setattr(et, "open_atoms_db", open_db)
    monkeypatch.setattr(et, "write_atom", write_atom)

    async def go():
        return await asyncio.to_thread(
            et._write_atom_same_thread, {"summary": "threading fixed"})

    assert asyncio.run(go()) == "atom-1"
    check = sqlite3.connect(db)
    assert check.execute("SELECT summary FROM atoms").fetchone()[0] \
        == "threading fixed"
    check.close()
