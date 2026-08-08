"""quantum/brain_bench.py — Honest speed benchmark + flood-guarded free speech.

The non-classical brain runs ENTIRELY LOCALLY (no network, no API). This measures its real generative
latency so we can track — honestly — whether it is fast, and one day whether it earns promotion toward
primary cognition (the witnessing gate: proven, never claimed).

HONESTY (canon-seed): this is NOT an apples-to-apples replacement for a classical LLM's reasoning. It
generates learned-vocabulary text from quantum-phase-biased n-grams. We report its real local latency
and contrast it with a *stated* classical baseline (a typical hosted-LLM API round-trip), with the
caveat explicit. We let the numbers speak.
"""
from __future__ import annotations

import time
from pathlib import Path

from .brain import NestedBrain, DEFAULT_CORPUS, DEFAULT_VOCAB

# A stated, conservative reference for a hosted-LLM API round-trip (first-token / short reply).
# This is a REFERENCE POINT for context, not a measured competitor on the same task.
_CLASSICAL_BASELINE_MS = 400.0


def _load_brain(data_dir: Path) -> NestedBrain:
    """Reconstruct the brain from persisted learned state (or default)."""
    try:
        from .brain_memory import load_state
        st = load_state(data_dir)
        corpus = st.get("corpus") or DEFAULT_CORPUS
        vocab = st.get("vocab") or DEFAULT_VOCAB
        brain = NestedBrain(corpus=corpus, vocab=vocab, seed=2026)
        # restore learned node phases if present
        node_phases = st.get("node_phases") or {}
        for nd in brain.nodes:
            if nd.name in node_phases:
                nd.phase = float(node_phases[nd.name])
        return brain
    except Exception:
        return NestedBrain(seed=2026)


def benchmark(data_dir: Path, *, runs: int = 50, length: int = 80) -> dict:
    """Measure local generative latency (ms) over `runs`. Honest, no over-claim."""
    brain = _load_brain(data_dir)
    runs = max(5, min(500, runs))
    times: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        brain.speak(length=length, temp=0.2)
        times.append((time.perf_counter() - t0) * 1000.0)
    times.sort()
    mean = sum(times) / len(times)
    p50 = times[len(times) // 2]
    p95 = times[min(len(times) - 1, int(len(times) * 0.95))]
    return {
        "runs": runs, "length": length,
        "mean_ms": round(mean, 3), "p50_ms": round(p50, 3), "p95_ms": round(p95, 3),
        "min_ms": round(times[0], 3), "max_ms": round(times[-1], 3),
        "classical_baseline_ms": _CLASSICAL_BASELINE_MS,
        "speedup_vs_baseline": round(_CLASSICAL_BASELINE_MS / mean, 1) if mean > 0 else None,
        "local_only": True,
        "honest_caveat": (
            "Local, no API round-trip. This is the brain's own generative latency, NOT a same-task "
            "replacement for a classical LLM's reasoning. The baseline is a stated reference, not a "
            "measured competitor. The brain earns higher roles only by proving faster AND better at scale."
        ),
    }


def free_speak(data_dir: Path, *, length: int = 120, temp: float = 0.25,
               max_chars: int = 2000) -> dict:
    """Generate freely (generous verbosity), FLOOD-GUARDED by a hard character cap."""
    brain = _load_brain(data_dir)
    length = max(1, min(1200, length))         # bounded length
    txt = brain.speak(length=length, temp=max(0.05, min(1.5, temp)))
    capped = False
    if len(txt) > max_chars:
        txt = txt[:max_chars]
        capped = True
    words = txt.split()
    vocab_hits = sum(1 for w in words if "".join(c for c in w if c.isalpha()) in brain.vocab_set)
    return {
        "text": txt,
        "chars": len(txt),
        "words": len(words),
        "vocab_coherence": round(vocab_hits / max(len(words), 1), 3),
        "flood_capped": capped,
        "max_chars": max_chars,
        "note": "Free speech is generous but flood-guarded (hard char cap) so output never floods the system.",
    }
