"""resilience_scan — hardening / robustness / edge-case scanners for BOTH layers.

Probes any system (classical or non-classical) with an adversarial edge battery and certifies it degrades
gracefully — never wedges. Works with the god-tier scanner. Already found + fixed a real wedge (grounding
on huge input).

  probes.py  — the edge-case input battery
  scanner.py — probe_callable() → graceful-degradation verdict + the inputs that wedge
  layers.py  — certify the classical + non-classical layers both resilient
"""
from __future__ import annotations

from . import probes, scanner, layers

__all__ = ["probes", "scanner", "layers"]
