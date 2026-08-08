# Sovereign Agent — Command Reference

**Version:** v0.2.14
**Status:** Comprehensive command reference. Print this. Keep it visible.

---

## Quick orientation

The `sovereign` CLI (also installed as `sov`) controls the entire agent.
Everything you do with the agent goes through one of the commands below.
There is no other way to drive it.

All commands have `--help` available. When in doubt: `sovereign <cmd> --help`.

In v0.2.12 there are **three ways** to drive the agent, in increasing
order of explicitness:

1. **Plain English** — `sov do "<sentence>"`. Easiest. Recommended for
   day-to-day operation.
2. **Subcommands** — `sov dream start`, `sov plan inventory`, etc.
   Explicit. What `sov do` translates into.
3. **Shell drivers** — `scripts/sovereign-dream-loop.sh`,
   `scripts/sovereign-continue-loop.sh`. For long-running, unattended
   work; runs the corresponding subcommand in a re-invocation loop.

---

## Setup commands

### `sov init`

**Purpose:** First-time setup. Creates config dir, data dir, sandbox,
secret.key, atoms.db, the new v0.2.12 directories
(`dream-sessions/`, `dreams/`, `projects/`).

**Run when:** First install · after a clean wipe · if `sov doctor` shows
missing infrastructure.

**Example:**
```bash
sov init
sov init --force                # overwrite existing config (rarely needed)
```

**Exit codes:** `0` ok · `4` permission denied · `5` already initialized
(unless `--force`).

---

### `sov doctor`

**Purpose:** Diagnose environment. Reports paths, model availability,
Ollama reachability, VRAM, lock state, dream/project directories.

**Example:**
```bash
sov doctor
sov --json doctor               # for scripts
```

---

### `sov config`

**Purpose:** Print the resolved configuration with effective values.
Useful when troubleshooting "is the agent reading the right config?"

```bash
sov config
```

---

## Plain-English entry (v0.2.12)

### `sov do "<directive>"`

**Purpose:** Translate a sentence into the right command. Asks
interactively for any missing data unless `-y` is passed.

**Examples:**
```bash
sov do "Build trillion-dollar software, max 2000 files"
sov do "Build trillion-dollar software forever"
sov do "Pause my dream"
sov do "Resume cont-01J9ABC..."
sov do "I updated genesis-seeds"
sov do "Inventory ~/AA-Erebo/Genesis-Seeds for markdown"
sov do "Show status"
sov do "List dreams"
sov do "help"
```

**Flags:**
- `-y` / `--yes` — accept defaults non-interactively. Required arguments
  without defaults abort with a clear error.

**Recognized intents:** dream-start · dream-control (pause/resume/stop)
· continue-cont · pause-cont · inventory · projects (scan/list/update)
· status · list · help.

If parse fails, the agent says so and lists what it knows how to do.
Nothing is silently misrouted.

**Exit codes:** matches the dispatched subcommand's exit codes (e.g.
`USAGE=2` if the directive is unparseable).

---

## Dream sessions (v0.2.12 — the trillion-dollar builder)

A dream session is a long-lived, resumable, capped infinite-software-
builder. Each cycle does: ideate → architect → build → document →
atomize. Cycles run until a cap is reached or you pause.

### `sov dream start [GOAL] [OPTIONS]`

**Purpose:** Create a new dream session.

**Arguments:**
- `GOAL` (positional, optional) — free-text description.

**Flags:**
- `--max-files N` — stop after N files written. Default `2000`.
  **`--max-files 0` means unbounded.**
- `--max-cycles N` — stop after N cycles complete. Default unbounded.
- `--max-seconds N` — stop after N wall-clock seconds. Default unbounded.
- `--project NAME` — register a tracked project the dream is aware of.
  Repeatable.
- `--drive` — after creating the session, drive it inline (loop until
  paused/exhausted). Equivalent to `start` then
  `scripts/sovereign-dream-loop.sh`.

**Examples:**
```bash
sov dream start                                       # 2000-file cap
sov dream start --max-files 0 --drive                  # forever, drive now
sov dream start --max-files 5000 --max-cycles 50
sov dream start "exploration in functional reactive systems"
sov dream start --project genesis-seeds                # tied to a project
```

