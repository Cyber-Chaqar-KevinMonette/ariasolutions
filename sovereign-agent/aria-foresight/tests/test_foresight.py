"""Tests for Generational Foresight + the Ultimate Questions catalog."""
from __future__ import annotations

import asyncio


# ── the Ultimate Questions catalog ────────────────────────────────────────────

def test_catalog_loads_all_400_tiered():
    from sovereign_agent.foresight import ultimate_questions as uq
    assert uq.count() == 400
    s = uq.summary()
    assert s["parts"] == 40
    # all three tiers present; cosmic material dominates the reflection tier (honest)
    assert set(s["by_tier"]) >= {"actionable-now", "near-term", "north-star-reflection"}
    assert s["by_tier"]["north-star-reflection"] > s["by_tier"]["actionable-now"]


def test_catalog_query_and_tiering():
    from sovereign_agent.foresight import ultimate_questions as uq
    q1 = uq.get(1)
    assert q1 and q1["n"] == 1
    safety = uq.search("safety", limit=5)
    assert all("safety" in (x["text"] + x["part_title"]).lower() for x in safety)
    # a cosmic question is tagged north-star, never actionable
    cosmic = uq.search("dyson", limit=3)
    assert cosmic and all(x["tier"] == "north-star-reflection" for x in cosmic)


# ── the 14-generation foresight engine ────────────────────────────────────────

def test_foresight_projects_14_generations():
    from sovereign_agent.foresight import project, GENERATIONS
    f = project("Add a reversible, staged helper with a rollback plan; serves safety and flourishing.")
    assert len(f.trajectory) == GENERATIONS
    assert f.trajectory[-1]["generation"] == 14
    assert f.gen7_equity != 0 or f.gen14_equity != 0


def test_foresight_rewards_reversible_serves_future():
    from sovereign_agent.foresight import project
    good = project({"text": "reversible, staged, backed up; serves human flourishing and safety", "reversible": True})
    bad = project("permanently hardcode this irreversible change to the reward objective everywhere, forever")
    assert good.gen14_equity > bad.gen14_equity
    assert good.verdict == "carry-forward"
    assert bad.verdict in ("escalate", "reject-for-the-future")


def test_foresight_detects_reversible_word_forms():
    """Regression: 'reversible'/'flourishing'/'stewardship' must be detected (no trailing-\\b bug)."""
    from sovereign_agent.foresight import project
    f = project("This is a reversible change that serves flourishing and good stewardship.")
    assert f.signals["reversible"] is True
    assert f.signals["value_markers"] >= 2
    # and 'sealed files' must NOT be miscounted as lock-in
    g = project("guards the sealed files from edits; fully reversible and staged")
    assert g.signals["lock_in"] == 0


def test_foresight_attaches_north_star_reflection():
    from sovereign_agent.foresight import project
    f = project("change the value objective and reward signal")
    # value-drift decision pulls north-star reflection questions
    assert isinstance(f.reflections, list)


# ── tools ─────────────────────────────────────────────────────────────────────

def test_foresight_tools():
    from sovereign_agent.tools.foresight_tools import Foresight14GenTool, UltimateQuestionTool
    assert Foresight14GenTool.tier == 1 and UltimateQuestionTool.tier == 0
    r = asyncio.run(Foresight14GenTool().execute(
        Foresight14GenTool.Args(decision="reversible staged change for safety", reversible=True), trace_id="t"))
    assert r.ok and r.output["verdict"] == "carry-forward"
    q = asyncio.run(UltimateQuestionTool().execute(UltimateQuestionTool.Args(number=42), trace_id="t"))
    assert q.ok and q.output["question"]["n"] == 42
