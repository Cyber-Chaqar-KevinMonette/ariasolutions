"""Tests for model_ladder — prove-then-promote, colibrì-style."""
from __future__ import annotations

import pytest

from sovereign_agent.model_ladder import (
    MIN_TOK_S,
    ProofRecord,
    add_rung,
    dress_slot_no_offload,
    find_max_no_offload_ctx,
    hw_fingerprint,
    latest_proof,
    load_ladder,
    probe_hardware,
    prove_model,
    prove_prefill,
    record_proof,
    resolve_slot,
)
from sovereign_agent.model_ladder import _gpu_fraction


def _hw():
    return {"gpu": "GTX 1070", "vram_total_mb": 8192, "vram_free_mb": 7000,
            "ram_total_mb": 15000, "ram_available_mb": 9000}


def _gpu_ok_poster(url, payload):
    return {"response": "ok", "load_duration": 1e9}


def _gpu_ok_getter(model_name: str):
    """A test /api/ps stand-in reporting `model_name` as 100% GPU-resident."""
    def getter(url):
        return {"models": [{"name": model_name, "size": 100, "size_vram": 100}]}
    return getter


def _gpu_frac_getter(model_name: str, frac: float):
    def getter(url):
        return {"models": [{"name": model_name, "size": 100,
                            "size_vram": 100 * frac}]}
    return getter


def test_probe_hardware_with_fake_runner():
    def runner(cmd):
        assert cmd[0] == "nvidia-smi"
        return "NVIDIA GeForce GTX 1070, 8192, 6997\n"
    hw = probe_hardware(runner)
    assert hw["vram_total_mb"] == 8192 and hw["vram_free_mb"] == 6997
    assert "1070" in hw["gpu"]
    assert hw["ram_total_mb"] > 0          # real /proc/meminfo


def test_probe_no_gpu_never_raises():
    def runner(cmd):
        raise FileNotFoundError("nvidia-smi")
    hw = probe_hardware(runner)
    assert hw["vram_total_mb"] == 0 and hw["gpu"] == ""


def test_ladder_base_rung_always_present_and_add(tmp_path):
    ladder = load_ladder(tmp_path)
    assert ladder["orchestrator"], "rung 0 comes from SETTINGS"
    base = ladder["orchestrator"][0]
    msg = add_rung(tmp_path, "orchestrator", "qwen3:14b")
    assert "unproven" in msg
    ladder = load_ladder(tmp_path)
    assert ladder["orchestrator"][0] == base       # base still rung 0
    assert "qwen3:14b" in ladder["orchestrator"]
    assert "already" in add_rung(tmp_path, "orchestrator", "qwen3:14b")
    assert "unknown slot" in add_rung(tmp_path, "nope", "x")


def test_prove_pass_and_fail_thresholds(tmp_path):
    def fast_poster(url, payload):
        return {"response": "Reliability.", "load_duration": 4e9,
                "eval_count": 48, "eval_duration": 4e9}   # 12 tok/s
    p = prove_model("big:14b", hw=_hw(), poster=fast_poster,
                    getter=_gpu_ok_getter("big:14b"))
    assert p.ok and p.tok_s > MIN_TOK_S and p.fingerprint == hw_fingerprint(_hw())

    def slow_poster(url, payload):
        return {"response": "ok", "load_duration": 4e9,
                "eval_count": 48, "eval_duration": 24e9}  # 2 tok/s
    p2 = prove_model("huge:70b", hw=_hw(), poster=slow_poster,
                     getter=_gpu_ok_getter("huge:70b"))
    assert not p2.ok and "too slow" in p2.note

    def broken_poster(url, payload):
        raise OSError("connection refused")
    p3 = prove_model("x", hw=_hw(), poster=broken_poster,
                     getter=_gpu_ok_getter("x"))
    assert not p3.ok and "trial failed" in p3.note


def test_prove_model_rejects_any_offload_regardless_of_speed(tmp_path):
    """no-offloading-d: a model spilling to CPU fails outright even with
    a great tok/s number -- speed is never allowed to excuse offload."""
    def blazing_poster(url, payload):
        return {"response": "Reliability.", "load_duration": 1e9,
                "eval_count": 48, "eval_duration": 1e9}   # 48 tok/s, great
    p = prove_model("big:14b", hw=_hw(), poster=blazing_poster,
                    getter=_gpu_frac_getter("big:14b", 0.61))   # 61% GPU
    assert not p.ok
    assert "offloads to CPU" in p.note
    assert "61%" in p.note
    assert p.tok_s == 0.0     # never even measured -- rejected before that step


