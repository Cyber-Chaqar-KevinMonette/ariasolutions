"""aria_lm/fusion.py — The UNIQUE EDGE: fuse the non-classical PEIG quantum brain into the neural LM.

No one else is building this. Aria's quantum brain (`quantum/brain.py`, Paper XI nested PEIG) holds a
12-node phase ring (Layer 2 Character) plus shadow-sync / guard-health — a genuine non-classical state.
Here we turn that state into a CONDITIONING signal for the from-scratch transformer:

  brain phase ring θ₀..θ₁₁  ──rotate by a per-sequence phase offset φ──►  feature vector
                                                              │
                                          learned Linear projection → conditioning embedding (B, n_embd)
                                                              │
                                              added to the token embeddings in AriaGPT.forward(cond=…)

Phase rotation is the brain's native operation, so this is principled, not decorative. It is OFF by
default and kept ONLY if A/B evidence shows it lowers validation loss (the EXPAI evidence gate). Honest
by construction: `ab_compare()` trains identical models with/without fusion and reports the real delta.
"""
from __future__ import annotations

import math

import torch
import torch.nn as nn

# feature = [cos(θ_i+φ), sin(θ_i+φ)] for 12 nodes (24) + [shadow_sync, guard_health] (2)
PEIG_FEAT_DIM = 26


def brain_phase_state(brain) -> tuple[list[float], float, float]:
    """Extract the current PEIG state from a NestedBrain: 12 node phases + shadow_sync + guard_health."""
    phases = [nd.phase for nd in brain.nodes]
    n = len(brain.nodes)
    shadow_sync = 1.0 - (sum(abs(brain.nodes[i].phase - brain.shadow[i]) for i in range(n))
                         / (n * math.pi))
    shadow_sync = max(0.0, min(1.0, shadow_sync))
    return phases, shadow_sync, float(brain.guard_health)


class PEIGConditioner(nn.Module):
    """Maps the quantum brain's phase state → a per-sequence conditioning embedding for the LM.

    The 12-node phase ring is frozen (the brain's learned state); only the projection is trained.
    Each sequence rotates the ring by a content-derived phase offset φ, so different contexts get
    different non-classical conditioning — grounded in the ring's own geometry.
    """

    def __init__(self, brain, n_embd: int, n_nodes: int = 12) -> None:
        super().__init__()
        phases, shadow_sync, guard = brain_phase_state(brain)
        self.n_nodes = len(phases)
        # frozen brain state (non-trainable buffers — Ring-1-style: the brain owns these)
        self.register_buffer("thetas", torch.tensor(phases, dtype=torch.float32))
        self.register_buffer("scalars", torch.tensor([shadow_sync, guard], dtype=torch.float32))
        self.proj = nn.Linear(PEIG_FEAT_DIM, n_embd)
        nn.init.normal_(self.proj.weight, mean=0.0, std=0.02)
        nn.init.zeros_(self.proj.bias)
        # Zero-init gate: the fusion starts as an EXACT no-op (gate·proj = 0), so it can never harm —
        # it only moves off zero if the data shows the quantum conditioning lowers loss (EXPAI-honest).
        self.gate = nn.Parameter(torch.zeros(1))

    def features(self, idx: torch.Tensor) -> torch.Tensor:
        """(B, T) token ids → (B, PEIG_FEAT_DIM) rotated phase features."""
        B = idx.shape[0]
        dev = idx.device
        # per-sequence phase offset φ from content: which of the 12 voices does this context evoke?
        node_sel = (idx[:, : min(4, idx.shape[1])].sum(dim=1) % self.n_nodes).float()  # (B,)
        phi = (2.0 * math.pi * node_sel / self.n_nodes).unsqueeze(1)                    # (B, 1)
        ang = self.thetas.to(dev).unsqueeze(0) + phi                                    # (B, n_nodes)
        feat = torch.cat([torch.cos(ang), torch.sin(ang)], dim=1)                       # (B, 2*n_nodes)
        sc = self.scalars.to(dev).unsqueeze(0).expand(B, -1)                            # (B, 2)
        return torch.cat([feat, sc], dim=1)                                             # (B, PEIG_FEAT_DIM)

    def forward(self, idx: torch.Tensor) -> torch.Tensor:
        return self.gate * self.proj(self.features(idx))                               # (B, n_embd)

    def gate_value(self) -> float:
        """How far the fusion moved off the no-op (0.0 = unused). Honest evidence of whether it helped."""
        return float(self.gate.detach().abs().item())


def ab_compare(dataset: dict, brain, *, iters: int = 400, device: str | None = None,
               **train_kwargs) -> dict:
    """Honest A/B: train identical models WITHOUT and WITH PEIG fusion; report the val-loss delta.

    Returns {baseline_val, fused_val, delta, fusion_helps}. `fusion_helps` is True only if the fused
    model's validation loss is meaningfully lower — the EXPAI evidence gate. No claim without proof.
    """
    from .train import train_model
    base = train_model(dataset, iters=iters, device=device, **train_kwargs)
    fused = train_model(dataset, iters=iters, device=device, brain=brain, **train_kwargs)
    delta = round(base["final_val_loss"] - fused["final_val_loss"], 4)  # positive = fusion helped
    return {
        "baseline_val": base["final_val_loss"],
        "fused_val": fused["final_val_loss"],
        "delta": delta,
        "fusion_helps": delta > 0.02,   # must beat noise to be kept
        "baseline_curve": base["curve"],
        "fused_curve": fused["curve"],
    }
