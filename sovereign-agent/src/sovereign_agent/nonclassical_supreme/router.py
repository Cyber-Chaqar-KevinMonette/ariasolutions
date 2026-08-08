"""nonclassical_supreme/router.py — "pure non-classical flow" as a real MODE, with honest LLM fallback.

The non-classical-first router: send a query to the superposition processor first. If its measured
confidence (peakedness of the Born distribution) clears the threshold, RETURN the NC answer — fast, free,
CPU, no GPU. If not, ESCALATE to the classical LLM (graceful fallback). This is the honest realization of
"replace LLMs where it can": the NC layer handles the structured majority at microsecond speed; the LLM is
the fallback for what genuinely needs it. Modes: `pure-nc` (NC only, no fallback) · `hybrid` (NC-first).
"""
from __future__ import annotations

from . import superpose

DEFAULT_CONFIDENCE_THRESHOLD = 0.55


def route(query: str, candidates: list | None = None, *, mode: str = "hybrid",
          threshold: float = DEFAULT_CONFIDENCE_THRESHOLD, seed: int = 0) -> dict:
    """Route a query NC-first. Returns {handled_by, result, confidence, escalated, mode}.

    - If `candidates` are given, the NC processor selects among them (its strongest task).
    - confidence ≥ threshold → NC handles it.
    - else, in `hybrid` mode → escalate to the LLM (caller runs the LLM); in `pure-nc` → return NC's best, flagged low-confidence.
    """
    if candidates:
        res = superpose.process(query, candidates, seed=seed)
        conf = res["confidence"]
        if conf >= threshold:
            return {"handled_by": "non_classical", "result": res["result"], "confidence": conf,
                    "escalated": False, "mode": mode, "latency_class": "microseconds",
                    "distribution": res["distribution"]}
        # low confidence
        if mode == "pure-nc":
            return {"handled_by": "non_classical", "result": res["result"], "confidence": conf,
                    "escalated": False, "mode": mode, "low_confidence": True,
                    "note": "pure-nc mode: returning NC's best despite low confidence (no fallback)."}
        return {"handled_by": "llm_fallback", "result": None, "confidence": conf, "escalated": True,
                "mode": mode, "reason": f"NC confidence {conf:.2f} < {threshold} — escalate to the LLM.",
                "nc_best": res["result"]}
    # no candidate set → this is open-ended; NC can't select, so escalate (or refuse in pure-nc)
    if mode == "pure-nc":
        return {"handled_by": "non_classical", "result": None, "escalated": False, "mode": mode,
                "low_confidence": True, "note": "pure-nc: open-ended query with no candidate space — NC abstains."}
    return {"handled_by": "llm_fallback", "result": None, "confidence": 0.0, "escalated": True,
            "mode": mode, "reason": "open-ended query (no candidate space) — the LLM handles generation."}


def envelope() -> dict:
    """The honest division of labor between the non-classical layer and the LLM."""
    return {
        "non_classical_first": ["selection", "classification", "ranking/decision", "associative recall",
                                "routing", "scoring", "fast filtering"],
        "llm_fallback": ["open-ended generation", "long-form reasoning", "novel synthesis", "world knowledge"],
        "principle": "NC handles the structured majority at microsecond speed + zero GPU; the LLM is the "
                     "fallback for open-ended work. Most system calls are structured → NC-first is a huge win.",
    }
