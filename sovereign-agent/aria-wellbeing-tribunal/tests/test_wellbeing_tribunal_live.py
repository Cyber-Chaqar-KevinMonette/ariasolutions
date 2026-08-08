"""aria-wellbeing-tribunal — standing audit + measured angel lens.
(Wellbeing round · W3)

Both patched files (spectrum/lenses.py, stewardship/wellbeing_sentinel.py)
are IN-PLACE patches to existing, already-live files — patch-dependent,
skip honestly pre-apply; the apply script re-runs this file and requires
zero skips.
"""
from __future__ import annotations

import inspect
import json


def _patched(obj) -> bool:
    return "wellbeing-tribunal-d" in inspect.getsource(obj)


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


HEALTHY_EVENTS = [
    {"flag": "commit-d", "payload": {"message": "fix the loader bug"}},
    {"flag": "presence-note-d", "payload": {}},
]


# ─── (1) angel lens: measured composite over live-only ────────────────────


def test_angel_unaffected_when_no_measured_keys_present():
    from sovereign_agent.spectrum.lenses import angel

    read = angel("a plain string proposal with no dict keys at all")
    assert read.lens == "angel"


def test_angel_prefers_the_measured_love_grade():
    import pytest

    from sovereign_agent.spectrum.lenses import angel

    if not _patched(angel):
        pytest.skip("pre-apply: angel lens not yet patched")
    high = angel({"love_grade": "A"})
    assert high.score > 0.5
    assert any("measured" in g for g in high.gifts)

    low = angel({"love_grade": "D"})
    assert low.score < 0.0


def test_angel_measured_reject_for_the_future_forces_a_low_score():
    import pytest

    from sovereign_agent.spectrum.lenses import angel

    if not _patched(angel):
        pytest.skip("pre-apply: angel lens not yet patched")
    read = angel({"love_grade": "A", "flourishing_verdict": "reject-for-the-future"})
    assert read.score <= -0.6
    assert any("reject-for-the-future" in c for c in read.concerns)


def test_angel_prose_fallback_still_works_with_a_plain_dict():
    import pytest

    from sovereign_agent.spectrum.lenses import angel

    if not _patched(angel):
        pytest.skip("pre-apply: angel lens not yet patched")
    read = angel({"text": "a proposal that protects safety and future generations"})
    assert read.lens == "angel"
    assert not any("measured" in g for g in read.gifts)


# ─── (2) the standing scan phase ──────────────────────────────────────────


def test_sentinel_standing_phase_logs_a_well_diagnosis_case():
    import pytest

    from sovereign_agent.config import SETTINGS
    from sovereign_agent.stewardship.wellbeing_sentinel import WellbeingSentinel

    if not _patched(WellbeingSentinel):
        pytest.skip("pre-apply: wellbeing_sentinel.py standing phase not yet patched")

    _write_events_file(SETTINGS.paths.data_dir, HEALTHY_EVENTS)
    sentinel = WellbeingSentinel(SETTINGS.paths.data_dir)
    sentinel.scan()

    standing = sentinel.load_catalog(name="standing-audit")
    assert standing is not None
    assert standing.get("case_id", "").startswith("WELL")

    from sovereign_agent.diagnosis import ConflictCatalog

    cat = ConflictCatalog(SETTINGS.paths.data_dir / "diagnosis")
    conflict = cat.get_conflict(standing["case_id"])
    assert conflict is not None
    assert conflict.type == "ambiguity"


def test_sentinel_standing_phase_never_breaks_the_scan_on_failure(monkeypatch):
    """Even if the standing-audit phase itself explodes, scan() must still
    return a real report — it's best-effort, never load-bearing for the
    wellbeing pass itself."""
    import pytest

    from sovereign_agent.config import SETTINGS
    from sovereign_agent.stewardship.wellbeing_sentinel import WellbeingSentinel

    if not _patched(WellbeingSentinel):
        pytest.skip("pre-apply: wellbeing_sentinel.py standing phase not yet patched")

    import sovereign_agent.tribunal as tribunal_pkg

    def _boom(*a, **k):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(tribunal_pkg, "convene", _boom)

    _write_events_file(SETTINGS.paths.data_dir, HEALTHY_EVENTS)
    sentinel = WellbeingSentinel(SETTINGS.paths.data_dir)
    report = sentinel.scan()   # must not raise
    assert report is not None


def test_sentinel_standing_phase_skips_cleanly_with_nothing_to_score():
    import pytest

    from sovereign_agent.config import SETTINGS
    from sovereign_agent.stewardship.wellbeing_sentinel import WellbeingSentinel

    if not _patched(WellbeingSentinel):
        pytest.skip("pre-apply: wellbeing_sentinel.py standing phase not yet patched")

    sentinel = WellbeingSentinel(SETTINGS.paths.data_dir)
    report = sentinel.scan()
    assert report is not None
    assert sentinel.load_catalog(name="standing-audit") is None
