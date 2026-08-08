# AEGIS — Operator Guide

*The incident response plane for sovereign-agent v0.2.35.0 "The Aegis"*

---

## What Aegis is

Aegis is sovereign-agent's defensive layer. Stewardship watches the work
being done; Aegis watches the system that does the work. They share the
fractal shape (manifest → catalogs → atoms, hash-bound) but their jobs differ.

The one-line doctrine: **distributed detection, centralized decision, scoped
action, dead-man's failsafe that prefers freeze over flail.**

## What it is *not*

- **Not a firewall.** It does not block network traffic.
- **Not an antivirus.** It does not scan for known malware signatures.
- **Not autonomous at the OS level.** Aegis cannot rotate your SSH keys,
  reinstall packages outside the venv, or modify systemd units. R3+ is
  operator-only, by design.
- **Not a substitute for backups.** Aegis tells you when something drifted;
  it doesn't have a time machine. Your backup discipline still matters.

## Mental model

```
        ┌──────────────────────────────────────────────┐
        │             AEGIS CONDUCTOR                  │
        │  (the only module that directs sentinels)   │
        └──────────────┬───────────────────────────────┘
                       │ leases / quiesce / unquiesce
   ┌───────┬───────────┴───────────┬─────────────────┐
   ▼       ▼                       ▼                 ▼
 cache   glyphs   locator   conformance   (more sentinels arriving)
   │       │       │            │
   └───────┴───────┴────────────┘
        damage reports + repair plans + evidence
                       │
                       ▼
        ┌──────────────────────────────────────────────┐
        │             AEGIS LEDGER                     │
        │  append-only, hash-chained, tamper-evident  │
        └──────────────────────────────────────────────┘
```

The Conductor is a singleton. There is one. It owns the conductor signing
key, the DEFCON state machine, and the repair-lease ledger.

## The five DEFCON states

| State | What it means | What changes for you |
|---|---|---|
| **GREEN** | normal | nothing — sentinels scan on cadence |
| **YELLOW** | anomaly, unconfirmed | nothing visible — affected sentinel scans faster |
| **ORANGE** | confirmed degradation, scope ≤ R1 | inbox notification, async; auto-repair authorized |
| **RED** | compromise OR scope R2+ | synchronous notification, Aria loop pauses |
| **BLACK** | integrity in question | total quiesce; only you can return to GREEN |

Upward transitions are automatic. Downward transitions need you (except
YELLOW → GREEN, which auto-downgrades after a quiet period).

## Blast radius (R0..R5)

Every incident is classified at intake. The classification governs what
Aegis is permitted to do without you.

- **R0** — single artifact. Sentinel acts on its own surface, reports within 60s.
- **R1** — one sentinel's surface. Lease required; Conductor authorizes.
- **R2** — Aria software boundary. Quorum required (≥2 sentinels corroborate).
- **R3** — workstation (OS state). **Operator-only. Aegis cannot execute.**
- **R4** — network. **Operator-only.**
- **R5** — federation. Out of scope for v0.2.35.

The R3+ ceiling is the sovereignty line. A local-first agent that can
autonomously alter OS state is no longer local-first.

## Day-to-day: what to expect

**Most days, you won't notice Aegis.** The Conductor is idle when no
incidents are open. The ledger grows by a handful of entries per week
under normal operation (sentinel bootstraps, occasional YELLOW pulses).

When something happens:

1. A sentinel reports damage. Conductor opens an incident, classifies it,
   maybe elevates DEFCON.
2. If R0/R1, Conductor issues a lease and the sentinel repairs itself.
   You see an inbox notification after the fact.
3. If R2, Conductor waits for corroboration from a second sentinel.
   Either it comes (lease issued) or the incident is logged as
   uncorroborated.
4. If R3+, you get a synchronous notification with a proposed plan. The
   plan is text and a command list; you read it and decide.

## Commands

