# sovereign-agent v0.2.12 — CHANGELOG

> *Released:* 2026-05-09  
> *Codename:* "Dream loop, plain English"  
> *Test count:* **435 passing** (v0.2.11 had 383, +52 new)

This release adds a **named, resumable, capped, infinite software-builder
loop** ("dream sessions"), a **plain-English entry point** (`sov do "..."`)
that translates a sentence into the right command + interactive prompts for
missing data, and **first-class pause/resume primitives** at both the
continuation level and the dream-session level. It also adds a **project
scanner** that detects added/modified/removed files between runs and emits
atoms so the rest of the system can react to changes.

Every change is **additive**. v0.2.11 continuations, palace data, atoms,
and config files are untouched and continue to work. There are no
migrations to run.

---

## Headline additions

### 1. Trillion-dollar dream sessions (`sov dream`)

A *dream session* is a long-lived, resumable plan to build software
forever (or until a cap is reached). Each cycle of the dream produces:

```
~/.local/share/sovereign-agent/dreams/<dream_id>/cycle-NNN/
  ├── idea.md            # what we're building this cycle
  ├── architecture.md    # design decisions
  ├── manifest.json      # which files we'll create
  ├── src/               # the actual code
  └── README.md          # how to run it
```

A dream cycle is just five planner steps:

```
ideate (orchestrator) → architect (orchestrator) → build (coder) →
document (orchestrator) → atomize (none, pure-Python)
```

When one cycle drains, the dream-runner plans the next, until a cap is
hit (`--max-files`, `--max-cycles`, `--max-seconds`) or the operator
pauses it. The shell driver `scripts/sovereign-dream-loop.sh` re-invokes
`sov dream advance` until the dream is terminal, mirroring the existing
`sovereign-continue-loop.sh` pattern: bounded model context per
invocation, OS-managed lifecycle, crash-resumable mid-cycle.

**The default cap is `--max-files 2000`** — a healthy ceiling that
prevents accidental runaway. Pass `--max-files 0` for "until I pause."

```bash
# create a dream, drive it inline
sov dream start --max-files 5000 --drive

# or: create then drive in a separate terminal
sov dream start --max-files 0
scripts/sovereign-dream-loop.sh dream-01J9...

# pause / resume any time
sov dream pause dream-01J9...
sov dream resume dream-01J9... --drive
```

The atomize step writes one atom per generated file with a deterministic
`atom_id` (`sha256(dream_id:cycle:path:hash)`). Result: the next cycle's
`memory_search` step naturally sees prior cycles, preventing the agent
from re-implementing the same idea twice. **Continuity is built into the
storage layer, not bolted on.**

Files added: `src/sovereign_agent/dream.py`, `dream_runner.py`,
`planners/trillion_dollar.py`, `scripts/sovereign-dream-loop.sh`.

### 2. Plain-English entry: `sov do "..."`

Instead of memorizing flag combinations, type what you want:

```bash
sov do "Build trillion-dollar software, max 2000 files"
sov do "Build trillion-dollar software forever"
sov do "Pause my dream"
sov do "Resume cont-01J9ABC..."
sov do "I updated genesis-seeds"
sov do "Inventory ~/AA-Erebo/Genesis-Seeds for markdown files"
sov do "Show status"
```

The parser is **deterministic and keyword-based** (`directives.py`) — no
model is invoked. This means:

- Zero latency for short directives.
- No trust boundary issue: a misclassifying model can't misroute a
  destructive directive.
- The agent doesn't need Ollama running just to type a command.
- Failures are debuggable: when classification fails, the error tells
  you which keywords were searched.

**Missing arguments become interactive prompts** with sensible defaults
and example suggestions. With `-y`, defaults are taken non-interactively;
required questions without defaults abort with a clear error.

Files added: `src/sovereign_agent/directives.py` and the `do` /
`dream` / `projects` subcommands in `cli.py`.

### 3. First-class pause/resume

