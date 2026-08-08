# aria-apply-queue — cockpit-driven, durable apply queue + safe sequencer + quarantine

> Kevin's flow: *"select modules in the cockpit → it writes a queue file that sequences applications
> safely → close the cockpit → safely apply selected → successes leave the queue; rollbacks go to
> quarantine for evaluation until fixed → watch progress in the terminal + a notification at the end."*
> This module is exactly that. Propose-only / reversible / staged.

## Why
You can't apply while the cockpit runs — that would mutate live `src/` beneath a running process
(CLAUDE.md doctrine). So applying becomes two phases: **select inside the cockpit** (writes a durable
queue file, no mutation), then **drain the queue after closing it** (each module through the existing
`safe_apply.sh` guards + auto-rollback). Nothing is lost: a rollback routes to a reviewable quarantine.

## Payload
- `src/sovereign_agent/apply_queue/store.py` — `ApplyQueueStore` (durable append-only `queue.ndjson`
  + live `queue.current.json` view) and `QuarantineRegistry` (one JSON per failed module). Atomic
  writes mirror `rollback.RollbackStore`; dependency order mirrors `apply_queue.sh`'s `PRIORITY[]`.
- `src/sovereign_agent/apply_queue/__main__.py` — CLI: `status · list · enqueue · next · mark · clear · quarantine`.
- `src/sovereign_agent/cockpit/apply_queue_screen.py` — `ApplyQueueScreen` (Ctrl+Shift+A): multi-select
  pending modules → "Queue selected" writes the durable queue. Writes the queue file only, never `src/`.
- `scripts/apply_queue_run.sh` (installed by apply) — the **safe sequencer**: drains the queue through
  `safe_apply.sh`, prints `▸ [n/N] slug …`, removes successes, quarantines rollbacks, and fires a
  desktop notification (`N applied · M quarantined`) at the end. `--dry-run` previews the plan + gate.

## What apply wires
1. Copies the `apply_queue/` package + `apply_queue_screen.py` into live `src/`.
2. Installs `scripts/apply_queue_run.sh`.
3. Wires the cockpit screen into `cockpit/app.py` — three anchored, idempotent edits (guarded import,
   `Ctrl+Shift+A` binding, `action_apply_queue`). Any missing anchor is **skipped, never fatal** — the
   CLI + sequencer work regardless. All edits backed up under `aria-apply-queue/backups/<ts>`.

## Use
```bash
# in the cockpit:  Ctrl+Shift+A → select modules → "Queue selected" → close cockpit
./scripts/apply_queue_run.sh                 # drain the queue safely (quarantines rollbacks)
./scripts/apply_queue_run.sh --dry-run       # preview plan + Tribunal verdict, mutate nothing

# or drive it from the CLI:
.venv/bin/python -m sovereign_agent.apply_queue enqueue aria-foo aria-bar
.venv/bin/python -m sovereign_agent.apply_queue status
.venv/bin/python -m sovereign_agent.apply_queue quarantine list
```

## Verify / Apply
```bash
./scripts/verify_module.sh aria-apply-queue     # before apply (read-only)
./aria-apply-queue/apply_apply_queue.sh         # cockpit stopped
```

## Relationship to D (aria-path-sentinel)
The sequencer applies through `safe_apply.sh`, whose **step-0 gate** is the path sentinel (D). So a
module carrying a false/test path is blocked before it can apply — the queue and the gate compose.

## Evolved since staging (2026-08-02)

Enhanced live, applied directly (not through this module's own apply script — those patches predate
these additions and don't cover them):
- `_pending_modules()` now imports the shared `sovereign_agent.staged_status.pending_modules()` instead
  of its own copy of the detection heuristic (was the 3rd independent copy of the same bug fixed
  elsewhere this session).
- Fixed `action_apply_queue()`'s `repo_root` computation — was `parents[3]`, pointed one directory above
  the actual repo, so the screen had always shown **zero pending modules** regardless of real state.
  Caught by writing a real test, not by inspection.
- `Ctrl+Shift+A` is now `show=True` (was hidden from the footer) + a `📋 apply queue` palette entry —
  Kevin asked for a visible front-end button, this was it.
- New "Queue & Quit" button: enqueues the selection, then closes the cockpit and hands off via
  `os.execvp` (in `cockpit/app.py`'s `run()`) directly into `scripts/apply_queue_run.sh` — same
  terminal, same PID, no separate manual command. `os.execvp` matters here specifically because
  `safe_apply.sh`'s cockpit-running guard (`pgrep -f "sovereign cockpit"`) would otherwise still match
  the parent CLI process if it were merely spawned as a child.
- `#aq-footer` is now `dock: bottom` — at the default 80×24 terminal size the footer (now 4 buttons) was
  rendering partially below the visible screen, making it unclickable. Found via test, not visually.
- The cockpit status bar now shows a live `🛠 N staged` / `✓ N queued` badge (5s refresh, same
  background-thread pass as the sentinel/system metrics — never a synchronous rescan) so the pending
  backlog can't silently grow unseen the way it did before this session's 31-module audit.
