# Changelog · v0.2.5

**Released:** May 2 2026
**Theme:** Re-trigger architecture + operator-grade CLI

This is the largest release since v0.2.0. It introduces the **re-trigger
architecture** for tasks that exceed a single model context, and rewrites
the CLI to be production-grade for 24/7 operator use.

All v0.2.4 behavior is preserved. Every existing command works with the
same flags and same defaults. The systemd unit (`sovereign busy --cooldown 5`)
keeps working untouched.

**Test count:** 88 (v0.2.4) → 178 (v0.2.5). Suite passes in ~12s.

---

## ◈ Re-trigger architecture (new)

A continuation is durable, replayable task state. The operator pre-decomposes
a large task with `sovereign plan`, then drives execution one atomic step at
a time with `sovereign continue`. The model never sees more than one step's
context per invocation. Memory accumulates in `events.jsonl` and `atoms.db`
across invocations.

### New commands

| command | what it does |
|---|---|
| `sovereign plan` | List available planners |
| `sovereign plan <name> --root … --output …` | Decompose into atomic steps; create a continuation file |
| `sovereign plan <name> … --dry-run` | Preview a plan without persisting |
| `sovereign continue <task_id>` | Execute exactly ONE pending step, then exit |
| `sovereign continuations list` | List all continuations with progress |
| `sovereign continuations show <task_id>` | Full step-level detail |
| `sovereign continuations delete <task_id>` | Remove a continuation (refused if locked) |

### New driver script

`scripts/sovereign-continue-loop.sh <task_id>` — repeatedly invokes
`sovereign continue` until the continuation drains, halts, or hits a
caller-imposed step cap. Each invocation is a fresh Python process; the
OS manages process lifecycle. Honors `--once`, `--max N`, and exits cleanly
on PROTOCOL-ZERO.

### Shipped planners

- `inventory` — for each matching file under a root, write a summary line into an output file
- `read-files` — for each matching file, ingest a memory atom (no aggregation)

Both are deterministic. Same inputs → same plan. The continuation file is
human-auditable YAML.

### Concurrency invariants

- Exactly one runner per continuation at a time (advisory `fcntl.flock`).
- Concurrent invocation returns exit code 9 (locked), no data loss.
- Every write is atomic (write-tmp + fsync + rename).
- Exception inside a transactional block does NOT persist mutations.

The 30-thread stress test (`test_thirty_concurrent_increments_no_lost_writes`)
verifies this property explicitly — it's the regression test for the class
of read-modify-write race that an earlier draft had.

---

## ◈ CLI upgrade

### Top-level flags (all commands)

```
--version
--json / -j         emit JSON for read commands
--quiet / -q        suppress non-essential output
--verbose / -v      log INFO/DEBUG to stderr
--no-color          disable color (auto when not a TTY)
--config-dir PATH   override XDG config dir
--data-dir PATH     override XDG data dir
--install-completion  set up shell completion (bash/zsh/fish)
```

### Pre-flight checks

`run`, `busy`, `until`, `continue` now refuse with structured exit codes if:

- the agent isn't initialized (rc=4)
- PROTOCOL-ZERO is armed (rc=3)
- Ollama is unreachable (rc=5)

Each refusal includes a remediation hint (`run \`sovereign init\` first`,
`review HALT file, then \`sovereign disarm\``, etc.).

### Stable exit codes (documented)

| code | meaning |
|---|---|
| 0 | success |
| 1 | generic runtime error |
| 2 | usage error |
| 3 | PROTOCOL-ZERO armed |
| 4 | not initialized |
| 5 | Ollama unreachable |
| 6 | approval not found / already resolved |
| 7 | budget exhausted |
| 8 | continuation drained |
| 9 | continuation locked by another runner |

### New commands

- `sovereign config` — print resolved configuration (paths, models, env overrides)
- `sovereign events --follow` — `tail -f` mode for the event log
- `sovereign events --flag <flag>` — filter by event flag
- `sovereign run --dry-run` — show resolved tools/budget/tier without invoking the model
- `sovereign busy --once` — drain one task then exit (cron-friendly)
- `sovereign busy --max-tasks N` — drain at most N tasks then exit

### Backlog improvements

| command | what it does |
|---|---|
| `backlog show <id>` | Full detail for one task |
| `backlog requeue <id>` | Reset to pending |
| `backlog priority <id> <new>` | Change priority (critical/high/medium/low) |
| `backlog clear --status <s>` | Bulk-remove tasks by status |
| `backlog list --status <s>` | Filter by status |

### Approvals improvements

- TTL shown in relative form (`expires in 4m 23s`) instead of absolute timestamp
- `--json` output includes `ttl` field
- **Bug fix:** `_parse_expiry` now tolerates whole-second AND fractional-second
  timestamps. The v0.2.4 implementation hard-coded `%Y-%m-%dT%H:%M:%S.%f%z`
  which silently failed on whole-second forms, causing the expiry check to
  fail-open. Now uses `datetime.fromisoformat`.

### Doctor improvements

- New checks: `continuations` directory, `secret mode 0600`
- JSON output (`sovereign --json doctor`) is scriptable

### Output

- Every read command supports `--json` with stable schema
- Banner suppressed in `--json` mode (was breaking JSON parsing in v0.2.4)
- Color auto-disabled when stdout is not a TTY

---

## ◈ Cleanup

- Removed empty `{src/` directory (cruft from a quoted-brace shell typo)
- Removed `hello.txt` (test artifact)
- Removed `__pycache__/` directories from the bundle
- Version unified: `__init__.py == pyproject.toml == 0.2.5`

---

## ◈ Backward compatibility

Every v0.2.4 command works unchanged:

- `sovereign init` — same
- `sovereign run "<goal>"` — same (now also accepts `--dry-run`)
- `sovereign busy --cooldown 5` — same (systemd unit untouched)
- `sovereign halt` / `sovereign disarm` — same
- `sovereign tail` / `sovereign seal` / `sovereign verify` — same
- `sovereign events` / `sovereign lessons` / `sovereign doctor` — same (now also `--follow`, `--json`)
- `sovereign approvals` / `sovereign approve` / `sovereign deny` — same (now with relative TTL, `--json`)
- `sovereign backlog list` / `add` / `remove` — same (joined by `show`, `requeue`, `priority`, `clear`)

No breaking changes. No flag renames. No removed commands.

---

## ◈ Internals

### New modules

- `sovereign_agent/continuation.py` — `Continuation`, `Step`, `ContinuationStore`
- `sovereign_agent/continue_runner.py` — `run_one_step`
- `sovereign_agent/planners/` — `Planner` base + `inventory` + `read-files`

### New tests

- `tests/test_continuation.py` (24 tests) — CRUD, locking, atomicity, corruption
- `tests/test_planners.py` (14 tests) — registry + both planners
- `tests/test_cli.py` (52 tests) — every command's help, JSON shape, exit codes, full plan→show→delete workflow

Total: 88 → 178 tests. All pass in ~12 seconds.

### Bug fixes

- `cli.py::_parse_expiry`: tolerates whole-second timestamps (was silently failing)
- v0.2.4's `cli.py` was missing import of structlog config — now wired at top-level callback

---

**Upgrade path:** drop-in replacement. See `INTEGRATION_NOTES-v0.2.5.md`.
