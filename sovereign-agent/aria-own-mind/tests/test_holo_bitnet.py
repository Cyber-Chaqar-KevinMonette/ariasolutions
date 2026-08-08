"""Tests for the Holographic BitNet — HRR holographic memory + cross-agent latent transfer."""
from __future__ import annotations

import math

import pytest

torch = pytest.importorskip("torch")


# ── HRR holographic memory ────────────────────────────────────────────────────

def test_hrr_bind_unbind_round_trips():
    from sovereign_agent.aria_lm import hrr
    D = 1024
    a = hrr.random_vectors(1, D, seed=1)[0]
    b = hrr.random_vectors(1, D, seed=2)[0]
    rec = hrr.unbind(hrr.bind(a, b), b)
    cos = torch.nn.functional.cosine_similarity(a.unsqueeze(0), rec.unsqueeze(0)).item()
    assert cos > 0.5                          # bind→unbind recovers the value well above chance


def test_holographic_memory_stores_many_in_one_vector():
    """The headline holographic property: many key→value pairs in ONE vector, all retrievable."""
    from sovereign_agent.aria_lm import hrr
    D = 2048
    vals = hrr.random_vectors(6, D, seed=3)
    keys = hrr.random_vectors(6, D, seed=4)
    mem = hrr.HolographicMemory(D)
    for i in range(5):
        mem.store(keys[i], vals[i])
    correct = 0
    for i in range(5):
        idx, _ = hrr.cleanup(mem.retrieve(keys[i]), vals)
        correct += (idx == i)
    assert correct >= 4                        # nearly all retrieved from a single vector (param-free)


# ── cross-agent latent transfer ───────────────────────────────────────────────

def test_latent_transfer_carries_thought_across_dims():
    from sovereign_agent.aria_lm import holo_bitnet as H
    torch.manual_seed(0)
    thought = torch.randn(256)
    fid = H.transfer_fidelity(thought, target_dim=128)
    rand = torch.randn(256)
    base = torch.nn.functional.cosine_similarity(thought.reshape(1, -1), rand.reshape(1, -1)).item()
    assert fid > 0.4                           # the thought survives the cross-agent hand-off
    assert fid > base + 0.3                     # and is far above an unrelated baseline


def test_latent_packet_serializes():
    from sovereign_agent.aria_lm import holo_bitnet as H
    pkt = H.export_latent(torch.randn(64), label="thought-1")
    d = pkt.to_dict()
    pkt2 = H.LatentPacket.from_dict(d)
    assert pkt2.source_dim == 64 and pkt2.label == "thought-1"
    assert torch.allclose(pkt.vector, pkt2.vector, atol=1e-5)


def test_holographic_conditioner_fuses_phases():
    from sovereign_agent.aria_lm import holo_bitnet as H
    cond = H.HolographicConditioner(dim=128)
    out = cond.condition(torch.randn(128), [2 * math.pi * i / 12 for i in range(12)])
    assert out.shape == (128,)
    assert abs(out.norm().item() - 1.0) < 1e-3   # normalized holographic conditioning vector


def test_levers_summary_is_honest():
    from sovereign_agent.aria_lm import holo_bitnet as H
    s = H.levers_summary()
    # honesty: the non-classical lever must state it is NOT real quantum hardware
    assert "NOT real quantum" in s["nonclassical_peig"]["honest"]
    assert s["ternary_bitnet"]["status"] == "built+proven"
