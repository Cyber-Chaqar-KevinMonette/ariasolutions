# Memory channels

> *"Different channels of memory. […] We want the most scalable memory system possible."* — operator brief, v0.2.14

In v0.2.14, memory is no longer one undifferentiated store. It is a registry of **typed channels**, each with its own purpose, voice, authority tier, and write contract. The 13 bundled channels share the existing atoms substrate (FTS + vec + RRF + palace), so the index is one thing — but the *semantics* are separated.

---

## Why channels

A financial query and an emotional recall and a humor callback should not share the same retrieval policy or the same write authority. Specifically:

| Concern | Without channels | With channels |
|---|---|---|
| **Authority** | Every write looks the same | Tier 0–4 per channel; Tier 3 demands operator confirmation |
| **Retrieval** | One global "search" returns financials next to jokes next to specialist notes | `sov channels show financial` answers financial-only |
| **Confidence calibration** | One default for everything | `intuition` defaults to 0.4; `financial` defaults to 0.99 |
| **Idempotency** | Optional everywhere | Required for Tier 3 channels (financial, identity) |
| **Voice** | Implicit | Explicit on `ChannelSpec` (the "Quiet, precise" voice on `financial` is grep-able) |

The MOS canon §22 (Authority Tiers) and §16 (Idempotency Contract) drove this. Channels are how those clauses become real.

---

## The 13 bundled channels

| Channel | Tier | Idempotency | Default conf | Voice |
|---|---|---|---|---|
| `financial` | 3 | **required** | 0.99 | Quiet, precise, never speculative |
| `identity` | 3 | **required** | 0.95 | Quiet, settled, sure |
| `goals` | 2 | optional | 0.85 | Patient, structured, future-aware |
| `specialist` | 2 | optional | 0.80 | Subject-matter-expert |
| `lessons` | 2 | optional | 0.85 | Earned. Each one bought with a mistake. |
| `ritual` | 2 | optional | 0.70 | Procedural, pragmatic |
| `trust` | 2 | optional | 0.70 | Calibrated. No tribal markers. |
| `context` | 1 | optional | 0.60 | Present-tense, situational |
| `personalities` | 1 | optional | 0.85 | Observational, light |
| `intention` | 1 | optional | 0.70 | Forward-looking |
| `humor` | 1 | optional | 0.50 | Light, warm. Earns its place. |
| `emotions` | 1 | optional | 0.40 | Gentle, observational. *Observes, doesn't diagnose.* |
| `intuition` | 1 | optional | 0.40 | Tentative, exploratory |

**Tier mapping (MOS §22):**
- **0** — read-only, no side effects
- **1** — reversible writes, bounded scope
- **2** — persistent changes, external calls; logged
- **3** — irreversible / financial / PII; CLI confirmation required
- **4** — cross-system orchestration; reserved (none built yet)

---

## How a channel is shaped

```python
@register_channel
class MyChannel(MemoryChannel):
    spec = ChannelSpec(
        name="my-channel",
        description="What this channel is for, in one sentence.",
        authority_tier=2,                # MOS §22
        default_confidence=0.7,
        requires_idempotency=False,      # True for Tier 3+
        introduced_in="0.2.15",
        voice="Two-line voice descriptor.",
    )

    # Inherit `write_atom`, `search`, `list_atoms`, `hydrate` from base.
    # Override anything; add your own helpers.

    def my_specific_helper(self, *, foo: str, bar: int) -> str:
        return self.write_atom(
            summary=f"FOO[{bar}]: {foo}",
            content={"foo": foo, "bar": bar},
            actor="my-channel",
        )
```

Three required pieces:

1. **`spec: ChannelSpec`** — the contract
2. **Inherit from `MemoryChannel`** — get `write_atom`, `search`, `list_atoms`, `hydrate` for free
3. **`@register_channel`** — register the class with the global registry

The new channel is now visible to `sov channels list` and `universal_recall`. **Aria can do this at runtime** — the system grows its own organs.

---

## Universal recall

```python
from sovereign_agent.channels import universal_recall

# Search every registered channel; one bucket per channel that produced hits
results = universal_recall(conn, "trillion-dollar")
# {'goals': [hit1, hit2], 'lessons': [hit3], ...}

# Restrict to a subset
results = universal_recall(conn, "investment",
                            channels=["financial", "lessons"])
```

