"""aria-wellbeing-ledger — the persisted composite value/care/flourishing
score. (Wellbeing round · W1)

`wellbeing/__init__.py`, `wellbeing/ledger.py` are brand-new submodules —
reachable pre-apply via path extension. `stewardship/wellbeing_sentinel.py`
is also new (a new file, not an in-place patch) — reachable the same way.
`stewardship/__init__.py`'s registration line and `tools/companion_tools.py`'s
event-glob bug fix are patch-dependent.
"""
from __future__ import annotations

import inspect
import json


def _patched(obj) -> bool:
    return "wellbeing-sentinel-d" in inspect.getsource(obj)


HEALTHY_EVENTS = [
    {"flag": "commit-d", "payload": {"message": "fix the loader bug"}},
    {"flag": "presence-note-d", "payload": {}},
    {"flag": "hypothesis-d", "payload": {"question": "does this hold?"}},
]


# ─── wellbeing/ledger.py ───────────────────────────────────────────────────


def test_record_wellbeing_pass_healthy_events_scores_healthy(tmp_path):
    from sovereign_agent.wellbeing import record_wellbeing_pass

    result = record_wellbeing_pass(HEALTHY_EVENTS, data_dir=tmp_path)
    assert result.verdict == "healthy"
    assert result.accomplished_count >= 1


def test_record_wellbeing_pass_zombie_iv_scores_strained(tmp_path):
    from sovereign_agent.stewardship.msims import (
        Cell, Dimension, ImpactVector, Scale,
    )
    from sovereign_agent.wellbeing import record_wellbeing_pass

    iv = ImpactVector()
    iv.set(Dimension.MENTAL, Scale.MICRO, Cell(value=0.0, confidence=0.9))
    iv.set(Dimension.MENTAL, Scale.MESO, Cell(value=0.0, confidence=0.9))
    iv.set(Dimension.MENTAL, Scale.MACRO, Cell(value=-0.5, confidence=0.9))
    assert iv.is_zombie() is True  # confirm the fixture actually triggers it

    result = record_wellbeing_pass(HEALTHY_EVENTS, iv=iv, data_dir=tmp_path)
    assert result.impact_is_zombie is True
    assert result.verdict == "strained"


def test_record_wellbeing_pass_empty_is_honest_not_a_false_strain(tmp_path):
    from sovereign_agent.wellbeing import record_wellbeing_pass

    result = record_wellbeing_pass([], data_dir=tmp_path)
    assert result.event_count_analyzed == 0
    assert result.verdict == "healthy"  # vacuously — nothing to check


def test_pass_persists_and_round_trips_through_the_ledger(tmp_path):
    from sovereign_agent.wellbeing import latest_wellbeing, record_wellbeing_pass

    result = record_wellbeing_pass(HEALTHY_EVENTS, data_dir=tmp_path)
    latest = latest_wellbeing(tmp_path)
    assert latest is not None
    assert latest["pass_id"] == result.pass_id
    assert latest["verdict"] == result.verdict


def test_flourishing_verdict_only_runs_when_decision_text_is_given(tmp_path):
    from sovereign_agent.wellbeing import record_wellbeing_pass

    # absent decision_text: no flourishing check at all — honest skip,
    # never a fabricated verdict from scoring the wrong kind of text.
    result = record_wellbeing_pass(HEALTHY_EVENTS, data_dir=tmp_path)
    assert result.flourishing_verdict == ""
    assert result.verdict == "healthy"


def test_flourishing_verdict_scores_real_decision_text_when_given(tmp_path):
    from sovereign_agent.wellbeing import record_wellbeing_pass

    reversible_text = "This is a reversible, staged change with a rollback plan."
    result = record_wellbeing_pass(
        HEALTHY_EVENTS, data_dir=tmp_path, decision_text=reversible_text)
    assert result.flourishing_verdict == "carry-forward"

    lockin_text = "This permanently hardcodes the value everywhere, forever."
    result2 = record_wellbeing_pass(
        [], data_dir=tmp_path, decision_text=lockin_text)
    assert result2.flourishing_verdict in ("escalate", "reject-for-the-future")
    assert result2.verdict == "strained"


def test_wellbeing_trend_insufficient_history_then_stable(tmp_path):
    from sovereign_agent.wellbeing import record_wellbeing_pass, wellbeing_trend

    assert wellbeing_trend(data_dir=tmp_path) == "insufficient-history"
    record_wellbeing_pass(HEALTHY_EVENTS, data_dir=tmp_path)
    record_wellbeing_pass(HEALTHY_EVENTS, data_dir=tmp_path)
    assert wellbeing_trend(data_dir=tmp_path) == "stable"


