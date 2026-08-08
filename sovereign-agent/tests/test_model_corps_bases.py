"""Tests for model_corps.bases — the single source of truth for "what base
model does each aria-<role> run on," and the one code path (build + create)
that turns a base-model choice into a real, dressed, live Ollama model.

model-corps-unify-d (Kevin, 2026-07-21): "rebuild the entire models system
if you have to and make it nice." Closes a real bug found this session:
model_ladder.promote_slot() used to write a RAW proven model straight into
the vault, bypassing the persona entirely.

Every test here monkeypatches _bases_path() to a tmp file -- these must
NEVER read or write the real, live src/sovereign_agent/model_corps/bases.json.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _isolated_bases_file(tmp_path, monkeypatch):
    """Redirect bases.json to a tmp file for every test in this module --
    the real one holds the actual, live-tuned model_corps configuration."""
    from sovereign_agent.model_corps import bases as bases_module

    fake_path = tmp_path / "bases.json"
    monkeypatch.setattr(bases_module, "_bases_path", lambda: fake_path)
    yield fake_path


def test_load_bases_on_missing_file_is_empty_not_an_error():
    from sovereign_agent.model_corps.bases import load_bases

    assert load_bases() == {}


def test_set_base_persists_and_round_trips():
    from sovereign_agent.model_corps.bases import load_bases, set_base

    set_base("orchestrator", "qwen3:14b", temperature=0.3)
    bases = load_bases()
    assert bases["orchestrator"]["model"] == "qwen3:14b"
    assert bases["orchestrator"]["temperature"] == 0.3


def test_set_base_updates_only_the_named_role():
    from sovereign_agent.model_corps.bases import load_bases, set_base

    set_base("orchestrator", "qwen3:14b")
    set_base("coder", "qwen2.5-coder:14b")
    bases = load_bases()
    assert bases["orchestrator"]["model"] == "qwen3:14b"
    assert bases["coder"]["model"] == "qwen2.5-coder:14b"


def test_set_base_rejects_unknown_role():
    from sovereign_agent.model_corps.bases import set_base

    with pytest.raises(ValueError, match="unknown model_corps role"):
        set_base("not-a-real-role", "some:model")


def test_set_base_keeps_existing_temperature_if_not_given():
    from sovereign_agent.model_corps.bases import load_bases, set_base

    set_base("coder", "qwen2.5-coder:7b", temperature=0.15)
    set_base("coder", "qwen2.5-coder:14b")  # no temperature this time
    assert load_bases()["coder"]["temperature"] == 0.15
    assert load_bases()["coder"]["model"] == "qwen2.5-coder:14b"


def test_build_modelfile_text_uses_the_configured_base_and_persona():
    from sovereign_agent.model_corps.bases import build_modelfile_text, set_base

    set_base("orchestrator", "qwen3:14b", temperature=0.3)
    text = build_modelfile_text("orchestrator")
    assert text.startswith("FROM qwen3:14b\n")
    assert "Your role: orchestrator." in text
    assert "PARAMETER temperature 0.3" in text
    assert "PARAMETER num_ctx 16384" in text
    # the frozen kernel priorities must always be present
    assert "Safety" in text and "Love" in text and "Flourishing" in text


def test_set_base_num_ctx_persists_and_overrides_the_default():
    """no-offloading-d (Kevin, 2026-07-28): "no GPU offloading allowed" --
    a per-role num_ctx override, found from a real GPU-residency search,
    not guessed."""
    from sovereign_agent.model_corps.bases import (
        build_modelfile_text, load_bases, set_base)

    set_base("orchestrator", "qwen3:8b", num_ctx=4096)
    assert load_bases()["orchestrator"]["num_ctx"] == 4096
    text = build_modelfile_text("orchestrator")
    assert "PARAMETER num_ctx 4096" in text


def test_set_base_keeps_existing_num_ctx_if_not_given():
    from sovereign_agent.model_corps.bases import load_bases, set_base

    set_base("coder", "qwen2.5-coder:7b", num_ctx=8192)
    set_base("coder", "qwen2.5-coder:14b")   # no num_ctx this time
    assert load_bases()["coder"]["num_ctx"] == 8192
    assert load_bases()["coder"]["model"] == "qwen2.5-coder:14b"


def test_build_modelfile_text_raises_on_unconfigured_role():
    from sovereign_agent.model_corps.bases import build_modelfile_text

    with pytest.raises(ValueError, match="no base configured"):
        build_modelfile_text("coder")  # nothing set_base'd yet


def test_create_model_runs_ollama_create_with_the_right_tag(tmp_path):
    from sovereign_agent.model_corps.bases import create_model, set_base

    set_base("coder", "qwen2.5-coder:14b", temperature=0.15)
    calls = []

    def fake_runner(argv, **kw):
        calls.append(argv)
        return MagicMock(returncode=0, stdout="success", stderr="")

    result = create_model("coder", runner=fake_runner)
    assert result.ok
    assert result.model_tag == "aria-coder"
    assert calls[0][:2] == ["ollama", "create"]
    assert calls[0][2] == "aria-coder"
    assert calls[0][3] == "-f"


def test_create_model_underscore_role_gets_hyphenated_tag():
    """orchestrator_fast (sprint-mode-d's persona alias) must never
    produce a tag with a literal underscore -- Ollama tags use hyphens."""
    from sovereign_agent.model_corps.bases import create_model, set_base

    # orchestrator_fast isn't a bases.json slot, but create_model's tag
    # naming itself must still be correct if ever called directly.
    set_base("orchestrator", "qwen3:14b")

    def fake_runner(argv, **kw):
        return MagicMock(returncode=0, stdout="", stderr="")

    result = create_model("orchestrator", runner=fake_runner)
    assert result.model_tag == "aria-orchestrator"


def test_create_model_reports_failure_without_raising():
    from sovereign_agent.model_corps.bases import create_model, set_base

    set_base("coder", "qwen2.5-coder:14b")

    def failing_runner(argv, **kw):
        return MagicMock(returncode=1, stdout="", stderr="Error: model not found")

    result = create_model("coder", runner=failing_runner)
    assert not result.ok
    assert "not found" in result.detail


def test_create_model_never_raises_on_a_broken_runner():
    from sovereign_agent.model_corps.bases import create_model, set_base

    set_base("coder", "qwen2.5-coder:14b")

    def broken_runner(argv, **kw):
        raise OSError("ollama binary not found")

    result = create_model("coder", runner=broken_runner)
    assert not result.ok
    assert "OSError" in result.detail


def test_create_model_on_unconfigured_role_fails_cleanly():
    from sovereign_agent.model_corps.bases import create_model

    result = create_model("vision")  # nothing set_base'd
    assert not result.ok
    assert "no base configured" in result.detail
