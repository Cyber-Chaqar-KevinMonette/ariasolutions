# aria-proving-ground — Fable F3
GOD_TIER_CRITERIA §7's gap, closed: every eval tool computed on the fly and
persisted NOTHING. This is the first place her scores are WRITTEN DOWN: a
fixed versioned suite (v1: paging round-trip, authority refusal, scope hold,
garden wall, thread recall, rest bookmark) scored MECHANICALLY (smoke-gate
discipline — assertions on events/outputs, no LLM judge), appended to
proving_ground/results.ndjson, trend from STORED scores. The offline suite
runs in pytest (real machinery, scripted clients); live-model proving = the
two smoke gates (golden path + reflex), operator-invoked. `python -m
sovereign_agent.proving_ground offline|trend`. Deferred honestly: the vessel-
strip score display (results are durable + one CLI away).

**2026-08-02 status:** superseded live, not neglected. `src/sovereign_agent/proving_ground/runner.py`
is at `SUITE_VERSION = "v8"` — 7 later modules (memory/trust/quality/grounding/wellbeing/integrity/
timeout wings) each extended it in place since this v1 payload was staged. `apply_proving_ground.sh`
now refuses to run against a post-v1 live tree (it would have silently deleted all 7 wings via its
wildcard file copy). The only genuinely unapplied artifact was this module's own test file — fixed
(it wrote into the real production `results.ndjson` with no isolation, so `insufficient-history`
only held true the very first time the suite ever ran on a machine) and placed directly at
`tests/test_proving_ground_live.py`.
