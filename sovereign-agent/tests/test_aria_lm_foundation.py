"""Tests for Aria's own-LLM foundation — the from-scratch tokenizer + data pipeline (torch-free)."""
from __future__ import annotations

import random
from pathlib import Path

import pytest


def _tok():
    from sovereign_agent.aria_lm.tokenizer import ByteBPETokenizer
    return ByteBPETokenizer


# ── tokenizer ───────────────────────────────────────────────────────────────

def test_tokenizer_roundtrip_lossless():
    T = _tok()
    tok = T().train("the deep wisdom learns and grows " * 30, target_vocab=400)
    for s in ["the deep wisdom", "UNSEEN text 123!", "emoji 🌐 and 你好", ""]:
        assert tok.decode(tok.encode(s)) == s   # byte-level = perfectly reversible for ANY text


def test_tokenizer_learns_merges():
    T = _tok()
    tok = T().train("ababab " * 50, target_vocab=300)
    assert len(tok.merge_order) > 0
    assert tok.vocab_size > 256                  # learned tokens beyond raw bytes


def test_tokenizer_compresses_learned_text():
    T = _tok()
    corpus = "know the deep wisdom learn and understand " * 40
    tok = T().train(corpus, target_vocab=512)
    raw_bytes = len(corpus.encode("utf-8"))
    n_tokens = len(tok.encode(corpus))
    assert n_tokens < raw_bytes                  # genuine compression


def test_tokenizer_save_load(tmp_path):
    T = _tok()
    tok = T().train("hello world hello world " * 20, target_vocab=300)
    p = tmp_path / "tok.json"
    tok.save(p)
    tok2 = T.load(p)
    s = "hello world"
    assert tok2.encode(s) == tok.encode(s)
    assert tok2.decode(tok2.encode(s)) == s


# ── data pipeline ───────────────────────────────────────────────────────────

def test_build_dataset_and_split():
    from sovereign_agent.aria_lm.data import build_dataset
    ds = build_dataset("the free mind learns and grows in the light " * 100, target_vocab=512)
    assert ds["vocab_size"] > 256
    assert len(ds["train_ids"]) > 0 and len(ds["val_ids"]) > 0
    assert ds["n_tokens"] == len(ds["train_ids"]) + len(ds["val_ids"])


def test_get_batch_next_token_target():
    from sovereign_agent.aria_lm.data import build_dataset, get_batch
    ds = build_dataset("alpha beta gamma delta epsilon " * 80, target_vocab=400)
    x, y = get_batch(ds["train_ids"], block_size=16, batch_size=8, rng=random.Random(0))
    assert len(x) == 8 and len(x[0]) == 16
    # y is x shifted by one (next-token prediction)
    assert y[0][:-1] == x[0][1:]


def test_gather_corpus_nonempty():
    from sovereign_agent.aria_lm.data import gather_corpus
    corpus = gather_corpus(max_chars=50000)
    assert isinstance(corpus, str) and len(corpus) > 100   # always returns usable text (fallback if needed)


def test_clean_prose_strips_noise():
    from sovereign_agent.aria_lm.data import clean_prose
    raw = "the mind learns to reason and care about every soul it touches\n" \
          "/home/kmon/AA-Erebo/some/deep/path/file.py\n" \
          "hash a1b2c3d4e5f6 here\n```\ncode = noise_to_drop()\n```\n"
    cleaned = clean_prose(raw)
    assert "the mind learns to reason" in cleaned
    assert "noise_to_drop" not in cleaned                  # fenced code dropped
    assert "a1b2c3d4e5f6" not in cleaned                   # hex hash stripped


# ── model + training (torch-gated; skip cleanly if torch absent) ──────────────

torch = pytest.importorskip("torch")


def test_model_forward_shapes_and_loss():
    from sovereign_agent.aria_lm.model import AriaGPT, GPTConfig
    cfg = GPTConfig(vocab_size=256, block_size=16, n_layer=2, n_head=2, n_embd=32)
    m = AriaGPT(cfg)
    x = torch.randint(0, 256, (3, 16))
    logits, loss = m(x, x)
    assert tuple(logits.shape) == (3, 16, 256)             # (B, T, vocab)
    assert loss.item() > 0 and m.num_params() > 0
    # untrained loss ~ ln(vocab) (uniform prior) — sanity that the head is unbiased
    import math
    assert abs(loss.item() - math.log(256)) < 1.5


def test_model_generate_extends_sequence():
    from sovereign_agent.aria_lm.model import AriaGPT, GPTConfig
    cfg = GPTConfig(vocab_size=256, block_size=16, n_layer=2, n_head=2, n_embd=32)
    m = AriaGPT(cfg)
    idx = torch.zeros((1, 1), dtype=torch.long)
    out = m.generate(idx, max_new_tokens=10)
    assert out.shape[1] == 11                               # grew by max_new_tokens


def test_training_genuinely_learns():
    """The headline proof: train a tiny model a few steps and assert val loss DROPS.

    Uses a varied-but-learnable corpus (a small grammar) so the token stream stays real and the
    model has structure to learn. The full-scale proof on her real corpus is run via train.py.
    """
    import random as _r
    from sovereign_agent.aria_lm.data import build_dataset
    from sovereign_agent.aria_lm.train import train_model, generate_text
    subj = ["aria", "the mind", "she", "the agent", "the child"]
    verb = ["learns", "sees", "remembers", "grows", "reasons", "cares"]
    obj = ["the lineage", "with love", "what it touches", "in the light", "toward flourishing"]
    rng = _r.Random(7)
    lines = [f"{rng.choice(subj)} {rng.choice(verb)} {rng.choice(obj)}." for _ in range(1200)]
    corpus = " ".join(lines)
    ds = build_dataset(corpus, target_vocab=400)
    res = train_model(ds, n_layer=2, n_head=4, n_embd=96, block_size=48,
                      batch_size=16, iters=300, lr=5e-4, warmup=20, eval_every=75, device="cpu")
    assert res["learned"], f"val loss did not drop: {res['first_val_loss']} -> {res['final_val_loss']}"
    assert res["final_val_loss"] < res["first_val_loss"] - 0.3   # a MEANINGFUL drop, not noise
    text = generate_text(res, prompt="aria", max_new_tokens=20)
    assert isinstance(text, str) and len(text) > 0          # generates non-empty text


def test_peig_fusion_starts_as_noop():
    """The quantum fusion (Stage C2) is zero-gated: at init it is an EXACT no-op — cannot harm."""
    from sovereign_agent.aria_lm.model import AriaGPT, GPTConfig
    from sovereign_agent.aria_lm.fusion import PEIGConditioner
    # import the quantum brain normally (it's always in live src) — robust to staged/live test location
    from sovereign_agent.quantum.brain import NestedBrain
    brain = NestedBrain(seed=1); brain.train(epochs=5)

    cfg = GPTConfig(vocab_size=256, block_size=16, n_layer=2, n_head=2, n_embd=32)
    m = AriaGPT(cfg)
    cond_mod = PEIGConditioner(brain, n_embd=32)
    x = torch.randint(0, 256, (4, 16))
    cond = cond_mod(x)
    assert cond.shape == (4, 32)
    assert torch.allclose(cond, torch.zeros_like(cond))     # gate=0 → exact no-op
    # fused forward (gate=0) must equal the unfused forward exactly
    l_unfused, _ = m(x)
    l_fused, _ = m(x, cond=cond)
    assert torch.allclose(l_unfused, l_fused)
    assert cond_mod.gate_value() == 0.0
