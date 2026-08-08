"""Tests for the God-Tier System Scanner — her vision over the whole system."""
from __future__ import annotations

import asyncio
from pathlib import Path

def _find_repo() -> Path:
    """Locate the sovereign-agent repo robustly — works whether this test lives in the staged
    aria-*/tests/ folder OR the live tests/ folder (it moves on apply)."""
    for up in Path(__file__).resolve().parents:
        if (up / "scripts" / "lib" / "god_tier_canon.json").exists() or (up / "CLAUDE.md").exists():
            return up
    return Path.cwd()


_REPO = _find_repo()


# ── targets ───────────────────────────────────────────────────────────────────

def test_enumerates_total_coverage():
    from sovereign_agent.godtier import targets
    tg = targets.enumerate_targets(_REPO)
    kinds = {t.kind for t in tg}
    assert len(tg) > 50                      # the real system has many targets
    assert {"module", "layer", "doc"} <= kinds
    assert any(t.signals.get("is_non_classical") for t in tg if t.kind == "layer")


# ── rubric ────────────────────────────────────────────────────────────────────

def test_rubric_scores_and_bands():
    from sovereign_agent.godtier import rubric, targets
    full = targets.Target("x", "module", "x", {"has_payload": True, "has_tests": True, "has_readme": True,
                          "has_apply": True, "no_debug": True, "error_handling": True, "has_docstrings": True})
    bare = targets.Target("y", "module", "y", {"has_payload": False, "has_tests": False, "has_readme": False,
                          "has_apply": False, "no_debug": True, "error_handling": False, "has_docstrings": False})
    sf, sb = rubric.score_target(full), rubric.score_target(bare)
    assert sf["band"] == "god_tier" and sf["score"] >= 0.85
    assert sb["band"] in ("neglected", "weak") and len(sb["gaps"]) >= 4


def test_non_classical_parity_penalty():
    from sovereign_agent.godtier import rubric, targets
    q = targets.Target("quantum", "layer", "q", {"is_non_classical": True, "has_tests": False,
                       "no_debug": True, "error_handling": True, "has_docstrings": True})
    s = rubric.score_target(q)
    assert s["score"] <= 0.49                 # untested non-classical layer is capped (parity demand)
    assert any("PARITY" in g for g in s["gaps"])


# ── scanner ───────────────────────────────────────────────────────────────────

def test_scanner_covers_and_ranks():
    from sovereign_agent.godtier import scanner
    rep = scanner.scan(_REPO)
    assert rep["total_targets"] > 50
    assert 0.0 <= rep["average_score"] <= 1.0
    scores = [s["score"] for s in rep["weakest"]]
    assert scores == sorted(scores)
    assert set(rep["bands"]) <= {"god_tier", "strong", "fragile", "weak", "neglected"}


def test_gaps_are_below_god_tier():
    from sovereign_agent.godtier import scanner
    g = scanner.gaps(_REPO, max_band="fragile")
    assert all(s["band"] in ("fragile", "weak", "neglected") for s in g)


# ── enhance (propose-only) ────────────────────────────────────────────────────

def test_draft_is_propose_only():
    from sovereign_agent.godtier import scanner, enhance
    g = scanner.gaps(_REPO, max_band="weak")
    if not g:
        return
    d = enhance.draft_for(g[0])
    assert d["remediation_steps"] and "Propose-only" in d["note"]
    assert "pre_apply_gate" in d["gate"]      # Tribunal + foresight before any apply


# ── sentinel + tools ──────────────────────────────────────────────────────────

def test_godtier_sentinel_contract(tmp_path):
    from sovereign_agent.stewardship.godtier_sentinel import GodTierSentinel
    s = GodTierSentinel(tmp_path)
    s.bootstrap()
    assert len(s.articles()) >= 3
    h = s.health_status()
    assert h.level in ("ok", "warning", "unknown")


def test_godtier_tools():
    from sovereign_agent.tools.godtier_tools import GodTierScanTool, GodTierGapsTool, GodTierDraftFixTool
    assert GodTierScanTool.tier == 0 and GodTierGapsTool.tier == 0 and GodTierDraftFixTool.tier == 1
    r = asyncio.run(GodTierScanTool().execute(GodTierScanTool.Args(), trace_id="t"))
    assert r.ok and r.output["total_targets"] > 50 and "bands" in r.output
