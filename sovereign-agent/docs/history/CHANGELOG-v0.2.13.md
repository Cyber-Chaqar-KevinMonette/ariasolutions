# sovereign-agent v0.2.13

**Release theme:** *Personality, FOSS, anti-zombie, anti-ghost, validators, edge-case registry, modulated memory, hardening.*

This is the largest non-breaking release since v0.2.6. It adds five new modules
(personas, foss, edge_cases, validators, health, memory_namespaces), wires them
into the dream-builder loop, and ships a coherent set of CLI commands that turn
those modules into real workflow features. **No data migration required** —
existing v0.2.12 dreams, continuations, projects, and atoms.db all upgrade cleanly.

---

## What's new

### Personas — the system gets a voice (and a spine)

`sovereign_agent.personas` is a registry of structured persona-prompts. The
star is **`master-architect`** — the founding voice of the dream-builder. It's
warm, rigorous, and impossible to bullshit. Three other personas ship in the
same registry:

- `master-architect` — dream ideate / architect / document steps
- `friendly-builder` — code-heavy build steps
- `patient-auditor` — palace-reflect (audit-shaped reads)
- `gentle-advocate` — when the agent disagrees with the operator

Each persona has named *principles* (CLARITY OVER CLEVERNESS, ANTI-ZOMBIE,
RESPECT THE FOSS LINEAGE…), enumerable *anti-patterns* (try/except that
swallows the error, names that lie), and a *voice* line. All four are wired
into the trillion-dollar planner's per-step prompts.

```bash
sov personas list                       # see them all
sov personas show master-architect      # full render
```

### FOSS — the agent honors prior art

`sovereign_agent.foss` ships with a curated SPDX table (MIT, Apache-2.0, GPL
family, BSD variants, MPL, ISC, CC0, CC-BY, Unlicense), license-detection
heuristics for embedded license blocks and `SPDX-License-Identifier:` comments,
license-header generators, and a conservative compatibility checker that
**refuses to guess** — when in doubt it returns "needs human review."

The dream-builder's documentation step now writes a `License` section with the
recommended SPDX identifier and citation reasoning.

### Anti-syntax / anti-indentation validators

`sovereign_agent.validators` is the immune system. Every file the dream-builder
writes goes through type-appropriate validation **before** it reaches atomize:

- **Python:** AST parse + tab/space mixing detection (the LLM smoking gun)
- **JSON:** parse + nesting depth check
- **YAML:** safe_load
- **Markdown / text:** non-empty + null-byte detection

Failed files move to `<cycle_dir>/quarantine/` with a `.errors.json` companion
documenting the failure. **Quarantined files are never atomized**, so a single
bad cycle can't poison `memory_search` for future cycles.

### Anti-zombie / anti-ghost health checks

`sovereign_agent.health` finds two failure modes:

- **Zombies:** continuations marked `in_progress` whose driver process died
- **Ghosts:** dreams marked `active` with no live cycle, orphan cycle
  continuations, stale lock files held by dead PIDs

Plus **idle-cycle detection**: if the last 3 cycles each produced ≤1 atom, the
dream is auto-paused and the operator is told why. This stops infinite loops
where the agent has saturated its idea space and is just burning tokens.

```bash
sov health check               # read-only audit
sov health repair --dry-run    # preview fixes
sov health repair --apply      # actually fix (with confirm prompt)
```

### Edge-case registry — a map of the cliffs

`sovereign_agent.edge_cases` is a central catalog of every defensive check in
the codebase. Each entry has a stable id (`EC-DREAM-001` style), location,
description, what fires it, recovery path, and severity. **20 edge cases**
documented in v0.2.13.

When something rare happens, run `sov edge-cases show <id>` and you get the
full context: what it means, where it lives, what to do. New defensive checks
in code MUST register here, which forces every author to think about the
recovery path before merging.

```bash
sov edge-cases list                       # all 20
sov edge-cases list --subsystem EC-VAL    # filtered
sov edge-cases show EC-DREAM-006          # full detail
```

### Per-project memory namespaces

`sovereign_agent.memory_namespaces` adds first-class project-scoping for atoms.
Atoms tagged with a project are visible **globally and** when filtered to that
project. This is additive — untagged atoms stay globally visible, so the
default behavior is unchanged.

When a dream is tied to a project (`sov dream start --project X "..."`),
atomize automatically tags every atom it writes with that project name. The
ideate step's `memory_search` calls then default-prefer that project's lineage,
giving the dream a focused memory.