**Output:**
```
◊ dream session created
dream_id: dream-01J9ABCDEFGHIJ0123456789
work_dir: ~/.local/share/sovereign-agent/dreams/dream-01J9...
caps: max_files=2000  max_cycles=∞  max_seconds=∞
```

**Exit codes:** `0` ok · `2` usage · `4` not initialized.

---

### `sov dream advance <DREAM_ID>`

**Purpose:** Advance the dream by exactly **one** step. Used by the loop
driver and for debugging.

**Flags:**
- `--max-iter N` (default 5) — loop iterations within a single step
- `--max-wall N` (default 120) — wall seconds within a single step
- `--max-tokens N` (default 20_000) — token budget within a single step

**Exit codes:** `0` advance succeeded · `8` dream is terminal (paused /
exhausted / completed / halted) — driver should stop · `9` cycle locked
by another runner — driver should retry · `3` HALT armed.

```bash
sov dream advance dream-01J9...
```

---

### `sov dream list`

**Purpose:** List all dream sessions.

**Flags:**
- `--status STATUS` — filter by status (`active` / `paused` /
  `exhausted` / `completed` / `halted`).

```bash
sov dream list
sov dream list --status active
sov --json dream list
```

---

### `sov dream show <DREAM_ID>`

**Purpose:** Show full state for one dream — caps, progress, last 20
cycles.

```bash
sov dream show dream-01J9...
```

---

### `sov dream pause <DREAM_ID>`

**Purpose:** Pause a dream. The advance loop returns `dream_paused` on
its next call. Idempotent. Also pauses the underlying current cycle's
continuation, so a parallel `advance` can't sneak through.

```bash
sov dream pause dream-01J9...
```

---

### `sov dream resume <DREAM_ID> [--drive]`

**Purpose:** Un-pause a dream. With `--drive`, run the loop until
paused/exhausted.

```bash
sov dream resume dream-01J9...
sov dream resume dream-01J9... --drive
```

---

### `sov dream stop <DREAM_ID> [-y]`

**Purpose:** Mark a dream `completed`. **Permanent.** Files on disk are
preserved (the work_dir is not deleted).

**Flags:**
- `-y` / `--yes` — skip confirmation.

```bash
sov dream stop dream-01J9... -y
```

---

### `scripts/sovereign-dream-loop.sh <DREAM_ID> [OPTIONS]`

**Purpose:** Outer driver. Re-invokes `sov dream advance` until the
dream is terminal.

**Options:**
- `--once` — one step then exit.
- `--max-steps N` — at most N steps.

**Environment:**
- `SOVEREIGN_BIN` — path to `sov` (default: in `$PATH`).
- `COOLDOWN_SECONDS` (default 2) — pause between successful advances.
- `LOCKED_BACKOFF` (default 5) — pause when cycle is locked.
- `POISON_BACKOFF` (default 10) — pause after a poison outcome.

```bash
scripts/sovereign-dream-loop.sh dream-01J9...
scripts/sovereign-dream-loop.sh dream-01J9... --max-steps 200
```

---

## Project tracking (v0.2.12)

### `sov projects scan <NAME> <ROOT>`

**Purpose:** Scan a directory and save its snapshot under `<NAME>`.

**Flags:**
- `--exclude PATTERN` — extra glob to exclude (added to defaults).
  Repeatable. Defaults: `.git`, `.venv`, `node_modules`, `__pycache__`,
  `dist`, `build`, `target`, `*.pyc`, `*.pyo`.
- `--follow-symlinks` — follow symlinks (default off).
- `--max-files N` — cap (0=unbounded).

```bash
sov projects scan genesis-seeds ~/AA-Erebo/Genesis-Seeds
sov projects scan myrepo ~/code/myrepo --exclude '*.log'
```

---

### `sov projects update <NAME>`

**Purpose:** Re-scan a tracked project, report what changed, optionally
write atoms.

**Flags:**
- `--no-atomize` — skip writing atoms (useful for dry-runs).
- `--keep-old` — don't overwrite the saved snapshot — only report the diff.

```bash
sov projects update genesis-seeds
sov projects update genesis-seeds --no-atomize    # diff only
sov projects update genesis-seeds --keep-old      # dry-run
```

