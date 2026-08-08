"""Tests for catalog-command-d.

Kevin, 2026-07-25: "I always ask her what she would like for me to have
her do. Let's make it where she can always find a grand catalog of
things that I could have her do or work on, and sessions I could have
her resume/continue." Deliberately read-only and non-generative — every
entry must already genuinely exist (a real resumable session, a real
open diagnosis.py case, a real note Kevin left) — never an invented
suggestion (that would brush the standing autonomous-goal-generation
limit).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from sovereign_agent.catalog import compose_catalog


def test_empty_state_says_so_plainly_not_silently(tmp_path):
    text = compose_catalog(tmp_path)
    assert "nothing paused" in text
    assert "no open mistake" in text
    assert "nothing pending" in text


def test_never_invents_a_goal():
    """The whole point: no LLM call, no generated suggestion text --
    only real, already-existing items ever appear."""
    import inspect
    from sovereign_agent import catalog

    src = inspect.getsource(catalog)
    assert "ollama" not in src.lower()
    assert "llm" not in src.lower()


def test_shows_a_real_resumable_session(tmp_path):
    fake_session = type("S", (), {
        "session_id": "sess-abc123", "status": "paused", "goal": "fix the parser",
        "subtasks": [],
    })()
    with patch("sovereign_agent.session_bridge.resumable_sessions",
              return_value=[fake_session]), \
         patch("sovereign_agent.session_bridge.resume_blocked_reason", return_value=None):
        text = compose_catalog(tmp_path)

    assert "fix the parser" in text
    assert "/resume" in text


def test_shows_why_a_session_is_blocked_not_just_that_it_is(tmp_path):
    fake_session = type("S", (), {
        "session_id": "sess-abc123", "status": "paused", "goal": "fix the parser",
        "subtasks": [],
    })()
    with patch("sovereign_agent.session_bridge.resumable_sessions",
              return_value=[fake_session]), \
         patch("sovereign_agent.session_bridge.resume_blocked_reason",
              return_value="mode 'companion' does not run work sessions"):
        text = compose_catalog(tmp_path)

    assert "blocked:" in text
    assert "companion" in text


def test_shows_a_real_open_mistake_case(tmp_path):
    from sovereign_agent.aria_xp import record_mistake

    record_mistake(
        what_happened="wrote to the wrong store",
        how_to_avoid="check which store a tool actually writes to",
        data_dir=tmp_path,
    )
    text = compose_catalog(tmp_path)
    assert "wrote to the wrong store" in text


def test_resolved_mistake_cases_are_not_listed_as_still_open(tmp_path):
    from sovereign_agent.diagnosis import ConflictCatalog

    catalog_obj = ConflictCatalog(tmp_path / "diagnoses")
    c = catalog_obj.open_conflict(type="drift", trigger_event="a resolved thing", actor="aria")
    catalog_obj.diagnose(c.case_id, symptom_vs_cause="summary", actor="aria")
    catalog_obj.resolve(c.case_id, fix_applied="fixed it", rollback_plan="revert",
                        actor="aria", verification_result="confirmed")

    text = compose_catalog(tmp_path)
    assert "a resolved thing" not in text
    assert "no open mistake" in text


@pytest.mark.asyncio
async def test_catalog_slash_command_wired():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch.object(app, "_show_catalog") as handler:
            app._handle_slash("/catalog")
        handler.assert_called_once()


@pytest.mark.asyncio
async def test_show_catalog_degrades_gracefully_on_failure():
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test() as pilot:
        app = pilot.app
        with patch("sovereign_agent.catalog.compose_catalog",
                  side_effect=RuntimeError("boom")), \
             patch.object(app, "_write_meta") as write_meta:
            app._show_catalog()  # must not raise

        messages = " ".join(c.args[0] for c in write_meta.call_args_list)
        assert "catalog unavailable" in messages
