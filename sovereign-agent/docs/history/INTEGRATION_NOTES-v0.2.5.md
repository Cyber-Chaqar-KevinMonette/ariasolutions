# Integration Notes · v0.2.5

**Drop-in replacement for v0.2.3 / v0.2.4.** No flag renames, no breaking
behavior changes, no manual code edits required.

This document tells you exactly what to do, in order, with a rollback path
at the end.

---

## TL;DR

```bash
# 1. Backup what you have
mv ~/AA-Erebo/sovereign-agent-v0.2.1 ~/AA-Erebo/sovereign-agent-v0.2.4-backup

# 2. Extract v0.2.5
cd ~/AA-Erebo
tar -xzf sovereign-agent-v0.2.5.tar.gz
ln -sf sovereign-agent-v0.2.5 sovereign-agent-current  # if you use a symlink

# 3. Reinstall
cd sovereign-agent-v0.2.5/sovereign-agent
pip install -e . --break-system-packages

# 4. Verify
sovereign --version           # expect: sovereign-agent 0.2.5
sovereign doctor              # all PASS except possibly Ollama-related
python -m pytest tests/ -q    # expect: 178 passed

# 5. Your data is untouched
sovereign continuations list  # empty (new feature, no prior continuations)
sovereign backlog list        # whatever was in your backlog still there
sovereign events -n 10        # event history preserved
```

That's it. systemd units, config files, `secret.key`, `events.jsonl`,
`atoms.db`, `backlog.yaml` — all untouched. Nothing migrates.

---

## What's in the bundle

```
sovereign-agent-v0.2.5/sovereign-agent/
├── CHANGELOG.md
├── CHANGELOG-v0.2.4.md         (preserved from prior version)
├── CHANGELOG-v0.2.5.md         (NEW — this release)
├── COMMANDS.md                 (preserved from v0.2.4 — still accurate)
├── README.md                   (preserved — still accurate)
├── RUNBOOK.md                  (preserved — still accurate)
├── INTEGRATION_NOTES-v0.2.5.md (this file)
├── pyproject.toml              (version 0.2.5)
├── scripts/
│   ├── sovereign-agent.service           (preserved, untouched)
│   ├── sovereign-agent-seal.service      (preserved, untouched)
│   ├── sovereign-agent-seal.timer        (preserved, untouched)
│   └── sovereign-continue-loop.sh        (NEW — re-trigger driver)
├── sql/                        (preserved, untouched)
├── src/sovereign_agent/
│   ├── __init__.py             (version bumped → 0.2.5)
│   ├── cli.py                  (REWRITTEN — full operator-grade CLI)
│   ├── config.py               (one-line addition: continuations_dir path)
│   ├── continuation.py         (NEW — re-trigger state)
│   ├── continue_runner.py      (NEW — single-step executor)
│   ├── planners/               (NEW — pure-Python decomposition)
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── inventory.py
│   │   └── read_files.py
│   ├── (every other module)    (UNCHANGED)
└── tests/
    ├── test_cli.py             (NEW — 52 CLI tests)
    ├── test_continuation.py    (NEW — 24 store tests)
    ├── test_planners.py        (NEW — 14 planner tests)
    └── (every other test file) (UNCHANGED)
```

---

## What changed (file-by-file)

### `src/sovereign_agent/cli.py` — FULL REWRITE

Every v0.2.4 command preserved with same flags. Added: `--version`, `--json`,
`--quiet`, `--verbose`, `--no-color`, `--config-dir`, `--data-dir`, plus new
commands `plan`, `continue`, `continuations`, `config`, expanded `backlog`,
expanded `approvals`, `events --follow`, `run --dry-run`, `busy --once /
--max-tasks`. Plus pre-flight checks and stable exit codes.

### `src/sovereign_agent/config.py` — ONE-LINE ADDITION

Added `continuations_dir` property (`<data_dir>/continuations`) and ensured
it gets created in `Paths.ensure()`. Everything else unchanged.

