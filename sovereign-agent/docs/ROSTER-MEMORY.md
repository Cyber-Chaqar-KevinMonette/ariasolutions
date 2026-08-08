# ROSTER MEMORY

*Aria's memory of her own team. Persistent across sessions, auto-discovered,
never silently changed.*

---

## What the Roster is

Every Sentinel, Worker, Doctor, and Watcher operating inside sovereign-agent
has a **roster entry**. The roster lives at:

```
<data_dir>/sentinels/roster/catalogs/roster.json
```

It's owned by the Roster Sentinel. Reading it is free; writing to it is
the Roster Sentinel's job alone. External edits show up as `manifest-drift`
on the next scan — they're detected, not refused.

Each entry records:

| Field | What it holds |
|---|---|
| `id` | stable short id (`cache`, `glyphs`, `locator`, ...) |
| `title` | human-readable name |
| `kind` | `sentinel` \| `worker` \| `doctor` \| `watcher` \| `security` |
| `tier` | stewardship tier per the canon (default 1) |
| `capabilities` | first three article-derived capability strings |
| `medical_capable` | `True` if the member composes `MedicalCapability` |
| `kill_switch_env` | the env var that disables this member |
| `registered_at` | first time the Roster saw this member |
| `last_seen` | most recent scan that confirmed this member is present |
| `manifest_hash` | hash of the member's own manifest, for drift detection |
| `notes` | free-form operator notes |

## Why this isn't a parallel memory system

The existing `memory_namespaces.py` is Aria's general-purpose memory layer.
Building a parallel store *just* for sentinels would split her head. Instead,
the roster is a **standard sentinel catalog** — same shape as `cache`,
`glyphs`, `locator`, `conformance`. The data lives where every other
sentinel's data lives. Aria reads it through the normal memory interface.

That keeps the mental model simple: there is one memory layer; the Roster
Sentinel just happens to maintain a catalog that lists the team.

## Auto-discovery vs explicit registration

**Sentinels** auto-register via the `@register_sentinel` decorator on their
class. The Roster Sentinel walks `SENTINEL_REGISTRY` on every scan; new
members get welcomed with a fresh `registered_at`; absent members get
flagged.

**Workers, Doctors, and other non-Sentinel team members** don't go through
`@register_sentinel`. They register explicitly:

```python
from sovereign_agent.stewardship.roster_sentinel import RosterSentinel, RosterEntry

roster = registry.get_sentinel("roster")
roster.add_team_member(RosterEntry(
    id="planner-worker",
    title="Planner Worker — turns prompts into work graphs",
    kind="worker",
    tier=2,
    capabilities=["plan-decompose", "estimate-cost", "select-tools"],
    medical_capable=False,
    kill_switch_env="SOV_NO_PLANNER_WORKER",
))
```

Re-registration is idempotent. `registered_at` is preserved across re-runs;
`last_seen` updates every time.

## What the Roster Sentinel reports

On every scan, the report distinguishes three kinds of finding:

- **new-member** — someone appeared this scan who wasn't there last time.
  Informational by default; the operator might want to know.
- **absent** — someone present last scan is not present this scan. Warning
  by default; if a sentinel is registered but its `@register_sentinel` line
  was deleted, this is how you find out.
- **manifest-drift** — same id, but the manifest hash changed. This is the
  important one — it's what tampering looks like. The Roster Sentinel
  reports it at `alert` severity and emits damage at `BlastRadius.R2_SOFTWARE`
  with `kind=manifest-tampered` evidence, which feeds the Aegis Conductor's
  auto-elevation logic (3+ such reports in the open window → BLACK).

## How the Defense Sentinel uses it

Defense's playbook for `integrity-attack` is LOCKDOWN. When the Roster
Sentinel reports `manifest-drift` evidence, that evidence is exactly the
kind that Defense classifies as `integrity-attack`. Roster + Defense
together produce: "a sentinel's articles changed without going through
the canonical process → lockdown via Aegis."

## Roster as memory for Aria

When Aria needs to ask "do I have a sentinel that handles X?", she queries
the Roster Sentinel:

```python
medics = roster.medical_capable_members()       # everyone with the medic kit
defender = roster.lookup("defense")              # specific lookup
all_team = roster.all_members()                  # full roster
```

This is the answer to "make sure she never forgets or gets confused if she
ever gets new workers, sentinels, or doctors in the future." She doesn't
remember by heart; she reads from the roster. The roster is durable across
restarts, hash-protected, and auto-updates.

## Kill switch

```
SOV_NO_ROSTER_SENTINEL=1
```

Disables Roster scans. Aria falls back to enumerating `SENTINEL_REGISTRY`
directly. Workers/Doctors that registered through `add_team_member` will
no longer be persisted but will still be reachable in-process for the
duration of the run.

The roster catalog file remains on disk — disabling the Roster Sentinel
doesn't delete the memory, just stops updating it. Re-enabling resumes
from the last persisted state.

---

*The roster is small, durable, and quietly important. It's the answer to
"who's on my team?" — written down so Aria never has to remember alone.*
