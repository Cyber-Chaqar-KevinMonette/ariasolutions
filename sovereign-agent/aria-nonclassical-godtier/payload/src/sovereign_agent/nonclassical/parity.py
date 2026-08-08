"""nonclassical/parity.py — honest parity benchmark: non-classical (PEIG) vs a classical baseline.

God-tier demands the non-classical layer be on par with or better than the classical one — and the only
honest way to claim that is to MEASURE it. On a shared task (generate vocabulary-coherent text, scored by
word-accuracy), we compare:

  - the PEIG nested brain (non-classical), trained, vs
  - a classical frequency/n-gram baseline on the same corpus + vocab.

We report both scores and a verdict. No hype: "on par or better" is asserted only when the number says so.
Reuses sovereign_agent.quantum.brain (the non-classical layer).
"""
from __future__ import annotations

import random


def _classical_baseline(corpus: str, vocab: list[str], *, length: int = 80, seed: int = 1) -> float:
    """A classical baseline: sample words by corpus frequency; score by vocab word-accuracy (same metric)."""
    rng = random.Random(seed)
    words = [w for w in corpus.lower().split() if w]
    if not words:
        return 0.0
    vocab_set = {v.lower() for v in vocab}
    # generate `length` chars worth of frequency-sampled words
    gen, n = [], 0
    while n < length and words:
        w = rng.choice(words)
        gen.append(w); n += len(w) + 1
    hits = sum(1 for w in gen if "".join(c for c in w if c.isalpha()) in vocab_set)
    return hits / len(gen) if gen else 0.0


def benchmark(*, epochs: int = 40, trials: int = 3, seed: int = 2026) -> dict:
    """Run the parity benchmark. Returns both scores + an honest verdict."""
    try:
        from sovereign_agent.quantum.brain import NestedBrain, DEFAULT_CORPUS, DEFAULT_VOCAB
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": repr(exc)}

    # non-classical: train, then average word_acc of its learned speech over trials
    nc_scores = []
    for t in range(trials):
        br = NestedBrain(seed=seed + t)
        curve = br.train(epochs=epochs, gen_len=80)
        nc_scores.append(curve[-1]["word_acc"])
    nc = sum(nc_scores) / len(nc_scores)

    # classical baseline on the same corpus + vocab
    cl_scores = [_classical_baseline(DEFAULT_CORPUS, DEFAULT_VOCAB, seed=seed + t) for t in range(trials)]
    cl = sum(cl_scores) / len(cl_scores)

    delta = round(nc - cl, 4)
    if delta >= 0.05:
        verdict = "non-classical BETTER"
    elif delta >= -0.05:
        verdict = "on par"
    else:
        verdict = "classical better — non-classical needs work"
    return {
        "available": True,
        "non_classical_word_acc": round(nc, 4),
        "classical_baseline_word_acc": round(cl, 4),
        "delta": delta,
        "verdict": verdict,
        "on_par_or_better": delta >= -0.05,
        "trials": trials, "epochs": epochs,
        "note": "Honest parity: 'on par or better' is asserted only when the measured delta supports it.",
    }


def parity_report() -> dict:
    """Combined parity result for the scanner to certify the non-classical layer."""
    bench = benchmark()
    return {"parity": bench,
            "certified_god_tier_parity": bench.get("on_par_or_better", False),
            "note": "Non-classical layer parity is measured, not claimed."}
