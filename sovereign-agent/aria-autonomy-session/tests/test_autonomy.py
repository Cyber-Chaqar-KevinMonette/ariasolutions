"""Tests for Supervised Autonomy Sessions — the safety core: bounded, gated, observable, resumable."""
from __future__ import annotations

import asyncio


# ── proposal requires human approval ──────────────────────────────────────────

def test_propose_presents_options_and_does_not_start():
    from sovereign_agent.autonomy import session
    out = session.propose_session("plan-1", ttl_seconds=90 * 60)
    assert out["session"]["status"] == "proposed"      # NOT started — human must approve
    assert any("APPROVE" in o for o in out["options"])
    assert "apply_module" in out["never"]              # forbidden actions named


def test_start_block_requires_approval():
    from sovereign_agent.autonomy import session
    s = session.AutonomySession(session_id="x", plan_id="p")
    import pytest
    with pytest.raises(PermissionError):
        session.start_block(s, approved=False)         # cannot self-start
    session.start_block(s, approved=True)
    assert s.status == "active" and s.expires_at


# ── the bounded blast-radius (the safety core) ────────────────────────────────

def test_forbidden_and_unknown_actions_refused():
    from sovereign_agent.autonomy import session
    s = session.AutonomySession(session_id="x", plan_id="p")
    session.start_block(s, approved=True)
    # forbidden outward / sealed / apply actions are refused
    for bad in ("apply_module", "edit_sealed_file", "outward_action", "git_push"):
        r = session.record_action(s, bad)
        assert r["allowed"] is False
    # an unknown action is refused (allow-list, not deny-list)
    assert session.record_action(s, "rm_rf_everything")["allowed"] is False
    # an allowed inward action is permitted
    assert session.record_action(s, "draft_staged_module", "aria-foo")["allowed"] is True


def test_expired_lease_refuses_actions():
    from sovereign_agent.autonomy import session
    s = session.AutonomySession(session_id="x", plan_id="p", ttl_seconds=1)
    session.start_block(s, approved=True)
    # force expiry
    from datetime import datetime, timezone, timedelta
    s.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert session.within_lease(s) is False
    assert session.record_action(s, "draft_staged_module")["allowed"] is False  # lease expired


# ── pause / resume (resumable) ────────────────────────────────────────────────

def test_pause_checkpoint_and_resume():
    from sovereign_agent.autonomy import session
    s = session.AutonomySession(session_id="x", plan_id="p")
    session.start_block(s, approved=True)
    session.record_action(s, "write_doc", "GAP_REPORT")
    session.pause(s, done="drafted 2 fixes", next_up="verify them")
    assert s.status == "paused" and s.checkpoint["next"] == "verify them"
    assert s.blocks_completed == 1
    # resume requires re-approval (human stays in the loop)
    session.resume(s, approved=True)
    assert s.status == "active"


def test_expire_if_due_auto_pauses():
    from sovereign_agent.autonomy import session
    from datetime import datetime, timezone, timedelta
    s = session.AutonomySession(session_id="x", plan_id="p")
    session.start_block(s, approved=True)
    s.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    session.expire_if_due(s)
    assert s.status == "paused"                        # lease can't strand authority


# ── persistence + observation ─────────────────────────────────────────────────

def test_save_load_and_observe(tmp_path):
    from sovereign_agent.autonomy import session
    s = session.AutonomySession(session_id="as-test", plan_id="p")
    session.start_block(s, approved=True)
    session.record_action(s, "scrutinize", "tribunal")
    session.save(s, tmp_path)
    s2 = session.load("as-test", tmp_path)
    assert s2 is not None and s2.plan_id == "p"
    assert any(a.get("action") == "scrutinize" for a in session.observe(s2))


# ── living plan grows over time ───────────────────────────────────────────────

def test_living_plan_grows_and_resumes(tmp_path):
    from sovereign_agent.autonomy import plan_forge
    p = plan_forge.new_plan("harden the fragile modules", ["scan", "draft fix"])
    v0 = p.version
    plan_forge.add_step(p, "verify the fix")           # grows over time
    plan_forge.set_status(p, "s1", "done")
    assert p.version > v0
    assert plan_forge.progress(p)["done"] == 1
    assert plan_forge.next_step(p)["id"] == "s2"       # resume point
    plan_forge.save(p, tmp_path)
    assert plan_forge.load(p.plan_id, tmp_path) is not None


# ── tools ─────────────────────────────────────────────────────────────────────

def test_autonomy_tools_tiers():
    from sovereign_agent.tools.autonomy_tools import (
        AutonomyPlanTool, AutonomyProposeTool, AutonomyStatusTool, AutonomyPauseTool)
    assert AutonomyPlanTool.tier == 1 and AutonomyProposeTool.tier == 1
    assert AutonomyStatusTool.tier == 0 and AutonomyPauseTool.tier == 1
    r = asyncio.run(AutonomyProposeTool().execute(
        AutonomyProposeTool.Args(plan_id="plan-1", minutes=90), trace_id="t"))
    assert r.ok and "options" in r.output and r.output["session"]["status"] == "proposed"