```bash
# continuation-level
sov pause cont-01J9...                       # mark paused
sov resume cont-01J9... [--drive]            # un-pause; optionally drive

# dream-level (also pauses the underlying current cycle)
sov dream pause dream-01J9...
sov dream resume dream-01J9... [--drive]
```

The continuation status field gained a new value, `paused`, with strict
semantics:

- A paused continuation **cannot be advanced** by `continue_runner`. It
  returns `outcome="paused"` with no model invocation, no token spend.
- `update_status_from_steps()` **preserves** paused while there's still
  work to do; it only settles to `done` when every step is terminal.
- The `paused` value round-trips through YAML. Pre-v0.2.12 continuations
  are unaffected.

Implementation note: the runner refuses `paused` continuations explicitly
*before* the lock is held to drive a step, so a paused state cannot be
accidentally clobbered by a stale cursor.

### 4. Project scanner & change-aware atoms (`sov projects`)

Track named directories, scan for SHA-256 fingerprints, then re-scan
later to see what changed and write atoms for added/modified/removed
files so the agent and palace can pick up the changes.

```bash
sov projects scan genesis-seeds ~/AA-Erebo/Genesis-Seeds
# ... edit some files ...
sov projects update genesis-seeds              # scan + diff + atomize
sov projects update genesis-seeds --no-atomize # scan + diff, no atoms
sov projects update genesis-seeds --keep-old   # diff only, no snapshot
```

Output of `update`:

```
3 files added · 7 modified · 1 removed (148 unchanged)
atoms written: 11
snapshot: replaced
```

Atom IDs are deterministic (`sha256(project:kind:path:filehash)`) so
re-running an update with the same inputs is idempotent. Default
excludes match a sane set: `.git`, `.venv`, `node_modules`, `__pycache__`,
`dist`, `build`, `target`, `*.pyc`, `*.pyo`. The hash is streamed in 1MB
chunks (no full-file reads into memory). Symlinks are not followed by
default.

Files added: `src/sovereign_agent/projects.py`, `projects` subcommand
in `cli.py`.

### 5. Continuation aliases (light-touch)

```bash
sov continuations alias cont-01J9ABCDEFGH erebo-inventory-2025
# ... later ...
sov continue erebo-inventory-2025
```

Aliases are stored in `<config_dir>/continuation-aliases.yaml`. The
storage is intentionally minimal: a flat `alias → task_id` map. There's
no shadow database, no fuzzy matching, no precedence rules. If an alias
isn't found, fall back to a literal task_id.

### 6. Status surface (`sov status` via `sov do "status"`)

A one-screen summary covering continuations, dreams, and projects:

```
═══ status ═══
continuations: total=12 active=2 paused=1
dreams: total=1 active=1 paused=0
projects: 3
```

Driven from `_render_status()` in cli.py — wired into `sov do "status"`
and the shell `sov-status` alias was extended to also list dreams.

---

## Hardening / audit notes

### `AGENT_THINK=plan_only` is *not* vestigial

The v0.2.11 audit notes flagged the `think_mode` config field as
"possibly unused." On verification, this turns out to be **wrong** —
there are live readers in:

- `src/sovereign_agent/cli.py:475/482/496` — the `config show` output
  reads it and reports it.
- `src/sovereign_agent/ollama_client.py:1/35` — the Ollama client uses
  `SETTINGS.think_mode` to gate the `<think>...</think>` prompt prefix
  for thinking-capable models.

So `think_mode` is load-bearing and must remain. The audit comment in
the v0.2.11 docs is incorrect; this changelog supersedes it. No code
change in v0.2.12.

### Continuation status enum is now strict

A new module-level frozenset `_VALID_CONT_STATUSES` is checked by
`update_status_from_steps()` and `_from_yaml_dict()`. A YAML file with
an unknown `status:` value now raises `ContinuationCorrupt` rather than
silently passing through. This catches typos and drift across versions.

Backward compatibility: every status value v0.2.11 knew about is in the
frozenset. Old files load unchanged.

### `_NO_MODEL_DISPATCH` extended for dream_atomize