def test_prove_model_measures_speed_with_keep_alive_zero_after_gpu_check(tmp_path):
    """The GPU-residency pre-check must use its own short keep_alive, but
    the real speed measurement must still unload immediately after
    (keep_alive=0) -- a trial can never zombify VRAM."""
    calls = []

    def tracking_poster(url, payload):
        calls.append(payload["keep_alive"])
        return {"response": "ok", "load_duration": 1e9,
                "eval_count": 48, "eval_duration": 4e9}
    p = prove_model("big:14b", hw=_hw(), poster=tracking_poster,
                    getter=_gpu_ok_getter("big:14b"))
    assert p.ok
    assert calls[-1] == 0                # the real measurement's request
    assert calls[0] != 0                 # the GPU pre-check's own request


def test_gpu_fraction_matches_by_name_or_model_field():
    assert _gpu_fraction("m", {"models": [{"name": "m", "size": 100, "size_vram": 50}]}) == 0.5
    assert _gpu_fraction("m", {"models": [{"model": "m", "size": 100, "size_vram": 100}]}) == 1.0
    assert _gpu_fraction("missing", {"models": [{"name": "m", "size": 100, "size_vram": 100}]}) is None
    assert _gpu_fraction("m", {}) is None
    assert _gpu_fraction("m", {"models": []}) is None


def test_prove_prefill_measures_real_prompt_eval_speed():
    def poster(url, payload):
        assert payload["keep_alive"] == 0                 # never zombify VRAM
        assert len(payload["prompt"]) > 5000               # a real long prompt
        return {"response": "ok.", "load_duration": 2e9,
                "prompt_eval_count": 1800, "prompt_eval_duration": 9e9,   # 200 tok/s
                "eval_count": 16, "eval_duration": 4e9}                  # 4 tok/s
    p = prove_prefill("qwen3:14b", poster=poster)
    assert p.ok
    assert p.prompt_tokens == 1800
    assert p.prefill_tok_s == pytest.approx(200.0, rel=0.01)
    assert p.decode_tok_s == pytest.approx(4.0, rel=0.01)


def test_prove_prefill_reports_cached_prompt_honestly_not_a_fake_speed():
    def poster(url, payload):
        # Ollama's real behavior: 0 duration when the prompt hit its cache
        return {"response": "ok.", "load_duration": 1e9,
                "prompt_eval_count": 1800, "prompt_eval_duration": 0,
                "eval_count": 16, "eval_duration": 4e9}
    p = prove_prefill("qwen3:14b", poster=poster)
    assert not p.ok
    assert "cache" in p.note
    assert p.prefill_tok_s == 0.0     # never a fabricated number from a 0 duration


def test_prove_prefill_never_raises_on_a_broken_connection():
    def broken_poster(url, payload):
        raise OSError("connection refused")
    p = prove_prefill("qwen3:14b", poster=broken_poster)
    assert not p.ok and "trial failed" in p.note


def test_find_max_no_offload_ctx_returns_the_largest_size_that_fits():
    # fits at 4096 and everything smaller, offloads at 6144 and above
    fits = {4096, 3072, 2048, 1536, 1024, 512}
    calls = []
    def poster(url, payload):
        ctx = payload["options"]["num_ctx"]
        calls.append(ctx)
        return {"response": "ok"}

    def dynamic_getter(url):
        # the LAST ctx posted decides the reported fraction
        ctx = calls[-1]
        frac = 1.0 if ctx in fits else 0.5
        return {"models": [{"name": "big:14b", "size": 100, "size_vram": 100 * frac}]}

    result = find_max_no_offload_ctx("big:14b", poster=poster, getter=dynamic_getter)
    assert result == 4096
    assert calls == [16384, 12288, 8192, 6144, 4096]   # stopped at the first fit


def test_find_max_no_offload_ctx_returns_none_when_nothing_fits():
    result = find_max_no_offload_ctx(
        "huge:70b", poster=_gpu_ok_poster,
        getter=_gpu_frac_getter("huge:70b", 0.4))
    assert result is None


