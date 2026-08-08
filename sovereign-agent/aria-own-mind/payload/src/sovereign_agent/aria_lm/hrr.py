"""aria_lm/hrr.py — Holographic Reduced Representations (Plate, 1995), from scratch.

Genuinely "holographic" compositional memory — and a real hardware-liberation lever: it stores
key→value associations in a SINGLE fixed-width vector with **zero extra parameters**, via circular
convolution. Bind a key with a value, superpose many such bindings into one vector, then unbind by a key
to approximately retrieve its value. The whole memory is one D-dim vector regardless of how many pairs.

Operations (all on unit-ish D-dim real vectors):
  bind(a, b)    = circular convolution  = IFFT(FFT(a) · FFT(b))         — distributes info holographically
  unbind(c, b)  = circular correlation  = bind(c, involution(b))         — approximate inverse
  superpose(*v) = normalized sum                                          — overlay many memories
  cleanup(x, M) = nearest codebook vector by cosine                       — denoise a noisy retrieval

This is the holographic substrate for `holo_bitnet.py`. Pure torch, deterministic, testable.
100% ours (the algorithm is Plate's; the implementation is from scratch).
"""
from __future__ import annotations

import torch


def random_vectors(n: int, dim: int, *, seed: int = 0, device: str = "cpu") -> torch.Tensor:
    """n random HRR vectors (Gaussian, unit-normalized) — the atoms of holographic memory."""
    g = torch.Generator(device=device).manual_seed(seed)
    v = torch.randn(n, dim, generator=g, device=device)
    return v / v.norm(dim=-1, keepdim=True).clamp_min(1e-8)


def bind(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    """Circular convolution via FFT (holographic binding). Works on (..., D)."""
    return torch.fft.irfft(torch.fft.rfft(a) * torch.fft.rfft(b), n=a.shape[-1])


def involution(b: torch.Tensor) -> torch.Tensor:
    """Approximate inverse for unbinding: b'[0]=b[0], b'[i]=b[D-i]. (circular reversal)"""
    return torch.cat([b[..., :1], b[..., 1:].flip(-1)], dim=-1)


def unbind(c: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    """Circular correlation = bind(c, involution(b)) — retrieve the value bound under key b."""
    return bind(c, involution(b))


def superpose(*vectors: torch.Tensor) -> torch.Tensor:
    """Overlay memories (normalized sum)."""
    s = torch.stack(vectors, dim=0).sum(dim=0)
    return s / s.norm(dim=-1, keepdim=True).clamp_min(1e-8)


def cleanup(x: torch.Tensor, codebook: torch.Tensor) -> tuple[int, float]:
    """Nearest codebook vector by cosine. Returns (index, similarity) — denoises a noisy retrieval."""
    xn = x / x.norm(dim=-1, keepdim=True).clamp_min(1e-8)
    cb = codebook / codebook.norm(dim=-1, keepdim=True).clamp_min(1e-8)
    sims = cb @ xn.reshape(-1)
    idx = int(sims.argmax().item())
    return idx, float(sims[idx].item())


class HolographicMemory:
    """A parameter-free associative memory: many key→value pairs in ONE D-dim vector. Hardware liberation
    for memory — capacity grows with D, not with a parameter matrix per pair."""

    def __init__(self, dim: int, *, device: str = "cpu") -> None:
        self.dim = dim
        self.device = device
        self.trace = torch.zeros(dim, device=device)

    def store(self, key: torch.Tensor, value: torch.Tensor) -> None:
        self.trace = self.trace + bind(key, value)

    def retrieve(self, key: torch.Tensor) -> torch.Tensor:
        return unbind(self.trace, key)

    def normalized(self) -> torch.Tensor:
        return self.trace / self.trace.norm().clamp_min(1e-8)
