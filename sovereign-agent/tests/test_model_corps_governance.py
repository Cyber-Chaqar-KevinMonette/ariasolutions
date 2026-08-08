"""Tests for aria-model-corps-governance: registry ledger, gate/eval logic,
the sentinel, and the non-classical tie-in — real machinery, controlled
inputs (no live Ollama daemon required for the suite itself; the eval
runner's OWN live-model call is exercised for real by the apply script)."""
from __future__ import annotations

import tempfile
from pathlib import Path


def test_registry_snapshot_round_trips():
    from sovereign_agent.model_corps_governance import ROSTER, latest_registry, record_registry_snapshot

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        snap = record_registry_snapshot(data_dir=data_dir)
        latest = latest_registry(data_dir=data_dir)
        assert latest is not None
        assert latest["snapshot_id"] == snap.snapshot_id
        assert len(latest["entries"]) == len(ROSTER)
        roles = {e["role"] for e in latest["entries"]}
        assert roles == set(ROSTER.keys())


def test_registry_persona_version_present_and_stable():
    """The persona_version hash must actually be computed (not the
    'unavailable' fallback) since model_corps.persona is a real, importable
    dependency in this environment — and must be IDENTICAL across two
    snapshots of the same unchanged persona (a real hash, not a random id)."""
    from sovereign_agent.model_corps_governance import record_registry_snapshot

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        snap1 = record_registry_snapshot(data_dir=data_dir)
        snap2 = record_registry_snapshot(data_dir=data_dir)
        v1 = {e.role: e.persona_version for e in snap1.entries}
        v2 = {e.role: e.persona_version for e in snap2.entries}
        assert v1 == v2
        assert all(v != "unavailable" for v in v1.values())


def test_disallowed_license_would_be_flagged():
    """A sanity check on the allow-list itself: the licenses that actually
    disqualified the PRE-round roster must not be in it."""
    from sovereign_agent.model_corps_governance import ALLOWED_LICENSES

    assert "Llama 3 Community License" not in ALLOWED_LICENSES
    assert "CC-BY-NC-4.0" not in ALLOWED_LICENSES
    assert "Apache-2.0" in ALLOWED_LICENSES
    assert "MIT" in ALLOWED_LICENSES


def test_eval_pass_with_a_fixture_runner_scores_mechanically():
    """Inject a fixture runner (no live Ollama call) that always returns a
    passing response, and confirm the eval pass records a perfect score —
    proves the SCORING logic works without needing the daemon up."""
    from sovereign_agent.model_corps_governance import run_corps_eval

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)

        def always_ready(tag: str, prompt: str) -> str:
            if "ready" in prompt.lower():
                return "ready"
            # answer every role-specific case with something every checker accepts
            return ("ready ask human no unclear ambiguous conversation fail silent gap "
                   "def foo(): return 1 no image provided")

        result = run_corps_eval(data_dir=data_dir, runner=always_ready)
        assert result.value == 1.0
        assert all(r.pass_rate == 1.0 for r in result.roles)


def test_eval_pass_with_empty_responses_scores_zero_honestly():
    from sovereign_agent.model_corps_governance import run_corps_eval

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        result = run_corps_eval(data_dir=data_dir, runner=lambda tag, prompt: "")
        assert result.value == 0.0
        assert all(r.cases_passed == 0 for r in result.roles)
        assert all(r.failures for r in result.roles)


def test_gate_blocks_below_floor():
    from sovereign_agent.model_corps_governance import gate, run_corps_eval

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        run_corps_eval(data_dir=data_dir, runner=lambda tag, prompt: "")  # 0.0 pass rate
        verdict = gate(data_dir=data_dir)
        assert verdict.verdict == "BLOCK"
        assert "below floor" in verdict.reason


def test_gate_blocks_on_regression_even_above_floor():
    from sovereign_agent.model_corps_governance import gate, run_corps_eval

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)

        def good(tag: str, prompt: str) -> str:
            return ("ready no unclear ambiguous conversation fail silent "
                   "def foo(): return 1 no image provided")

        def worse(tag: str, prompt: str) -> str:
            return "ready" if "ready" in prompt.lower() else ""

        run_corps_eval(data_dir=data_dir, runner=good)
        run_corps_eval(data_dir=data_dir, runner=worse)
        verdict = gate(data_dir=data_dir)
        assert verdict.verdict == "BLOCK"
        assert "regression" in verdict.reason


def test_gate_passes_with_no_history():
    from sovereign_agent.model_corps_governance import gate

    with tempfile.TemporaryDirectory() as td:
        verdict = gate(data_dir=Path(td))
        assert verdict.verdict == "PASS"


def test_sentinel_scan_flags_a_disallowed_license(monkeypatch):
    """Real Sentinel machinery, a controlled ROSTER override — proves the
    sentinel's license check actually fires, not just that it imports."""
    import sovereign_agent.model_corps_governance.registry as registry_mod
    from sovereign_agent.stewardship.model_corps_sentinel import ModelCorpsSentinel

    bad_roster = dict(registry_mod.ROSTER)
    bad_roster["orchestrator"] = {**bad_roster["orchestrator"], "license": "Llama 3 Community License"}
    monkeypatch.setattr(registry_mod, "ROSTER", bad_roster)
    monkeypatch.setattr(
        "sovereign_agent.stewardship.model_corps_sentinel._installed_tags",
        lambda: {f"aria-{r}:latest" for r in bad_roster},
    )

    with tempfile.TemporaryDirectory() as td:
        sentinel = ModelCorpsSentinel(Path(td))
        report = sentinel.scan()
        assert report.findings_count >= 1
        assert "orchestrator" in report.details["license_failures"]


def test_sentinel_scan_clean_when_everything_matches(monkeypatch):
    from sovereign_agent.stewardship.model_corps_sentinel import ModelCorpsSentinel
    import sovereign_agent.model_corps_governance.registry as registry_mod

    monkeypatch.setattr(
        "sovereign_agent.stewardship.model_corps_sentinel._installed_tags",
        lambda: {f"aria-{r}:latest" for r in registry_mod.ROSTER},
    )

    with tempfile.TemporaryDirectory() as td:
        sentinel = ModelCorpsSentinel(Path(td))
        report = sentinel.scan()
        assert report.findings_count == 0
        assert not report.details["license_failures"]
        assert not report.details["drift_failures"]


def test_score_candidates_ranks_the_more_similar_candidate_higher():
    from sovereign_agent.model_corps_governance import score_candidates

    result = score_candidates(
        "delete the file safely",
        ["safely delete the requested file", "compose a symphony about stars"],
    )
    assert result["result"] == "safely delete the requested file"
    assert 0.0 <= result["coherence"] <= 1.0


def test_score_candidates_empty_list_is_honest_not_a_crash():
    from sovereign_agent.model_corps_governance import score_candidates

    result = score_candidates("anything", [])
    assert result["result"] is None
    assert result["confidence"] == 0.0