def test_dress_slot_no_offload_refuses_without_touching_model_corps(tmp_path, monkeypatch):
    from sovereign_agent import model_ladder
    from unittest.mock import MagicMock

    fake_set_base = MagicMock()
    fake_create_model = MagicMock()
    import sovereign_agent.model_corps as model_corps_module
    monkeypatch.setattr(model_corps_module, "set_base", fake_set_base)
    monkeypatch.setattr(model_corps_module, "create_model", fake_create_model)

    msg = model_ladder.dress_slot_no_offload(
        tmp_path, "orchestrator", "huge:70b",
        poster=_gpu_ok_poster, getter=_gpu_frac_getter("huge:70b", 0.3))
    assert "refused" in msg
    assert "huge:70b" in msg
    fake_set_base.assert_not_called()
    fake_create_model.assert_not_called()


def test_dress_slot_no_offload_sets_num_ctx_and_rebuilds_when_it_fits(tmp_path, monkeypatch):
    from sovereign_agent import model_ladder
    from unittest.mock import MagicMock

    set_base_calls = []
    def fake_set_base(role, model, **kw):
        set_base_calls.append((role, model, kw))

    def fake_create_model(role, **kw):
        return MagicMock(ok=True, model_tag=f"aria-{role}", detail="created")

    import sovereign_agent.model_corps as model_corps_module
    monkeypatch.setattr(model_corps_module, "set_base", fake_set_base)
    monkeypatch.setattr(model_corps_module, "create_model", fake_create_model)

    msg = model_ladder.dress_slot_no_offload(
        tmp_path, "orchestrator", "qwen3:8b",
        poster=_gpu_ok_poster, getter=_gpu_ok_getter("qwen3:8b"))
    assert "100% GPU" in msg
    assert "qwen3:8b" in msg
    assert set_base_calls == [("orchestrator", "qwen3:8b", {"num_ctx": 16384})]


def test_resolution_prefers_proven_biggest_and_pins_hardware(tmp_path):
    fp = hw_fingerprint(_hw())
    base = load_ladder(tmp_path)["fast"][0]
    add_rung(tmp_path, "fast", "mid:7b")
    add_rung(tmp_path, "fast", "big:14b")
    # nothing proven → base
    model, reason = resolve_slot(tmp_path, "fast", fingerprint=fp)
    assert model == base and "base model" in reason
    # mid proven → mid wins
    record_proof(tmp_path, ProofRecord("mid:7b", 1.0, fp, True, 5.0, 9.0))
    model, _ = resolve_slot(tmp_path, "fast", fingerprint=fp)
    assert model == "mid:7b"
    # big proven → big wins (highest proven rung)
    record_proof(tmp_path, ProofRecord("big:14b", 2.0, fp, True, 9.0, 6.5))
    model, reason = resolve_slot(tmp_path, "fast", fingerprint=fp)
    assert model == "big:14b" and "proven" in reason
    # a FAILED newer proof retracts the vouch
    record_proof(tmp_path, ProofRecord("big:14b", 3.0, fp, False, note="too slow"))
    model, _ = resolve_slot(tmp_path, "fast", fingerprint=fp)
    assert model == "mid:7b"
    # different hardware → those proofs never vouch
    model, _ = resolve_slot(tmp_path, "fast", fingerprint="other|0MB|0MB")
    assert model == base


def test_latest_proof_survives_corrupt_lines(tmp_path):
    fp = hw_fingerprint(_hw())
    record_proof(tmp_path, ProofRecord("m", 1.0, fp, True, 1.0, 8.0))
    from sovereign_agent.model_ladder import proofs_path
    with proofs_path(tmp_path).open("a") as f:
        f.write("{broken json\n")
    p = latest_proof(tmp_path, "m", fp)
    assert p is not None and p.ok
    assert latest_proof(tmp_path, "missing", fp) is None


# ── model-corps-unify-d (Kevin, 2026-07-21) ─────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_model_corps_bases(tmp_path, monkeypatch):
    """These tests must never read the REAL, live bases.json -- it
    already records the actual promoted qwen3:14b/qwen2.5-coder:14b
    bases from this same session, which would make "before promotion"
    assertions below false-pass against real, unrelated state."""
    from sovereign_agent.model_corps import bases as bases_module

    monkeypatch.setattr(bases_module, "_bases_path", lambda: tmp_path / "isolated_bases.json")
    yield


def test_promote_slot_refuses_when_only_base_resolves(tmp_path, monkeypatch):
    """Unchanged behavior: nothing proven above rung 0 -> refuse, and
    never even touch model_corps."""
    from sovereign_agent import model_ladder
    from unittest.mock import MagicMock

    fake_set_base = MagicMock()
    monkeypatch.setattr(model_ladder, "SLOTS", model_ladder.SLOTS)  # sanity no-op

    msg = model_ladder.promote_slot(tmp_path, "orchestrator")
    assert "stays on its base model" in msg


