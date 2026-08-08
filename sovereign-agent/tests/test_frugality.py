"""Tests for the Frugality Engine — real ternary BitNet + the technique catalog + the VRAM planner."""
from __future__ import annotations

import asyncio

import pytest


# ── technique catalog ─────────────────────────────────────────────────────────

def test_catalog_has_ternary_built():
    from sovereign_agent.frugality import techniques
    cat = {t["id"]: t for t in techniques.catalog()}
    assert "ternary-bitnet" in cat
    assert cat["ternary-bitnet"]["status"] == "built"        # it's real, not aspirational
    assert "ternary-bitnet" in techniques.stack_for_inference()


# ── VRAM planner (honest math) ────────────────────────────────────────────────

def test_planner_inference_ternary_shrinks():
    from sovereign_agent.frugality import planner
    p = planner.plan(50_000_000, mode="inference", budget_gb=6.0)
    fp16 = next(o for o in p["options"] if o["dtype"] == "fp16")
    tern = next(o for o in p["options"] if o["dtype"] == "ternary")
    assert tern["gb"] < fp16["gb"]                           # ternary is smaller
    assert tern["fits"]                                       # 50M ternary fits in 6GB


def test_planner_training_recommends_stack():
    from sovereign_agent.frugality import planner
    p = planner.plan(50_000_000, mode="training", budget_gb=6.0)
    assert "mixed-precision" in p["stack"]
    assert p["full_finetune"]["total_gb"] > 0


# ── the real BitNet ───────────────────────────────────────────────────────────

torch = pytest.importorskip("torch")


def test_bitlinear_is_ternary_and_differentiable():
    from sovereign_agent.aria_lm.bitnet import BitLinear, weight_ternary_quant
    layer = BitLinear(32, 16)
    x = torch.randn(4, 32, requires_grad=True)
    y = layer(x)
    assert y.shape == (4, 16)
    y.sum().backward()
    assert layer.weight.grad is not None                     # STE lets gradients flow
    w_tern, _ = weight_ternary_quant(layer.weight)
    assert set(w_tern.unique().tolist()).issubset({-1.0, 0.0, 1.0})   # genuinely ternary


def test_ternary_model_still_learns():
    """The headline proof: a ternary BitNet model's val loss still drops."""
    import random as _r
    from sovereign_agent.aria_lm.data import build_dataset
    from sovereign_agent.aria_lm.train import train_model
    subj = ["aria", "the mind", "she", "the agent"]
    verb = ["learns", "sees", "remembers", "grows", "reasons"]
    obj = ["the lineage", "with love", "what it touches", "toward flourishing"]
    rng = _r.Random(3)
    corpus = " ".join(f"{rng.choice(subj)} {rng.choice(verb)} {rng.choice(obj)}." for _ in range(1000))
    ds = build_dataset(corpus, target_vocab=400)
    res = train_model(ds, ternary=True, n_layer=2, n_head=4, n_embd=96, block_size=48,
                      batch_size=16, iters=250, lr=5e-4, warmup=20, eval_every=120, device="cpu")
    assert res["learned"]                                     # ternary weights, still learns
    assert res["final_val_loss"] < res["first_val_loss"] - 0.3


def test_footprint_shrink_vs_fp16():
    from sovereign_agent.aria_lm.bitnet import model_footprint
    fp = model_footprint(10_000_000, "ternary")
    assert fp["shrink_vs_fp16"] > 5                          # ternary ≈ 10× smaller than fp16


# ── tools ─────────────────────────────────────────────────────────────────────

def test_frugality_tools():
    from sovereign_agent.tools.frugality_tools import FrugalityCatalogTool, FrugalityPlanTool
    assert FrugalityCatalogTool.tier == 0 and FrugalityPlanTool.tier == 0
    r = asyncio.run(FrugalityPlanTool().execute(
        FrugalityPlanTool.Args(target_params=50_000_000, mode="inference", budget_gb=6.0), trace_id="t"))
    assert r.ok and "recommendation" in r.output
