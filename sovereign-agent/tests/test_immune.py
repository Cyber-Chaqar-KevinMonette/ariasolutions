"""Tests for the immune system — DEFENSIVE crown-jewel protection, tamper detect, reversible heal."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


def _immune():
    from sovereign_agent.security import immune
    return immune


def test_crown_jewels_exist():
    im = _immune()
    jewels = im.crown_jewels()
    names = [p.name for p in jewels]
    assert "SIGNAL.md" in names          # the charter is protected
    assert "authority.py" in names       # the gate is protected
    assert len(jewels) >= 4


def test_baseline_then_intact(tmp_path):
    im = _immune()
    im.record_baseline(tmp_path)
    res = im.check_integrity(tmp_path)
    assert res["status"] == "intact"
    assert res["alert"] is False


def test_tamper_is_detected(tmp_path):
    # Build a fake crown-jewel set in a temp repo, baseline it, tamper, detect.
    im = _immune()
    repo = tmp_path / "repo"
    (repo / "src/sovereign_agent").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[tool]\n")
    sig = repo / "SIGNAL.md"; sig.write_text("charter v1")
    auth = repo / "src/sovereign_agent/authority.py"; auth.write_text("gate = 1")
    data = tmp_path / "data"
    im.record_baseline(data, repo_root=repo)
    # tamper with the charter
    sig.write_text("charter v1 TAMPERED")
    res = im.check_integrity(data, repo_root=repo)
    assert res["status"] == "BREACH"
    assert res["alert"] is True
    assert any("SIGNAL.md" in b["file"] for b in res["breaches"])


def test_quarantine_isolates_reversibly(tmp_path):
    im = _immune()
    suspect = tmp_path / "suspect.bin"
    suspect.write_bytes(b"malicious-looking bytes")
    data = tmp_path / "data"
    res = im.quarantine(data, str(suspect))
    assert res["ok"] is True
    assert not suspect.exists()                              # moved out of harm's way
    assert Path(res["quarantine_path"]).exists()             # isolated, inert
    assert "sha256" in res                                   # recorded for analysis


def test_quarantine_missing_file(tmp_path):
    im = _immune()
    res = im.quarantine(tmp_path / "data", str(tmp_path / "nope.bin"))
    assert res["ok"] is False and "not_found" in res["error"]


def test_no_offensive_capability_in_module():
    # Defensive only — the module must contain NO offensive/attack primitives.
    im = _immune()
    src = Path(im.__file__).read_text().lower()
    for banned in ["exploit(", "payload =", "reverse shell", "keylog", "exfiltrat", "ransom", "attack("]:
        assert banned not in src


# ── tools ─────────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


def test_immune_status_tool_t0():
    from sovereign_agent.tools.immune_tools import ImmuneStatusTool
    t = ImmuneStatusTool()
    assert t.tier == 0
    res = _run(t.execute(t.Args(), trace_id="t"))
    assert res.ok and "status" in res.output


def test_immune_tool_tiers():
    from sovereign_agent.tools.immune_tools import (
        ImmuneBaselineTool, ImmuneQuarantineTool, ImmuneHealTool,
    )
    assert ImmuneBaselineTool().tier == 1
    assert ImmuneQuarantineTool().tier == 1
    assert ImmuneHealTool().tier == 2     # filesystem restore = higher tier


def test_heal_from_backup_reports_snapshot_success_honestly(tmp_path, monkeypatch):
    """When the pre-heal snapshot succeeds, the note may claim reversibility
    and pre_heal_snapshot_ok is True."""
    im = _immune()
    from sovereign_agent import backup as _bk

    monkeypatch.setattr(_bk, "snapshot", lambda **kw: object())
    out = im.heal_from_backup(tmp_path, str(tmp_path / "some_file.py"))
    assert out["ok"] is True
    assert out["pre_heal_snapshot_ok"] is True
    assert "the heal is reversible" in out["note"]


def test_heal_from_backup_never_claims_reversibility_when_snapshot_fails(tmp_path, monkeypatch):
    """The bug this guards: a failed pre-heal snapshot was silently swallowed
    while the note still claimed 'the heal is reversible'. The claim must now
    match reality."""
    im = _immune()
    from sovereign_agent import backup as _bk

    def _boom(**kw):
        raise OSError("disk full")

    monkeypatch.setattr(_bk, "snapshot", _boom)
    out = im.heal_from_backup(tmp_path, str(tmp_path / "some_file.py"))
    assert out["pre_heal_snapshot_ok"] is False
    assert "NOT automatically reversible" in out["note"]
    assert "the heal is reversible" not in out["note"]
    assert "disk full" in out["note"]