### `src/sovereign_agent/__init__.py` — VERSION BUMP

`__version__ = "0.2.5"` (was `"0.2.3"`).

### `pyproject.toml` — VERSION BUMP

`version = "0.2.5"` (was `"0.2.3"`).

### Everything else: UNTOUCHED

The safety story (loop, mode_controller, authority, pathguard, approval,
events, seal, code_gate, vram, ollama_client, protocol_zero, reflector,
db, tools/, memory/, sql/, the systemd units) — all bit-identical to v0.2.4.

---

## Verification procedure

After installing, run this. It takes about 30 seconds.

```bash
cd ~/AA-Erebo/sovereign-agent-v0.2.5/sovereign-agent

# 1. Tests
python -m pytest tests/ -q
# EXPECTED: 178 passed in ~12s

# 2. Version
sovereign --version
# EXPECTED: sovereign-agent 0.2.5

# 3. Doctor
sovereign doctor
# EXPECTED: all PASS except possibly Ollama (depending on whether it's running)
# WARN on Ollama is fine if you don't have it running RIGHT NOW.

# 4. Config visible
sovereign --json config | python3 -m json.tool | head -20
# EXPECTED: parseable JSON with paths, models, ollama_host

# 5. Pre-flight refusals work
unset SOVEREIGN_HOME  # if you set it
mkdir -p /tmp/sa-test/{cfg,data}
sovereign --config-dir /tmp/sa-test/cfg --data-dir /tmp/sa-test/data run "test"
echo "rc=$?"
# EXPECTED: "✗ agent is not initialized" / rc=4

# 6. Plan workflow (no Ollama needed for this test)
mkdir -p /tmp/sa-test/corpus
echo "test content" > /tmp/sa-test/corpus/sample.md

sovereign --config-dir /tmp/sa-test/cfg --data-dir /tmp/sa-test/data init
sovereign --config-dir /tmp/sa-test/cfg --data-dir /tmp/sa-test/data \
    plan inventory \
    --root /tmp/sa-test/corpus \
    --output /tmp/sa-test/INVENTORY.txt \
    --pattern '*.md' \
    --dry-run
# EXPECTED: shows 1 step, doesn't write anything

sovereign --config-dir /tmp/sa-test/cfg --data-dir /tmp/sa-test/data \
    plan inventory \
    --root /tmp/sa-test/corpus \
    --output /tmp/sa-test/INVENTORY.txt \
    --pattern '*.md'
# EXPECTED: creates a continuation, prints task_id

sovereign --config-dir /tmp/sa-test/cfg --data-dir /tmp/sa-test/data continuations list
# EXPECTED: shows the continuation, status=planned, progress=0/1

# Cleanup
rm -rf /tmp/sa-test
```

If any step deviates from EXPECTED, halt and tell me what diverged.

---

## Real-world workflow: Genesis-Seeds inventory

This is what the re-trigger architecture was built for. Each step is one
file, one summary line, one tool call. Memory accumulates across steps.

```bash
# 1. Plan (no model invocation; pure Python)
sovereign plan inventory \
    --root ~/AA-Erebo/Genesis-Seeds/ConsiderableStartingpoint \
    --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory.txt \
    --pattern '*.md' --pattern '*.txt'

# Note the task_id printed — looks like cont-01J9...

# 2. Drive it (each iteration = fresh process, ONE file's worth of context)
~/AA-Erebo/sovereign-agent-v0.2.5/sovereign-agent/scripts/sovereign-continue-loop.sh \
    cont-01J9...

# Or step manually for inspection:
sovereign continue cont-01J9...      # rc=0 step OK, rc=8 drained
sovereign continuations show cont-01J9...   # see progress

# 3. Halt anytime; resume anytime
sovereign halt --reason "lunch"
# (continuation file persists; loop will exit cleanly when it next checks)
sovereign disarm
~/AA-Erebo/sovereign-agent-v0.2.5/sovereign-agent/scripts/sovereign-continue-loop.sh \
    cont-01J9...   # picks up exactly where it left off
```

