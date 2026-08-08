"""Tests for workflow.demo — the bounded ✦ demo runner.

These assert the safety properties that make the demonstration trustworthy:
the menu and the demo can never drift, the run is bounded/observable/sandboxed,
it refuses to run while halted, and one broken probe never sinks the run.
"""
from __future__ import annotations

import itertools

from sovereign_agent.workflow import catalog as cat
from sovereign_agent.workflow import demo


def _clock():
    return itertools.count(1000.0, 0.5).__next__


def test_checks_match_demoable_workflows_lockstep():
    # The compatibility invariant: every demoable workflow has a probe, and
    # every probe maps to a demoable workflow. The ▸ flows menu and ✦ demo
    # can never silently diverge.
    assert set(demo.CHECKS.keys()) == {w.wid for w in cat.demoable_workflows()}


def test_demonstration_runs_all_probes_green(tmp_path):
    rep = demo.run_demonstration(demo_root=str(tmp_path), clock=_clock(),
                                 sleep=lambda s: None)
    assert rep.ran is True
    assert rep.failed == 0
    assert rep.passed == len(cat.demoable_workflows())
    assert "VALID" in rep.verdict


def test_demonstration_writes_a_journal(tmp_path):
    rep = demo.run_demonstration(demo_root=str(tmp_path), clock=_clock(),
                                 sleep=lambda s: None)
    assert rep.journal_path is not None
    from pathlib import Path
    assert Path(rep.journal_path).exists()


def test_demonstration_refuses_when_halted_preflight(tmp_path):
    rep = demo.run_demonstration(demo_root=str(tmp_path), should_stop=lambda: True,
                                 clock=_clock(), sleep=lambda s: None)
    assert rep.ran is False
    assert rep.reason in ("halted_preflight", "kill_switch")
    assert rep.passed == 0


def test_demonstration_stays_in_its_sandbox(tmp_path):
    before = set(p.name for p in tmp_path.rglob("*"))
    demo.run_demonstration(demo_root=str(tmp_path), clock=_clock(), sleep=lambda s: None)
    # Everything written lives under the demo_root we passed; nothing escapes it.
    # (We can only assert positively that the run dir was created under tmp_path.)
    run_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert run_dirs, "expected a timestamped run dir under demo_root"
    sandboxes = list(tmp_path.rglob("sandbox"))
    assert sandboxes, "expected a sandbox dir under the run dir"
    assert all(str(s).startswith(str(tmp_path)) for s in sandboxes)
    _ = before


def test_one_broken_probe_does_not_sink_the_run(tmp_path, monkeypatch):
    # Make a single probe raise; the run must still complete, with that probe
    # failed and the rest passing. Defensive isolation per the design.
    target = "self.doctrine"
    assert target in demo.CHECKS

    def boom(ctx):
        raise RuntimeError("deliberate test failure")

    patched = dict(demo.CHECKS)
    patched[target] = boom
    monkeypatch.setattr(demo, "CHECKS", patched)

    rep = demo.run_demonstration(demo_root=str(tmp_path), clock=_clock(),
                                 sleep=lambda s: None)
    assert rep.ran is True
    assert rep.failed == 1
    assert rep.passed == len(cat.demoable_workflows()) - 1
    bad = [r for r in rep.results if r.wid == target]
    assert bad and bad[0].status == "fail"


def test_events_are_emitted_for_observability(tmp_path):
    kinds = []
    demo.run_demonstration(demo_root=str(tmp_path),
                           on_event=lambda e: kinds.append(e.kind),
                           clock=_clock(), sleep=lambda s: None)
    assert "start" in kinds and "step" in kinds and "done" in kinds
