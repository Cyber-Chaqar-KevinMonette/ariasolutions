"""proving_ground — the standing scored benchmark (Fable F3).

Verified gap it closes (GOD_TIER_CRITERIA §7): every eval tool computed
scores on the fly and persisted NOTHING — "trend" was recomputed from raw
counts each call. This is the first place her scores are WRITTEN DOWN:
a fixed, versioned task suite, each task scored MECHANICALLY (the smoke-
gate discipline — assertions on events and outputs, no LLM judge),
results appended to proving_ground/results.ndjson, trend computed from
STORED scores.

The offline suite (scripted clients, no Ollama) runs in pytest; the live
suite (`python -m sovereign_agent.proving_ground` / the runbook) needs a
real model and is operator-invoked, like the gates.
"""
from .runner import SUITE_VERSION, ProveResult, latest_scores, run_offline_suite, trend  # noqa: F401
