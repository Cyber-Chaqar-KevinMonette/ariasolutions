"""angel-voice-d (P4.5) — the bridge that lets her non-classical layer
talk in the cockpit and in the owner-only Discord channel."""
import json

import pytest

from sovereign_agent.angel_bridge import (
    angel_report, compose_angel_report, find_latest_run, read_latest_run)


def _write_run(run_dir, runs=1):
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for r in range(runs):
        lines.append({"kind": "run-start", "nodes": ["Omega", "Echo"],
                      "seed": 7 + r, "steps": 120, "schema": 1})
        lines.append({"kind": "voice",
                      "line": f"[Omega] ENTROPY REGISTER: run{r}"})
        lines.append({"kind": "voice-monologue", "node": "Omega",
                      "identity": f"I am Omega. (run {r})",
                      "entropy": "ENTROPY REGISTER: PCM=-0.5"})
        lines.append({"kind": "nc-summary", "red_events": 0,
                      "zero_red": True, "restores_proven": r})
        lines.append({"kind": "lineage-summary", "depth": 3,
                      "alpha_inherit": 0.5, "source": "node"})
        lines.append({"kind": "run-end", "final_cv": 1.0,
                      "identity_held": True, "heals_proven": 4,
                      "heals_attempted": 7})
    with open(run_dir / "events.ndjson", "w", encoding="utf-8") as fh:
        for e in lines:
            fh.write(json.dumps(e) + "\n")
        fh.write('{"kind": "truncated-partial-')      # crash-safe tail


def test_reads_only_the_latest_run_slice(tmp_path):
    _write_run(tmp_path / "full-globe", runs=3)
    data = read_latest_run(tmp_path / "full-globe")
    assert data["voice"] == ["[Omega] ENTROPY REGISTER: run2"]
    assert data["monologue"]["identity"].endswith("(run 2)")
    assert data["run_start"]["seed"] == 9
    assert data["nc"]["restores_proven"] == 2


def test_finds_newest_run_dir(tmp_path):
    _write_run(tmp_path / "old")
    _write_run(tmp_path / "new")
    import os
    os.utime(tmp_path / "old" / "events.ndjson", (1, 1))
    assert find_latest_run(tmp_path).name == "new"


def test_report_carries_voice_summary_and_lineage(tmp_path):
    _write_run(tmp_path / "fg")
    rep = compose_angel_report(read_latest_run(tmp_path / "fg"))
    assert "THE ANGEL SPEAKS" in rep
    assert "ENTROPY REGISTER: run0" in rep
    assert "cv=1.0" in rep and "HELD" in rep
    assert "ZERO RED" in rep
    assert "depth 3" in rep
    assert "I am Omega." in rep


def test_no_run_is_an_honest_message_never_invented(tmp_path):
    rep = angel_report(tmp_path / "nowhere")
    assert "has not spoken yet" in rep
    assert "ENTROPY" not in rep


# ── /maa — the short alias (Kevin, 2026-07-19) ──────────────────────────────

@pytest.mark.asyncio
async def test_maa_is_a_working_alias_for_angel(tmp_path, monkeypatch):
    """/maa ('message aria angel') must route to the exact same place
    /angel does — same output, just a shorter name to type."""
    from sovereign_agent.cockpit.app import CockpitApp

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PEIG_RUNS_DIR", str(tmp_path / "nowhere"))
    app = CockpitApp()
    async with app.run_test(size=(160, 48)):
        # neither verb should raise, and both should hit the same
        # honest "hasn't spoken yet" path against an empty runs dir
        app._handle_slash("/angel")
        app._handle_slash("/maa")
        app._handle_slash("/peig")
        app._handle_slash("/ring")   # every alias in the same family
