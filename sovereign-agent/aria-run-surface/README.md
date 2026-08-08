# aria-run-surface

Keys round K1 — the observability core: payload-aware event rendering, red
failures, the live run strip, and the mode/breaker status-bar fields.

## The gaps (researched 2026-07-04)

- `_render_event` (app.py:2588-2624) discarded the payload for ~80 event
  types — `session-*`, `subtask-*`, `workflow-step-*` all carry rich
  payloads (titles, used/limit, done/total) that rendered as bare flags.
- Failure events (`-x`) rendered WHITE — the color chain never checked the
  suffix. `circuit-open-x`, `ingest-skip-x` scrolled past unmissed.
- No live surface answered "what is she doing right now": no run view, no
  active-mode field (the `/mode work` autonomy signal was invisible), no
  breaker state.

## The fix

- **`cockpit/run_surface.py`** (new): `render_rich_event` — a renderer
  registry per family (session/subtask/workflow-step/prompt-diet/
  ingest-skip/circuit-open/qa); unknown flags return None and fall through
  to the generic renderer byte-for-byte. `RunState` — a cross-event
  tracker (goal from `ingest-d`, subtask progress, tokens, breaker,
  outcome). Everything is derived from events.jsonl because the loop
  usually runs in a SEPARATE process — the event stream is the one honest
  cross-process window.
- **7 anchored app.py patches**: routing + rich renders at the tailer
  chokepoint; `-x` → red (before the generic matches); the 5th palette
  strip `#run-strip` ("◈ run <goal> · 2/5✓ · <current> · 8100t"); refresh
  wiring; status-bar ACTIVE MODE (dim `◈ chat` / bold magenta `◈ work`)
  + red breaker badge.
- The multi-line run PANE ships with K2's layout rows, where the vertical
  space lives — `RunState.render_pane()` is already built for it.

## Verify / Apply

```
.venv/bin/python -m pytest aria-run-surface/tests/test_patcher.py -q
./aria-run-surface/apply_run_surface.sh
```

Reversible: restore `cockpit/app.py` from the timestamped `backups/` dir
and remove `cockpit/run_surface.py`.