### Hardening — fcntl on dream YAML, cached counts, idle detection wiring

- **`DreamStore.lock(dream_id)`** — fcntl-backed exclusive lock on the dream
  YAML. Closes the rare two-runner race that v0.2.12 documented as
  "single-operator by design."
- **`count_files_under` skips `quarantine/`** — quarantined files don't inflate
  cap accounting.
- **`count_files_in_cycle`** — cheap incremental count helper.
- **EC-DREAM-005** — runner detects "cycle paused but dream active" and
  auto-pauses the dream too (otherwise inline drivers spin on `outcome="paused"`).
- **EC-DREAM-006** — runner detects 3 idle cycles in a row and auto-pauses.

### `CycleEntry.atoms_written` and `quarantined_count`

Cycles now record (a) how many *new* atoms hit atoms.db (vs already-present
duplicates) and (b) how many files were quarantined. The atomize step's output
is parsed at finalize-time. These two fields drive idle detection and let
`sov dream show` give an honest cycle-by-cycle novelty/quality picture.

---

## New commands

| Command | What it does |
|---|---|
| `sov status` | Top-level one-glance summary (was `sov do status`) |
| `sov health check` | Anti-zombie / anti-ghost / idle scan |
| `sov health repair [--dry-run\|--apply]` | Plan and apply fixes |
| `sov edge-cases list [--subsystem X]` | List the registry |
| `sov edge-cases show EC-...` | Full detail for one edge case |
| `sov personas list` | List registered personas |
| `sov personas show <name>` | Full rendered persona |
| `sov dream tail <dream_id>` | Stream the latest cycle's idea/architecture/README |
| `sov dream gc [--older-than 30d]` | Garbage-collect work_dirs of terminal dreams |

All new commands honor `--json` for scripting and emit edge-case telemetry events.

---

## Tab completion

Typer's built-in completion now works:

```bash
sov --install-completion bash    # or zsh, fish
exec $SHELL                      # reload
sov d<TAB>                       # → dream, do, doctor
sov edge-cases <TAB>             # → list, show
```

---

## Test count

435 (v0.2.12) → **503 (v0.2.13)**. +68 new tests across personas, FOSS,
edge_cases, validators, health, memory_namespaces, and dream hardening.
No regressions; full suite passes in ~14s.

---

## Upgrade

Drop-in over v0.2.12. No migration. Your data is untouched.

```bash
tar xzf sovereign-agent-v0.2.13.tar.gz
cd sovereign-agent-v0.2.13
pip install --break-system-packages -e .
sov --version    # → sovereign-agent 0.2.13
sov doctor       # all green
sov status       # NEW — top-level summary
```

---

## Rollback

If you want to revert:

```bash
pip install --break-system-packages sovereign-agent==0.2.12
```

The new fields on `CycleEntry` (`atoms_written`, `quarantined_count`) are
forward-incompat: v0.2.13 YAML files load fine on v0.2.12 (the fields are
simply ignored), but if you've used the new auto-pause status messages
("AUTO-PAUSED: …") on a dream, those notes survive the downgrade as plain text.

---

## What got deferred to v0.2.14

- **Per-cycle pathguard root for `dream_build`** — passing the cycle_dir as
  an additional sandbox boundary for the build step. Currently relies on the
  global sandbox + the model following instructions.
- **`sov dream branch <id>`** — fork a dream from its current state. Designed,
  not yet built.
- **`sov projects watch <name>`** — inotify daemon mode for live tracking.
- **`sov dream metrics`** — throughput/quality numbers for tuning caps.
- **Mocked-model end-to-end test of the full dream cycle** — the cycle's
  static pieces are well covered, but a synthetic-model integration test
  would be valuable.

---

## Honest accounting — what to verify before long unattended runs

The same advice from the v0.2.12 release applies: do a bounded test cycle
first. New in v0.2.13: also check that validators are quarantining, not
crashing, on at least one bad file:

```bash
sov dream start --max-cycles 1 --max-files 10 --drive
sov dream show <dream_id>
ls $(sov dream show <dream_id> --json | jq -r '.cycles[0].cycle_dir')/quarantine/  # may be empty if model wrote clean code
sov atoms search "trillion" -k 5
```

If any quarantines exist, inspect the `.errors.json` companions to confirm
the validators are catching the right kinds of failures.

---

*Built with care, in the spirit the user asked for: fun, powerful, reliable, friendly, super intelligent. Master Architect approved.* 🏛️