```bash
# Inspect current DEFCON state
sov aegis status

# Walk the incident log
sov aegis incidents --tail 20

# Verify the ledger's hash chain (slow on long histories; use for audits)
sov aegis verify-ledger

# Bring DEFCON back to GREEN after an incident (requires reason)
sov aegis downgrade GREEN --reason "incident xyz123 resolved by hand"

# Emergency kill switch — disables Aegis entirely
SOV_NO_AEGIS=1 sov ...

# Per-sentinel kill switch — disables one sentinel's contribution
SOV_NO_CACHE_SENTINEL=1 sov ...
```

*(The `sov aegis *` subcommands are part of v0.2.35.0 — they wrap the
`AegisConductor` Python API for operator use. Until they ship, the API
is accessible from `python -m sovereign_agent.aegis` or directly.)*

## What can go wrong, and what to do

### "Aegis won't start — conductor key permission error"

The conductor key (`~/.local/share/sovereign-agent/aegis/conductor.key`)
must be mode `0600`. If permissions drifted (e.g., a previous install
left it world-readable), Aegis refuses to start. **This is the correct
behavior** — silent self-repair of permission failures hides real
problems.

```bash
chmod 600 ~/.local/share/sovereign-agent/aegis/conductor.key
```

### "Aegis went to BLACK and I don't know why"

Walk the ledger backward:

```bash
sov aegis incidents --tail 5
```

The most common cause: three sentinels reporting manifest-tampered
evidence within the open-incident window. This is by design — the
question "is the system corrupt?" is the one place automatic freeze is
safer than letting work proceed.

If you've verified nothing was actually tampered (e.g., you manually
edited a sentinel's articles and the hash check fired), re-bootstrap
the affected sentinel:

```bash
sov sentinels bootstrap --reseal cache
```

Then `sov aegis downgrade GREEN --reason "false-positive: manual edit to cache articles"`.

### "I want to disable a specific sentinel temporarily"

Per-sentinel kill switch in the environment is the right tool:

```bash
SOV_NO_GLYPHS_SENTINEL=1 sov ...
```

This silences the named sentinel without affecting any others.

### "I want to disable Aegis entirely"

```bash
SOV_NO_AEGIS=1 sov ...
```

System reverts to v0.2.34 behavior: sentinels still scan and propose,
operator acts directly. No Conductor, no leases, no DEFCON state machine.

## What Aegis does NOT do without you

- Modify OS state outside `data_dir` and the venv
- Rotate credentials (SSH, API keys)
- Touch the network
- Decide what's "good" vs "bad" work — that's QASentinel's job (when it ships)
- Lock you out — there is always a kill switch, always a downgrade path

## Reading the ledger

Each entry is one JSONL line. The fields:

```json
{
  "sequence": 17,
  "kind": "lease-issued",
  "written_at": "2026-05-24T14:23:11.000Z",
  "actor": "conductor",
  "data": {
    "lease_id": "01H...",
    "incident_id": "01H...",
    "sentinel_id": "cache",
    "scope": 1,
    "plan_hash": "abc...",
    "ttl_seconds": 300
  },
  "prior_hash": "...",
  "entry_hash": "..."
}
```

`prior_hash` always equals the previous entry's `entry_hash`. The first
entry's `prior_hash` is the genesis constant
`sha256("aegis-ledger-genesis-2026")`. If you ever see these break,
that's a tamper signal — run `sov aegis verify-ledger` for the exact
broken sequence.

## What's next (v0.3.0 horizon)

- Aegis moves out-of-process. Currently in-module; v0.3.0 promotes it
  to a separate process (~hundreds of lines) talking over a Unix socket.
  This is the "watchman shouldn't live in the building it watches"
  refinement.
- Cross-witnessing across sentinels formalized. Today the Conductor
  treats damage reports as independent; v0.3 has them triangulate
  (Locator confirms paths Cache claims exist; Metrics confirms cadence
  rates Behavior claims).
- R3 proposals integrate with PolicyKit / launchctl / systemd — operator
  pre-authorizes specific *kinds* of workstation actions; Aegis can
  execute those specific kinds, nothing else.

---

*Aegis is built so you can mostly forget it exists. The one job that
matters: when something goes wrong, the system fails toward safe and
shows you exactly what happened. That's it. That's the whole story.*
