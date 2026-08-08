# MOS Canon Alignment — v0.2.14

The Unified MOS God-Tier Canon Edition Ω was used as a **flexible guide for higher leverage**, not as a strict rulebook. This document is the audit trail: each v0.2.14 module maps to specific canon clauses.

The principle from MOS Ω-Axiom A6: *"Layered Identity (Core vs Strategy) — hold a small immutable core; keep strategies, plans, and implementations flexible. Resist value drift; resist fanatic clinging."* That is what we did. The kernel obeys the canon. The implementation chooses what serves the operator.

---

## Module → canon clause

| Module | Canon section | What it implements |
|---|---|---|
| `aria.py` | Ω-Axiom A6 | Layered identity — small immutable kernel (7 commitments, stance, voice, tagline) above mutable channels |
| `aria.py` | Behavioral Law 5 | Calibrated uncertainty — Aria's "what I might be wrong about" stance is in the kernel voice |
| `channels.py` | §22 Authority Tiers | Every `ChannelSpec` declares a tier ∈ {0,1,2,3,4} |
| `channels.py` | §10 Append-only events | `write_atom` is `INSERT OR IGNORE`; supersession via new atoms, not edits |
| `channels.py` | §17 Observability | Every write emits `channel-write-d` event with channel, tier, idempotency_id |
| `channels.py` | §14 Knowledge Atoms | Channel atoms use the existing canonical atom schema |
| `mem_channels/financial.py` | §16 Idempotency Contract | `requires_idempotency=True`; deterministic `entry_id` from `idempotency_id`; UNIQUE constraint at storage |
| `mem_channels/financial.py` | §16.6 Side-Effect Propagation | Companion atom written *first*, ledger row second — defends the "operation succeeded but result-storage failed" failure mode |
| `mem_channels/financial.py` | §10 Lifecycle invariants | Reverts are counter-entries with `reverts_entry_id` FK, never deletes |
| `mem_channels/financial.py` | §22 Tier 3 | CLI `financial invest/earn` prompts for operator confirmation by default |
| `mem_channels/identity.py` | §22 Tier 3 | Identity changes require explicit operator commit |
| `mem_channels/emotions.py` | Behavioral Law 3 | Framing field set to `"observation-not-diagnosis"` — the canon's emotional honesty law made explicit at the data layer |
| `mem_channels/intuition.py` | Behavioral Law 5 | Default `confidence=0.4` — explicit low-confidence floor |
| `mem_channels/goals.py` | §6.5 Horizon Scan | Goal timeframes match the canon's horizons (3-month / 12-month / 3-year / 7th-generation) |
| `mem_channels/intention.py` | Behavioral Law 5 | Calibration loop — declared intent paired with observed outcome |
| `appendix.py` | §14 (atom extensions) | Appendix docs are FK-bound to atoms but live in a separate table; survives lost lineage gracefully |
| `horizon.py` | §6.5 Horizon Scan | Template matched verbatim — 3-month / 12-month / 3-year / 7th-generation + emerging signals + best forward path |

---

## Where we deviated, and why

The canon is comprehensive. Some clauses were not built. Each is a deliberate choice, not an oversight:

| Clause | Status | Rationale |
|---|---|---|
| §17.2 Token-level metrics (TTFT, TBT, KV cache hit rate) | not built | sovereign-agent runs against local Ollama in single-operator mode; the metrics matter at fleet scale, not solo |
| §18.3 Secret Zero protocol | partial | We have a local secret key for approvals; full Secret Zero with rotation/HSM is overkill for local-first operation |
| §21 Four-Layer Cognitive Architecture (L1 spine, L2 skill mesh, L3 hooks, L4 sub-agents) | partial | L1 (CLAUDE.md) is the operator's responsibility, not the agent's; L2 lives upstream in Anthropic's skill system; L3 hooks exist as `validators.py` (v0.2.13); L4 sub-agents are designed but not generalized |
| §6.4 PIAL infinite-audit loop | not built | Heavyweight; canon itself says "engage when stakes warrant deeper investigation." No production decision yet has warranted it. |
| §15 OpenAPI + RFC 9457 contracts | partial | We have CLI surfaces, not external HTTP endpoints. When sovereign-agent grows a server, this lands. |
| §20 Sealing (Merkle root over event days) | partial | Daily seal exists in the events plane (v0.2.x); cross-channel sealing of atoms is a future release. |
| CRDT replication (atom schema reserves the block) | not built | Single-node operation today; replication is a v0.3.0 candidate. |

---

## What this audit is for

When you (the operator) ask "is this thing actually doing what the doctrine says?" — this is the answer. The mapping is enforced by tests where it matters most:

- `test_v0214.py::TestFinancialChannel::test_idempotency_required` — §16 enforced
- `test_v0214.py::TestFinancialChannel::test_idempotency_returns_existing` — §16.2 atomicity behavior
- `test_v0214.py::TestIdentityAndAria::test_aria_kernel_constants` — Ω-Axiom A6 (the kernel is stable)
- `test_v0214.py::TestHorizon::test_render_includes_all_horizons` — §6.5 template fidelity

When the audit drifts, the test breaks. That's the contract.

---

*Per MOS canon §6.7 closing line: I know the next move. Should I proceed?*