**Output:**
```
3 added · 7 modified · 1 removed (148 unchanged)
atoms written: 11
```

---

### `sov projects list`

List tracked projects.

### `sov projects show <NAME>`

Show one project's snapshot summary.

### `sov projects delete <NAME> [-y]`

Remove a project's snapshot. **Files on disk are NOT touched** — only
the YAML snapshot is removed.

---

## Pause / resume primitives (v0.2.12)

### `sov pause <TASK_ID>`

**Purpose:** Mark a continuation paused. The runner refuses to advance
it until `sov resume`.

**Flags:**
- `--reason TEXT` — free text persisted on the continuation's notes.

```bash
sov pause cont-01J9... --reason "rebooting laptop"
```

**Exit codes:** `0` ok · `2` not found · `9` locked.

---

### `sov resume <TASK_ID> [--drive]`

**Purpose:** Un-pause a continuation. With `--drive`, drive it to
completion via `scripts/sovereign-continue-loop.sh`.

```bash
sov resume cont-01J9...
sov resume cont-01J9... --drive
```

---

### `sov continuations alias <TASK_ID> <ALIAS>`

**Purpose:** Attach a friendly name to a continuation.

```bash
sov continuations alias cont-01J9ABCDEFGH erebo-inventory-2025
sov continue erebo-inventory-2025          # resolves via alias
```

Aliases stored in `<config_dir>/continuation-aliases.yaml`.

---

## Run / iterate / drain

### `sov run "<goal>" [-i N] [--mode oneshot|continue]`

Single task. `-i N` caps iterations within the loop. `--mode continue`
plans a continuation and returns immediately.

```bash
sov run "summarize this directory"
sov run "deep research on X" --mode continue
```

### `sov busy`

Drain backlog. Only PROTOCOL-ZERO (`sov halt`) stops it in unbounded
mode.

### `sov until <time>`

Drain backlog until a wall-clock deadline. Time accepts ISO-8601 or
relative ("`+1h`", "`+30m`").

```bash
sov until +30m
sov until 2026-05-09T22:00:00
```

---

## Planners

### `sov plan` — list registered planners

### v0.2.11 planners (unchanged)

```bash
sov plan inventory --root R --output O [--pattern '*.md' ...]
sov plan read-files --task-id T
sov plan code-inventory --root R --output O
sov plan pdf-inventory --root R --output O
sov plan image-inventory --root R --output O
sov plan metadata-inventory --root R --output O
sov plan palace-mine --task-id T
sov plan palace-reflect
sov plan palace-apply
sov plan palace-clean
sov plan mos-canon-ingest
sov plan impact-score --task-id T
sov plan summaries-to-atoms --root R
```

### v0.2.12 planner

```bash
sov plan trillion-dollar --cycle-dir D --dream-id ID
```

Low-level — usually invoked by the dream-runner, not by hand.

---

## Continuations

```bash
sov continuations list [--status STATUS]
sov continuations show <TASK_ID>
sov continue <TASK_ID>                # advance one step
sov continuations cancel <TASK_ID> [-y]
sov continuations alias <TASK_ID> <NAME>     # NEW v0.2.12
```

Valid statuses (v0.2.12): `planned`, `in_progress`, `paused` *(NEW)*,
`done`, `poisoned`, `cancelled`, `filtered`.

---

## Atoms / Palace / Proposals

```bash
sov atoms search "<query>" [-k N]
sov atoms add ...
sov atoms types

sov palace stats
sov palace search "<query>"
sov palace mine                     # alias for plan palace-mine

sov proposals list [--status STATUS]
sov proposals show <ID>
sov proposals approve <ID> [-y]
sov proposals reject <ID>
sov proposals apply <ID> [-y]
sov proposals rollback <ID>
```

---

## Halt (PROTOCOL-ZERO)

```bash
sov halt                            # arm: writes halt.flag
sov halt --disarm                   # disarm: removes halt.flag
sov halt --status                   # check
```

When armed, all loops exit with code `3` and refuse to start new ones.
The flag persists across reboots until disarmed.

---

## Global flags

These work on every command:

