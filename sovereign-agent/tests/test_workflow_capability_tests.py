"""Tests for workflow.capability_tests — the ⚡ real capability test runner.

Mirrors tests/test_workflow_demo.py's structure and safety-property coverage.
Key divergence: real GPU/network calls in CAPABILITY_TEST_FNS are NOT safe or
fast enough for CI, so the green-path/observability/journal tests monkeypatch
the whole dict to cheap stand-ins. The three capability tests that need
neither GPU nor network (create.marketing_brief, create.discord_tracker,
create.discord_bot_command) are exercised for real, directly, at the bottom —
proving the actual wiring works at least once, not just the mocked shape.
"""
from __future__ import annotations

import itertools
from pathlib import Path

from sovereign_agent.workflow import capability_tests as ct
from sovereign_agent.workflow import catalog as cat


def _clock():
    return itertools.count(1000.0, 0.5).__next__


def _fake_fns():
    """Cheap, instant stand-ins for every real cap-testable wid — used
    whenever a test needs the WHOLE run to be fast/safe, not just one probe."""
    return {
        w.wid: (lambda ctx, _wid=w.wid: (f"fake pass for {_wid}", None))
        for w in cat.capability_testable_workflows()
    }


def test_cap_test_fns_match_capability_testable_workflows_lockstep():
    # The compatibility invariant: every cap-testable workflow has a real
    # test, and every test maps to a cap-testable workflow. The ▸ flows menu
    # and the ⚡ test menu can never silently diverge.
    assert set(ct.CAPABILITY_TEST_FNS.keys()) == {
        w.wid for w in cat.capability_testable_workflows()}


def test_capability_tests_run_all_green_when_mocked_cheap(tmp_path, monkeypatch):
    monkeypatch.setattr(ct, "CAPABILITY_TEST_FNS", _fake_fns())
    rep = ct.run_capability_tests(out_root=str(tmp_path), clock=_clock(),
                                  sleep=lambda s: None)
    assert rep.ran is True
    assert rep.failed == 0
    assert rep.passed == len(cat.capability_testable_workflows())
    assert rep.queued == len(cat.capability_testable_workflows())
    assert "COMPLETE" in rep.verdict


def test_capability_tests_write_a_journal_and_session(tmp_path, monkeypatch):
    monkeypatch.setattr(ct, "CAPABILITY_TEST_FNS", _fake_fns())
    rep = ct.run_capability_tests(out_root=str(tmp_path), clock=_clock(),
                                  sleep=lambda s: None)
    assert rep.journal_path is not None
    out_dir = Path(rep.journal_path)
    assert (out_dir / "journal.md").exists()
    assert (out_dir / "session.json").exists()


def test_capability_tests_refuse_when_halted_preflight(tmp_path):
    rep = ct.run_capability_tests(out_root=str(tmp_path), should_stop=lambda: True,
                                  clock=_clock(), sleep=lambda s: None)
    assert rep.ran is False
    assert rep.reason in ("halted_preflight", "kill_switch")
    assert rep.passed == 0


def test_capability_tests_stay_in_their_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(ct, "CAPABILITY_TEST_FNS", _fake_fns())
    ct.run_capability_tests(out_root=str(tmp_path), clock=_clock(), sleep=lambda s: None)
    run_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert run_dirs, "expected a timestamped run dir under out_root"
    sandboxes = list(tmp_path.rglob("sandbox"))
    assert sandboxes, "expected a sandbox dir under the run dir"
    assert all(str(s).startswith(str(tmp_path)) for s in sandboxes)


def test_one_broken_capability_test_does_not_sink_the_run(tmp_path, monkeypatch):
    fakes = _fake_fns()
    target = next(iter(fakes))

    def boom(ctx):
        raise RuntimeError("deliberate test failure")

    fakes[target] = boom
    monkeypatch.setattr(ct, "CAPABILITY_TEST_FNS", fakes)

    rep = ct.run_capability_tests(out_root=str(tmp_path), clock=_clock(),
                                  sleep=lambda s: None)
    assert rep.ran is True
    assert rep.failed == 1
    assert rep.passed == len(cat.capability_testable_workflows()) - 1
    bad = [r for r in rep.results if r.wid == target]
    assert bad and bad[0].status == "fail"


def test_a_skipped_capability_test_is_not_counted_as_a_failure(tmp_path, monkeypatch):
    fakes = _fake_fns()
    target = next(iter(fakes))

    def offline(ctx):
        raise ct.CapTestSkipped("internet unavailable — never ran")

    fakes[target] = offline
    monkeypatch.setattr(ct, "CAPABILITY_TEST_FNS", fakes)

    rep = ct.run_capability_tests(out_root=str(tmp_path), clock=_clock(),
                                  sleep=lambda s: None)
    assert rep.failed == 0
    assert rep.skipped == 1
    assert rep.passed == len(cat.capability_testable_workflows()) - 1
    skipped = [r for r in rep.results if r.wid == target]
    assert skipped and skipped[0].status == "skip"


def test_artifact_path_is_recorded_when_a_test_reports_one(tmp_path, monkeypatch):
    fakes = _fake_fns()
    target = next(iter(fakes))
    fakes[target] = lambda ctx: ("made a thing", "/tmp/fake/artifact.png")
    monkeypatch.setattr(ct, "CAPABILITY_TEST_FNS", fakes)

    rep = ct.run_capability_tests(out_root=str(tmp_path), clock=_clock(),
                                  sleep=lambda s: None)
    hit = [r for r in rep.results if r.wid == target]
    assert hit and hit[0].artifact_path == "/tmp/fake/artifact.png"


def test_selected_wids_runs_only_the_chosen_subset(tmp_path, monkeypatch):
    monkeypatch.setattr(ct, "CAPABILITY_TEST_FNS", _fake_fns())
    wid = next(iter(ct.CAPABILITY_TEST_FNS))
    rep = ct.run_capability_tests([wid], out_root=str(tmp_path), clock=_clock(),
                                  sleep=lambda s: None)
    assert rep.queued == 1
    assert rep.passed == 1
    assert rep.results[0].wid == wid


def test_events_are_emitted_for_observability(tmp_path, monkeypatch):
    monkeypatch.setattr(ct, "CAPABILITY_TEST_FNS", _fake_fns())
    kinds = []
    ct.run_capability_tests(out_root=str(tmp_path),
                            on_event=lambda e: kinds.append(e.kind),
                            clock=_clock(), sleep=lambda s: None)
    assert "start" in kinds and "queued" in kinds
    assert "running" in kinds and "step" in kinds and "done" in kinds


# ─── real, un-mocked wiring proofs — no GPU, no network, always safe ───────


def test_real_marketing_brief_capability_test_actually_works(tmp_path):
    detail, artifact = ct.CAPABILITY_TEST_FNS["create.marketing_brief"](
        ct.CapTestContext(sandbox=tmp_path))
    assert "5" in detail or "sections" in detail


def test_real_discord_tracker_capability_test_actually_works(tmp_path):
    detail, artifact = ct.CAPABILITY_TEST_FNS["create.discord_tracker"](
        ct.CapTestContext(sandbox=tmp_path))
    assert "categories" in detail and "channels" in detail


def test_real_discord_bot_command_capability_test_actually_works(tmp_path):
    detail, artifact = ct.CAPABILITY_TEST_FNS["create.discord_bot_command"](
        ct.CapTestContext(sandbox=tmp_path))
    assert "commands" in detail