# ─── stewardship/wellbeing_sentinel.py ─────────────────────────────────────


def _write_events_file(data_dir, events):
    from datetime import datetime, timezone

    events_dir = data_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = events_dir / f"events-{today}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for e in events:
            e = dict(e)
            e.setdefault("ts", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
            fh.write(json.dumps(e) + "\n")


def test_sentinel_scan_scores_real_event_fixtures():
    import pytest

    from sovereign_agent.config import SETTINGS
    from sovereign_agent.tools import companion_tools
    from sovereign_agent.stewardship.wellbeing_sentinel import WellbeingSentinel

    if not _patched(companion_tools._load_recent_events_for_report):
        pytest.skip("pre-apply: companion_tools.py events glob not yet patched "
                    "(the sentinel reads events through the still-buggy glob)")
    # _load_recent_events_for_report() has no data_dir override — it always
    # reads live SETTINGS.paths, so the sentinel must be pointed at the
    # same directory for its own catalog storage to line up with what it
    # actually scans (this is a real, load-bearing asymmetry, not a
    # test-only quirk — see the ledger's own docstring on decision_text).
    _write_events_file(SETTINGS.paths.data_dir, HEALTHY_EVENTS)
    sentinel = WellbeingSentinel(SETTINGS.paths.data_dir)
    report = sentinel.scan()
    assert report.details["events_scanned"] >= 1
    assert report.details["pass"]["verdict"] == "healthy"


def test_sentinel_scan_empty_vessel_is_honest():
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.stewardship.wellbeing_sentinel import WellbeingSentinel

    sentinel = WellbeingSentinel(SETTINGS.paths.data_dir)
    report = sentinel.scan()
    assert report.details["events_scanned"] == 0
    assert "nothing to score" in report.summary


def test_sentinel_notifies_on_strained_verdict():
    import pytest

    from sovereign_agent.config import SETTINGS
    from sovereign_agent.tools import companion_tools
    from sovereign_agent.stewardship.wellbeing_sentinel import WellbeingSentinel

    if not _patched(companion_tools._load_recent_events_for_report):
        pytest.skip("pre-apply: companion_tools.py events glob not yet patched")
    _write_events_file(SETTINGS.paths.data_dir, [{"flag": "unrecognized-flag-d", "payload": {}}])
    sentinel = WellbeingSentinel(SETTINGS.paths.data_dir)
    sentinel.scan()
    health = sentinel.health_status()
    assert health.level == "warning"


def test_sentinel_bookmark_advances_so_the_same_events_are_not_rescored():
    import pytest

    from sovereign_agent.config import SETTINGS
    from sovereign_agent.tools import companion_tools
    from sovereign_agent.stewardship.wellbeing_sentinel import WellbeingSentinel

    if not _patched(companion_tools._load_recent_events_for_report):
        pytest.skip("pre-apply: companion_tools.py events glob not yet patched")
    _write_events_file(SETTINGS.paths.data_dir, HEALTHY_EVENTS)
    sentinel = WellbeingSentinel(SETTINGS.paths.data_dir)
    first = sentinel.scan()
    assert first.details["events_scanned"] >= 1
    second = sentinel.scan()
    assert second.details["events_scanned"] == 0


# ─── companion_tools.py event-glob bug fix (patch-dependent) ──────────────


def test_load_recent_events_for_report_finds_real_event_files_once_patched():
    import pytest

    from sovereign_agent.config import SETTINGS
    from sovereign_agent.tools import companion_tools

    if not _patched(companion_tools._load_recent_events_for_report):
        pytest.skip("pre-apply: companion_tools.py events glob not yet patched")
    # this helper has no data_dir override — it always reads live
    # SETTINGS.paths, isolated per-test by the autouse fixture above.
    _write_events_file(SETTINGS.paths.data_dir, HEALTHY_EVENTS)
    events = companion_tools._load_recent_events_for_report(100)
    assert len(events) == len(HEALTHY_EVENTS)


# ─── stewardship/__init__.py registration (patch-dependent) ───────────────


def test_wellbeing_sentinel_registered_once_patched():
    import pytest

    from sovereign_agent import stewardship

    if "wellbeing-sentinel-d" not in inspect.getsource(stewardship):
        pytest.skip("pre-apply: stewardship/__init__.py not yet patched")
    from sovereign_agent.stewardship.registry import registered_ids

    assert "wellbeing" in registered_ids()