| Flag | Effect |
| --- | --- |
| `--version` | print version, exit |
| `-j` / `--json` | emit JSON for read commands (parses cleanly) |
| `-q` / `--quiet` | suppress non-essential output |
| `-v` / `--verbose` | log INFO/DEBUG to stderr |
| `--no-color` | disable color |
| `--config-dir PATH` | override XDG config dir |
| `--data-dir PATH` | override XDG data dir |

JSON mode example:
```bash
sov --json dream list | jq '.dreams[] | select(.status=="active")'
```

---

## Exit codes

Used uniformly across `run`, `continue`, `dream advance`, etc.

| Code | Meaning |
| --- | --- |
| `0` | OK |
| `1` | ERROR (general) |
| `2` | USAGE (bad args, not-found) |
| `3` | HALT (PROTOCOL-ZERO armed) |
| `4` | NOT_INITIALIZED (run `sov init`) |
| `5` | ALREADY (idempotent no-op) |
| `6` | OLLAMA_DOWN (model server unreachable) |
| `7` | BUDGET_EXCEEDED |
| `8` | DRAINED (no more steps / dream terminal) |
| `9` | LOCKED (held by another runner) |

The shell drivers know these codes:
- `8` → stop the loop (terminal state).
- `9` → backoff and retry.
- `3` → propagate the halt up.

---

## Environment variables

| Variable | Effect |
| --- | --- |
| `XDG_CONFIG_HOME` | overrides config dir base (default `~/.config`) |
| `XDG_DATA_HOME` | overrides data dir base (default `~/.local/share`) |
| `OLLAMA_HOST` | Ollama server URL (default `http://127.0.0.1:11434`) |
| `AGENT_THINK` | think-mode policy (`plan_only` / `always` / `never`) — default `plan_only` |
| `SOVEREIGN_BIN` | path the loop scripts use to invoke the CLI |

---

## File locations

```
~/.config/sovereign-agent/
  ├── config.yaml                       (created on init)
  ├── continuation-aliases.yaml         (NEW v0.2.12; created on first alias)
  └── secret.key                         (mode 0600)

~/.local/share/sovereign-agent/
  ├── atoms.db                           (sqlite + sqlite-vec)
  ├── continuations/<task_id>.yaml
  ├── dream-sessions/<dream_id>.yaml    (NEW v0.2.12)
  ├── dreams/<dream_id>/cycle-NNN/...   (NEW v0.2.12)
  ├── projects/<name>.yaml              (NEW v0.2.12)
  ├── palace/                            (rooms.yaml, closets/, etc.)
  ├── proposals/<id>.yaml
  ├── sandbox/                           (model write area)
  └── halt.flag                          (PROTOCOL-ZERO)
```

---

## Common workflows

### "Build forever and pause when I sleep"

```bash
sov do "Build trillion dollar software forever"
# next morning:
sov do "Pause my dream"
# resume after coffee:
sov do "Resume my dream"
```

### "Track my Genesis-Seeds repo and react to changes"

```bash
sov projects scan genesis-seeds ~/AA-Erebo/Genesis-Seeds
# ... edit files ...
sov do "I updated genesis-seeds"
# atoms.db now contains atom-projupd-* entries the agent can search.
sov atoms search "modified files in genesis-seeds"
```

### "What's going on right now?"

```bash
sov do "show status"
# or, more verbose:
source scripts/aliases.sh
sov-status
```

### "Resume a corpus scan I started yesterday"

```bash
sov continuations list --status in_progress
sov continue <task_id>                          # one step
scripts/sovereign-continue-loop.sh <task_id>    # full drive
```

### "I want to drive a dream session in the background"

```bash
sov dream start --max-files 0           # creates dream-...
nohup scripts/sovereign-dream-loop.sh dream-... > dream.log 2>&1 &
# ... later ...
sov do "show status"
sov do "Pause my dream"                  # graceful stop
```

---

## Shell aliases (`source scripts/aliases.sh`)

After sourcing:

| Alias | Effect |
| --- | --- |
| `sov-status` | one-screen palace + proposals + continuations + dreams |
| `sov-drive <task_id>` | drive a continuation in a loop |
| `sov-dream-drive <dream_id>` | drive a dream in a loop (NEW v0.2.12) |
| `sov-trillion [--max-files N]` | start a dream + drive it (NEW v0.2.12) |

