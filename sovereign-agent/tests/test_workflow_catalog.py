"""Tests for workflow.catalog — the single source of truth for ▸ flows."""
from __future__ import annotations

from sovereign_agent.workflow import catalog as cat


def test_every_workflow_is_well_formed():
    seen_ids = set()
    for w in cat.all_workflows():
        assert w.wid and w.wid not in seen_ids, f"duplicate/empty wid: {w.wid}"
        seen_ids.add(w.wid)
        assert w.title and w.category and w.summary
        assert len(w.how_to) >= 1, f"{w.wid} has no how_to steps"
        assert 0 <= w.authority <= 4, f"{w.wid} authority out of range"
        assert w.status in ("ready", "gated")


def test_ready_and_gated_are_honest():
    for w in cat.gated_workflows():
        assert w.status == "gated"
        assert w.needs, f"gated workflow {w.wid} must say what it needs"
        assert w.demo_kind is None, f"gated workflow {w.wid} must not be demoable"
        assert w.cap_test is None, f"gated workflow {w.wid} must not be cap-testable"
    for w in cat.ready_workflows():
        assert w.status == "ready"


def test_demoable_have_demo_kind_and_are_ready():
    demoable = cat.demoable_workflows()
    assert demoable, "expected at least some demoable workflows"
    for w in demoable:
        assert w.is_demoable
        assert w.demo_kind in ("introspect", "sandbox", "sov")
        assert w.status == "ready"
        assert w.demo_note, f"{w.wid} should describe what its live probe does"


def test_counts_are_consistent():
    c = cat.counts()
    assert c["total"] == len(cat.all_workflows())
    assert c["ready"] + c["gated"] == c["total"]
    assert c["demoable"] == len(cat.demoable_workflows())
    assert c["cap_testable"] == len(cat.capability_testable_workflows())
    assert c["categories"] == len(cat.categories())


def test_cap_testable_have_cap_test_and_are_ready():
    cap_testable = cat.capability_testable_workflows()
    assert cap_testable, "expected at least some capability-testable workflows"
    for w in cap_testable:
        assert w.is_cap_testable
        assert w.cap_test
        assert w.status == "ready"
        assert w.cap_test_note, f"{w.wid} should describe what its real test does"


def test_new_generate_create_workflows_present():
    ids = {w.wid for w in cat.all_workflows()}
    for wid in ("create.image", "create.image_edit", "create.web_search",
                "create.game_project", "create.marketing_brief",
                "create.movie_project", "create.movie_pitch",
                "create.discord_tracker", "create.discord_bot_command",
                "create.video"):
        assert wid in ids, f"missing workflow {wid}"


def test_create_video_is_now_ready_and_cap_testable():
    # movie-studio-d Phase 2: LTX-Video was built, confirmed live on this
    # exact GPU (four consecutive real runs) — the honest catalog now
    # reflects that it flipped from gated to ready, same as any other
    # real capability, not left stale as "coming soon."
    w = cat.get("create.video")
    assert w is not None
    assert w.status == "ready"
    assert w.cap_test == "create.video"
    assert "LTX-Video" in w.summary or "LTX-Video" in " ".join(w.uses)


def test_discord_capability_tests_stay_dry_run_by_design():
    # these two are the ones a careless test could accidentally make live —
    # the catalog text itself must say so, not just the (untested-here)
    # implementation.
    for wid in ("create.discord_tracker", "create.discord_bot_command"):
        w = cat.get(wid)
        assert w is not None
        note = w.cap_test_note.lower()
        assert "network" in note or "offline" in note, (
            f"{wid}'s cap_test_note must say it makes no real network/Discord call")


def test_by_category_covers_everything():
    by_cat = cat.by_category()
    assert sum(len(v) for v in by_cat.values()) == len(cat.all_workflows())
    assert set(by_cat) == set(cat.categories())


def test_new_subsystems_are_present():
    ids = {w.wid for w in cat.all_workflows()}
    for wid in ("skills.author", "skills.sentinel", "diagnose.catalog", "beacon.showcase"):
        assert wid in ids, f"missing workflow {wid}"


def test_render_text_color_preserves_literal_button_names():
    # color=True wraps content in Rich markup; literal [doctor]-style button
    # names must survive (escaped), not get eaten as style tags.
    from rich.text import Text
    from rich.console import Console
    import io
    txt = cat.render_text(color=True)
    assert txt.strip()
    con = Console(file=io.StringIO(), width=100, no_color=True)
    con.print(Text.from_markup(txt))
    out = con.file.getvalue()
    assert "[doctor]" in out  # the button name is visible, not swallowed


def test_render_text_plain_has_no_markup_or_escapes():
    plain = cat.render_text(color=False)
    assert plain.strip()
    assert "[b]" not in plain and "[dim]" not in plain
    assert "\\[" not in plain  # no escape artifacts in plain mode
    assert "[doctor]" in plain  # literal button name still shown


def test_to_dict_is_jsonable():
    import json
    d = cat.to_dict()
    json.dumps(d)  # must not raise
    assert d["counts"]["total"] == len(cat.all_workflows())


def test_every_workflow_has_a_valid_tier():
    from sovereign_agent.workflow.catalog import WORKFLOW_TIER
    for w in cat.all_workflows():
        assert 0 <= w.tier <= 3
        assert w.tier in WORKFLOW_TIER
        assert w.tier_label  # renders a badge string


def test_all_four_tiers_are_represented():
    tiers = {w.tier for w in cat.all_workflows()}
    assert tiers == {0, 1, 2, 3}


def test_tutorials_are_well_formed_when_present():
    tutored = [w for w in cat.all_workflows() if w.has_tutorial]
    assert tutored, "expected at least some workflows to ship a tutorial"
    for w in tutored:
        assert all(isinstance(step, str) and step.strip() for step in w.tutorial)


def test_workflow_sentinel_card_present_and_demoable():
    w = cat.get("workflow.sentinel")
    assert w is not None
    assert w.is_demoable and w.tier == 3
    assert w.has_tutorial


def test_render_shows_tier_badges():
    plain = cat.render_text(color=False)
    assert "God Tier" in plain or "[T3" in plain
    assert "tutorial:" in plain  # walkthrough rendered on tutored cards