Per-step budget defaults are tight (`--max-iter 5`, `--max-wall 120s`,
`--max-tokens 20000`). One file's worth of context. If a particular step
needs more, raise the per-step limits with flags on `sovereign continue`,
or replan with smaller scope.

---

## systemd integration (unchanged)

Your existing unit invocation `sovereign busy --cooldown 5` continues to
work identically. v0.2.5 added `--once` and `--max-tasks` as ADDITIVE
flags; the unbounded-drain default with `--cooldown` is the same code path
as v0.2.4.

If you want to add a re-trigger systemd timer (optional, advanced):

```ini
# ~/.config/systemd/user/sovereign-continue.service
[Unit]
Description=Sovereign continuation step
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/sovereign continue %i
SuccessExitStatus=0 8

# ~/.config/systemd/user/sovereign-continue.timer
[Unit]
Description=Drive a sovereign continuation every 30s

[Timer]
OnUnitActiveSec=30s
Unit=sovereign-continue@%i.service

[Install]
WantedBy=timers.target
```

`SuccessExitStatus=0 8` is the key — exit 8 means "drained," which is
success, not failure. Don't restart the timer in that case.

---

## Rollback (≤ 3 steps)

If anything goes wrong:

```bash
# 1. Rename v0.2.5 out of the way
cd ~/AA-Erebo
mv sovereign-agent-v0.2.5 sovereign-agent-v0.2.5-failed

# 2. Restore the v0.2.4 backup
mv sovereign-agent-v0.2.4-backup sovereign-agent-v0.2.1
# (keeping the original v0.2.1 directory name your scripts may reference)

# 3. Reinstall
cd sovereign-agent-v0.2.1/sovereign-agent
pip install -e . --break-system-packages
sovereign --version  # back to 0.2.3
```

Your data (`~/.local/share/sovereign-agent/`) is untouched throughout —
the rollback only swaps the code. Continuations created under v0.2.5
remain on disk; v0.2.4 simply doesn't know about them. They'll still be
there if you re-upgrade later.

---

## Known limitations

1. **`sovereign continue` requires Ollama up.** The pre-flight check
   refuses with rc=5 if Ollama isn't reachable. This is by design — running
   a step without the model is wasted work. If you want to inspect a
   continuation without invoking the model, use `sovereign continuations
   show <id>` or `sovereign continue --dry-run` (NOT YET — see roadmap).

2. **Per-step budgets are conservative.** Defaults: 5 iter, 120s wall,
   20k tokens. Tune per-invocation with `--max-iter`, `--max-wall`,
   `--max-tokens`. The continuation file records actual usage, so you can
   see whether you're hitting the cap.

3. **Step-rendering is planner-specific.** The two shipped planners cover
   the common cases (one file → one summary, one file → one memory atom).
   For richer decompositions (e.g., distillation chains, hierarchical
   plans), write a new planner under `src/sovereign_agent/planners/` and
   register it. Contract is small: subclass `Planner`, implement `.plan()`
   and `.render_step()`, register in `planners/__init__.py::REGISTRY`.

4. **Continuation lock is advisory.** Only respected by code that goes
   through `ContinuationStore`. Don't hand-edit a `.yaml` file while a
   runner holds it. The atomic-write design means hand-edits between
   runs are safe.

---

## What's next (not in this release)

- `sovereign continue --dry-run` — render the next step's goal without
  invoking the model. Useful for preview/audit.
- More planners: distill-chain, hierarchical-plan, pdf-corpus.
- A `sovereign continuations resume <task_id>` that requeues poisoned
  steps with relaxed budgets.
- Integration with the backlog so `sovereign busy` can drain continuations
  in addition to backlog tasks.

These are roadmap items. Tell me which matter most after you've used
v0.2.5 enough to know.

---

## When you've integrated

Run the end-to-end smoke test in **Verification procedure** above. If
all six steps pass, the integration is solid. Then queue your real corpus.

If any step deviates: halt, send me the divergent output, we fix.