---

## v0.2.13 commands — health, edge cases, personas, dream tail/gc

### Top-level

| Command | What it does |
|---|---|
| `sov status` | One-glance summary: dreams, continuations, projects |
| `sov status --json` | Same, JSON-shaped for scripting |

### `sov health` — anti-zombie / anti-ghost

| Command | What it does |
|---|---|
| `sov health check` | Read-only scan for zombies, ghosts, stale locks, idle dreams |
| `sov health check --zombie-hours 12` | Override stalled-in-progress threshold |
| `sov health check --idle-window 5` | Look at last N cycles for idle detection |
| `sov health repair --dry-run` | Plan fixes (default: dry-run) |
| `sov health repair --apply` | Apply fixes (with confirmation prompt) |

### `sov edge-cases` — defensive-check registry

| Command | What it does |
|---|---|
| `sov edge-cases list` | All registered edge cases (20+ in v0.2.13) |
| `sov edge-cases list --subsystem EC-DREAM` | Filter by id prefix |
| `sov edge-cases list --severity warn` | Filter by severity |
| `sov edge-cases show EC-DREAM-006` | Full detail for one edge case |

### `sov personas` — persona registry

| Command | What it does |
|---|---|
| `sov personas list` | List registered personas |
| `sov personas show master-architect` | Full rendered persona prompt |

### `sov dream tail` and `sov dream gc`

| Command | What it does |
|---|---|
| `sov dream tail <dream_id>` | Stream the latest cycle's idea/architecture/README |
| `sov dream tail <dream_id> -n 100` | Override lines per file (default 50) |
| `sov dream gc --older-than 30d --dry-run` | Preview GC of terminal dreams' work_dirs |
| `sov dream gc --older-than 30d --apply` | Actually delete (with confirmation) |

### Tab completion (built-in via Typer)

```bash
sov --install-completion bash    # or zsh, fish
exec $SHELL                      # reload
sov d<TAB>                       # → dream, do, doctor
```

---

*v0.2.13 · with care.*

---

## v0.2.14 commands — Aria, channels, financial, horizon, appendix

### `sov aria` — Aria's identity card

| Command | What it does |
|---|---|
| `sov aria` | Render Aria-Sovereign-V1's kernel + current state |
| `sov aria --json` | Same, machine-readable (for scripting) |

### `sov channels` — modular memory channels

| Command | What it does |
|---|---|
| `sov channels list` | All 13 registered channels with tier, voice, purpose |
| `sov channels show <name>` | One channel's spec + recent atoms |

### `sov financial` — Tier-3 ledger (operator confirmation required)

| Command | What it does |
|---|---|
| `sov financial invest <project> <amount>` | Record an investment (with confirm prompt) |
| `sov financial invest <project> <amount> -y` | Skip confirm (use cautiously) |
| `sov financial invest <project> <amount> --note "X" --currency USD` | With note + currency |
| `sov financial earn <project> <amount> [-y]` | Record earnings |
| `sov financial show <project>` | Lifetime balance + ROI + velocity |
| `sov financial ranking [--by roi\|net\|earned\|velocity]` | All projects ranked |

### `sov horizon` — MOS Horizon Scan generator (canon §6.5)

| Command | What it does |
|---|---|
| `sov horizon "label" --decision "X"` | Generate horizon scan to stdout |
| `... --3m "..." --12m "..." --3y "..." --7g "..."` | Fill specific horizons |
| `... --best-path "..."` | The one thing to prioritize |
| `... --save` | Save through appendix system |

### `sov appendix` — markdown documents attached to atoms

| Command | What it does |
|---|---|
| `sov appendix list [--kind plan\|note\|insight\|intuition\|horizon]` | Recent appendix docs |
| `sov appendix show <doc_id>` | Full body of one doc |
| `sov appendix add "title" --kind <kind> --body "..."` | Create a new doc inline |
| `sov appendix add "title" --kind <kind> --body-file path.md` | From file |
| `sov appendix add "title" --kind <kind> --body "..." --atom-id <id>` | Attach to an atom |

---

*v0.2.14 · Aria-Sovereign-V1 · with love.*