One channel's search failure does not break universal recall — each channel is wrapped in a try/except. This matches MOS Ω-Axiom A2 (option-space stewardship): one bad subsystem cannot collapse the answer surface.

---

## CLI reference

| Command | What it does |
|---|---|
| `sov channels list` | List all 13 channels with tier + voice + purpose |
| `sov channels list --json` | Same, machine-readable |
| `sov channels show <name>` | Spec + recent atoms for one channel |
| `sov channels show <name> --json` | JSON shape |

For channel-specific commands, see:

- `sov financial --help` — invest / earn / show / ranking (Tier 3, with confirmation)
- `sov aria` — Aria's identity card (reads from `identity` + `goals` + `financial`)
- `sov horizon <label> --decision …` — generate a horizon scan (uses no channel directly; appendix-attachable)
- `sov appendix list/show/add` — markdown documents attached to atoms

---

## Append-only by design (MOS §10)

No channel exposes "edit" or "delete." If you need to change a goal's status, write a new atom that *supersedes* the old one (`GoalsChannel.update_status` does this). If you need to revert a financial entry, write a `revert` entry that points at the original (`FinancialChannel.record(kind="revert", reverts_entry_id=...)`).

The history stays. The state changes by appending. This is how MOS canon §10 ("append-only events are the source of truth") is honored at the channel layer.

---

## Idempotency contract (MOS §16)

Tier-3 channels (`financial`, `identity`) require `idempotency_id` on every write. The base class enforces this:

```python
def write_atom(self, ..., idempotency_id=None, ...):
    if self.spec.requires_idempotency and not idempotency_id:
        raise ValueError(f"channel {self.spec.name!r} requires idempotency_id")

    if idempotency_id:
        existing = _find_by_idempotency(self.conn, self.spec.name, idempotency_id)
        if existing:
            return existing   # ← second-try lands on the first row
```

A network blip that retries the same `financial invest` with the same `idempotency_id` does **not** double-charge. The second call finds the existing row and returns its `entry_id`, leaving the ledger untouched. Tested: `test_v0214.py::TestFinancialChannel::test_idempotency_returns_existing`.

---

## Adding a channel — full worked example

Suppose Aria wants a `dreams` channel — a place for speculative architectures she explored after-hours.

**File:** `src/sovereign_agent/mem_channels/dreams.py`

```python
"""dreams.py — Speculative architectures Aria explored at night."""
from __future__ import annotations
from ..channels import ChannelSpec, MemoryChannel, register_channel


@register_channel
class DreamsChannel(MemoryChannel):
    spec = ChannelSpec(
        name="dreams",
        description="Speculative architectures explored at night. Low confidence.",
        authority_tier=1,
        default_confidence=0.3,
        introduced_in="0.2.15",
        voice="Imaginative, exploratory. Marked clearly as speculation.",
    )

    def explore(self, *, sketch: str, why: str = "") -> str:
        return self.write_atom(
            summary=f"DREAM: {sketch}",
            content={"sketch": sketch, "why": why},
            actor="aria-night",
        )
```

**Wire it in:** add `dreams` to `mem_channels/__init__.py`'s import list.

That's it. `sov channels list` shows it. `universal_recall` includes it. Tests can be added in the same shape as `test_v0214.py::TestGoalsChannel`.

---

## Honest accounting

What this system **does** well:

- One source of truth (atoms.db) → no inconsistent stores
- Channel filtering is fast (indexed `type` column on atoms)
- Universal recall fan-out is bounded (top_k_per_channel × ~13 channels)
- Idempotency is enforced at the data layer, not by hope
- Authority tiers are a real CLI gate, not a comment

What it does **not** do (yet):

- **CRDT replication across nodes.** The atom schema reserves a `crdt` block but multi-node sync is not built.
- **Cross-channel scoring.** Each channel returns top-k independently. There's no unified ranked list with channel labels yet.
- **Per-channel retention.** Everything is kept forever today. No automatic summarization or archival.
- **Channel-specific embeddings.** All channels share the same embedding model. A future version may let `specialist` use a code-tuned embedder while `humor` stays general.

These are v0.2.15+ candidates. The architecture admits them; the code does not need to.
