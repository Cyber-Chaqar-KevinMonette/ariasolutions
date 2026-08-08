# aria-atelier — Workstream A: "Aria's Atelier"

A live work-theater pane: watch every file Aria writes/edits and every
command she runs, color-coded — green=new file, yellow=edited (with a diff
excerpt), blue=command run. Kevin's own framing: "watch her work in all her
beauty."

## What this ships

`src/sovereign_agent/work_events.py` — **new file**, no tool files touched.
Rather than adding an `emit_event()` call to every file-mutation/shell tool
(`edit_file.py`, `write_file.py`, `copy_file.py`, `command_master.py`,
`runner.py`, …), this hooks the ONE existing dispatch choke point in
`loop.py` — right after `result = await tool.execute(parsed, ...)`, where
`tool_name`, the parsed `Args`, and the `ToolResult` are all already in
scope — and derives a `work-write` / `work-edit` / `work-command` event
purely from data that's already there. Recognizes: `write_file`,
`copy_file` (write); `edit_file`, `edit_in_place` (edit, with a real
`difflib` diff excerpt + added/removed line counts); `run_command`,
`run_shell`, `run_code`, `run_tests` (command). Only emits on success —
a failed edit never actually changed anything, so it stays out of a pane
whose whole point is "watch her work," not "watch her attempt things."
Best-effort throughout: never raises, never blocks the agent loop.

`src/sovereign_agent/loop.py` — 2 anchored patches: import
`maybe_emit_work_event`, call it once right after the existing
"Invariant 2: one event per action" `_record(...)` block.

`src/sovereign_agent/cockpit/app.py` — 6 anchored patches:
- CSS: `#atelier-pane` (1fr, same discipline as memory/live/inbox) +
  `#divider-4` (same discipline as divider-1/2/3).
- `compose()`: the 5th pane, right after `#inbox-pane` closes.
- `on_mount`: binds `self._atelier_log`.
- **A routing branch added to the START of the EXISTING `_render_event()`
  method**: if `ev["flag"]` starts with `work-`, delegate to a new
  `_render_work_event()` and return — every other flag falls through to
  the untouched original logic, completely unaffected.
- A new `_render_work_event()` method, colorizing by op.

## A simplification found during the actual build

The plan's own text suggested a *second* file-tailing worker
(`_tail_work_worker()`) mirroring `_tail_events_worker()`. Once building it
became clear that's unnecessary: work events land in the exact same
`events.jsonl` the cockpit already tails once a second. A second tailer
reading the same file would just double the I/O for no benefit. Instead,
the ONE existing tailer's `_render_event()` gets a routing branch at the
top — same file, same offset-tracking, different destination pane based on
the flag prefix. Simpler, and there was nothing in the plan's own
reasoning that actually required a second worker; it was just the first
design that came to mind before the choke point was fully understood.

## Tests

`tests/test_patcher.py` (11 tests) — both patch functions (loop.py, app.py)
apply cleanly against the CURRENT live files, are idempotent, all three
patched/new files compile, the work- routing branch runs before the
generic color-by-flag logic, `_render_work_event` covers all three ops, a
missing anchor raises `PatchError` (never a silent no-op).

`tests/test_atelier.py` (11 tests, staging only, shadow-copy — legitimate
pre-apply verification, never promoted) / `tests/test_atelier_live.py`
(same 11, promoted to live `tests/` after apply, plain imports, zero
`sys.modules` manipulation — the lesson learned twice already this session):
`write_file`/`edit_file`/`run_command` each emit the right event shape; a
failed tool call never emits; an unrecognized tool never emits; garbage
input never raises; the atelier pane exists and starts empty; a
`work-write` event routes to the atelier pane and leaves the "live" pane
untouched; a generic flag (`trace-start-d`) still routes to the "live"
pane exactly as before (regression guard); edit events colorize diff
lines by +/-; command events show the command string.

## Deliberately deferred (named, not silently dropped)

Per the plan's own "god-tier extensions" framing, these are noted as
follow-ups, not built now: collapsible diff entries, a per-file change
counter, a session "replay" scrub, secret redaction in diffs before they
hit the pane, an opt-in desktop notification for large/destructive edits.
No dedicated file-delete tool exists in this codebase today (deletion
happens via `edit_file` with `new_str=""`, or via `run_command`/`run_shell`
invoking `rm`) — so there's no separate "delete" op color; a deletion
via `edit_file` shows as a yellow edit with removed lines, which is
honest, not a bug.

Reversible: restore `loop.py` + `app.py` from the backup, delete
`work_events.py`.
