"""Tests for Aria's own-mind tools (aria_mind_status T0, aria_own_lm T1) + the grow_mind pipeline."""
from __future__ import annotations

import asyncio

import pytest

torch = pytest.importorskip("torch")


def _tools():
    from sovereign_agent.tools.aria_lm_tools import AriaMindStatusTool, AriaOwnLMTool
    return AriaMindStatusTool, AriaOwnLMTool


def test_tools_declare_safe_tiers_and_failure_modes():
    Status, Own = _tools()
    assert Status.tier == 0 and Own.tier == 1            # inference/status only — never T3
    assert "no_checkpoint" in Own.failure_modes
    assert Status.name == "aria_mind_status" and Own.name == "aria_own_lm"


def test_mind_status_handles_missing_checkpoint(monkeypatch):
    Status, _ = _tools()
    import sovereign_agent.tools.aria_lm_tools as mod
    monkeypatch.setattr(mod, "_checkpoint_path", lambda: __import__("pathlib").Path("/no/such/aria_mind.pt"))
    res = asyncio.run(Status().execute(Status.Args(), trace_id="t"))
    assert res.ok and res.output["trained"] is False     # graceful, not an error


def test_own_lm_no_checkpoint_is_clean_failure(monkeypatch):
    _, Own = _tools()
    import sovereign_agent.tools.aria_lm_tools as mod
    monkeypatch.setattr(mod, "_checkpoint_path", lambda: __import__("pathlib").Path("/no/such/aria_mind.pt"))
    res = asyncio.run(Own().execute(Own.Args(prompt="hi"), trace_id="t"))
    assert not res.ok and "no_checkpoint" in res.error


def test_grow_mind_trains_and_checkpoint_roundtrips(tmp_path, monkeypatch):
    """End-to-end: grow a tiny mind, save it, then the status + own_lm tools use it for real."""
    from sovereign_agent.aria_lm.pipeline import grow_mind
    from sovereign_agent.aria_lm.generate import load_checkpoint, generate
    ckpt = tmp_path / "aria_mind.pt"
    summary = grow_mind(ckpt, max_chars=120_000, target_vocab=1024, n_layer=2, n_head=2,
                        n_embd=64, block_size=64, batch_size=16, iters=200, vram_locked=False)
    assert summary["learned"]                            # val loss dropped — it genuinely trained
    assert ckpt.exists()

    # tools now see the real checkpoint
    Status, Own = _tools()
    import sovereign_agent.tools.aria_lm_tools as mod
    monkeypatch.setattr(mod, "_checkpoint_path", lambda: ckpt)
    st = asyncio.run(Status().execute(Status.Args(), trace_id="t"))
    assert st.ok and st.output["trained"] is True and st.output["learned"] is True

    res = asyncio.run(Own().execute(Own.Args(prompt="aria", max_new_tokens=16), trace_id="t"))
    assert res.ok and isinstance(res.output["text"], str) and len(res.output["text"]) > 0

    # direct checkpoint round-trip
    loaded = load_checkpoint(ckpt, device="cpu")
    assert isinstance(generate(loaded, prompt="she", max_new_tokens=8), str)