The pure-Python steps registry in `continue_runner.py` gained an entry
for `dream_atomize`. This is the cycle's terminator step — it walks the
just-built `cycle_dir`, computes deterministic atom IDs, and writes them
to atoms.db. No model call. No tokens. By landing it in
`_NO_MODEL_DISPATCH`, a paused Ollama / unreachable inference server
**does not** block dream cycles from finalizing.

### Files-on-disk is the single source of truth for cap accounting

`DreamSession.files_written` is recomputed by walking the `work_dir` at
the end of every cycle, not by summing per-cycle deltas. Consequence: a
crash mid-cycle doesn't leave a dream record claiming files exist that
got rolled back, nor undercount files that were partially written. The
cap check looks at the ground truth.

### Defensive ID generation

Cycle task IDs are deterministic: `cycle-{sha256(dream_id)[:8]}-{NNN}`.
Resuming a dream after a crash mid-cycle creates the same task_id, so
the existing continuation is reused (`FileExistsError` is caught and
treated as success). This makes the dream-runner safely re-entrant.

### Hard backstop on cycle count

`HARD_CAP_CYCLES = 100_000` in `dream.py`. Even with all caps set to
unbounded, a dream cannot exceed 100,000 cycles. This prevents pathological
runaway from a misconfigured session — a real escape valve.

---

## Test count history

| Version | Test count | Delta |
| --- | --- | --- |
| v0.2.11 | 383 | — |
| **v0.2.12** | **435** | **+52** |

The 52 new tests cover: `DreamCaps` boundary cases, `DreamStore` create/
get/list/yaml-roundtrip/corruption, `cycle_task_id_for` determinism,
`count_files_under` (with .git skipping), the trillion-dollar planner
shape and registry presence, `scan_directory` (excludes, max_files,
hashing), `diff_snapshots` (added/modified/removed/unchanged), the
directive parser (forever, until-i-pause, pause-with-id, project update,
inventory with path, unknown, empty), the `paused` continuation status
roundtrip and recompute, and the runner's refusal to advance paused
continuations.

All 383 v0.2.11 tests still pass, unmodified.

---

## Install / upgrade

This is a drop-in upgrade. From the unpacked tarball:

```bash
cd sovereign-agent-v0.2.12/
pip install --break-system-packages -e .
sov --version    # → sovereign-agent 0.2.12
```

No data-dir migration is needed. The new directories are created on
first use:

```
~/.local/share/sovereign-agent/
  ├── dream-sessions/         # NEW
  ├── dreams/                  # NEW (per-cycle work dirs)
  ├── projects/                # NEW
  ├── continuations/           # unchanged
  ├── atoms.db                 # unchanged
  ├── palace/                  # unchanged
  └── proposals/               # unchanged
```

To verify a fresh install:

```bash
sov --version
sov doctor
sov dream list                  # should print "(no dreams yet ...)"
sov projects list               # should print "(no tracked projects ...)"
sov do "show status"            # should render the status panel
```

---

## Rollback

If you need to revert:

```bash
pip install --break-system-packages sovereign-agent==0.2.11
```

The new YAML files under `dream-sessions/`, `dreams/`, and `projects/`
will be ignored by v0.2.11 (it doesn't read those paths). They can be
left in place — re-installing v0.2.12 picks up exactly where it left
off. **No data loss on rollback.**

The `paused` status on continuations is the only schema change. If a
v0.2.11 install reads a continuation YAML with `status: paused`, the
loader rejects it with `ContinuationCorrupt`. If you have paused
continuations and want to roll back, run `sov resume <task_id>` for
each before downgrading.

---

## What's next (not in this release)

The compaction summary noted these as candidates for future work, all
deferred:

- Continuation alias TTL / GC (current implementation is forever).
- Dream session "fork" (branch a new dream from a cycle's state).
- Project diff archive (keep prior snapshots for diff-of-diff).
- Inline atomize idempotency check (currently rebuilds; could skip).

None of these are blockers for shipping v0.2.12.

---

*With ♡ from a careful build session that respects v0.2.11's audit-driven
discipline. Every line had a reason; every reason is in the docs.*