def test_promote_slot_dresses_and_rebuilds_not_just_vault_write(tmp_path, monkeypatch):
    """THE actual bug this closes: promote_slot() used to write the raw
    proven model straight into the vault, bypassing the persona. Now it
    must call model_corps.set_base + create_model instead."""
    from sovereign_agent import model_ladder
    from sovereign_agent.model_ladder import ProofRecord, add_rung, hw_fingerprint, probe_hardware, record_proof
    from unittest.mock import MagicMock

    fp = hw_fingerprint(probe_hardware())
    add_rung(tmp_path, "coder", "qwen2.5-coder:14b")
    record_proof(tmp_path, ProofRecord("qwen2.5-coder:14b", 1.0, fp, True, 5.0, 9.0))

    set_base_calls = []
    create_model_calls = []

    def fake_set_base(role, model, **kw):
        set_base_calls.append((role, model))

    def fake_create_model(role, **kw):
        create_model_calls.append(role)
        return MagicMock(ok=True, model_tag=f"aria-{role}", detail="created")

    import sovereign_agent.model_corps as model_corps_module
    monkeypatch.setattr(model_corps_module, "set_base", fake_set_base)
    monkeypatch.setattr(model_corps_module, "create_model", fake_create_model)

    msg = model_ladder.promote_slot(
        tmp_path, "coder", poster=_gpu_ok_poster,
        getter=_gpu_ok_getter("qwen2.5-coder:14b"))
    assert "qwen2.5-coder:14b" in msg
    assert "dressed with her persona" in msg
    assert set_base_calls == [("coder", "qwen2.5-coder:14b")]
    assert create_model_calls == ["coder"]


def test_promote_slot_reports_dress_failure_without_raising(tmp_path, monkeypatch):
    from sovereign_agent import model_ladder
    from sovereign_agent.model_ladder import ProofRecord, add_rung, hw_fingerprint, probe_hardware, record_proof
    from unittest.mock import MagicMock

    fp = hw_fingerprint(probe_hardware())
    add_rung(tmp_path, "coder", "qwen2.5-coder:14b")
    record_proof(tmp_path, ProofRecord("qwen2.5-coder:14b", 1.0, fp, True, 5.0, 9.0))

    import sovereign_agent.model_corps as model_corps_module
    monkeypatch.setattr(model_corps_module, "set_base", MagicMock())
    monkeypatch.setattr(model_corps_module, "create_model",
                        lambda role, **kw: MagicMock(ok=False, detail="ollama create failed"))

    msg = model_ladder.promote_slot(
        tmp_path, "coder", poster=_gpu_ok_poster,
        getter=_gpu_ok_getter("qwen2.5-coder:14b"))
    assert "couldn't rebuild aria-coder" in msg
    assert "ollama create failed" in msg


def test_resolve_slot_shows_already_dressed_candidate_as_folded_into_base(tmp_path, monkeypatch):
    """The exact display bug this closes: after a real promote, the
    ladder used to still show the raw candidate as a separate "resolved"
    winner, as if promoting hadn't happened. Once model_corps.bases
    records the candidate as the slot's current base, resolve_slot must
    report rung 0 (aria-<slot>:latest) as resolved, annotated with what
    it's dressed on."""
    from sovereign_agent import model_ladder
    from sovereign_agent.model_ladder import (
        ProofRecord, add_rung, hw_fingerprint, load_ladder, probe_hardware,
        record_proof, resolve_slot,
    )

    fp = hw_fingerprint(probe_hardware())
    base = load_ladder(tmp_path)["orchestrator"][0]
    add_rung(tmp_path, "orchestrator", "qwen3:14b")
    record_proof(tmp_path, ProofRecord("qwen3:14b", 1.0, fp, True, 4.0, 12.0))

    # before "promotion" (model_corps.bases not yet updated): candidate wins
    model, reason = resolve_slot(tmp_path, "orchestrator", fingerprint=fp)
    assert model == "qwen3:14b" and "proven" in reason

    # after promotion: model_corps.bases now records qwen3:14b as the
    # orchestrator's actual current base
    monkeypatch.setattr(model_ladder, "_already_dressed_on",
                        lambda slot, m: slot == "orchestrator" and m == "qwen3:14b")
    model, reason = resolve_slot(tmp_path, "orchestrator", fingerprint=fp)
    assert model == base  # rung 0 (aria-orchestrator:latest), not the raw candidate
    assert "already dressed on qwen3:14b" in reason
