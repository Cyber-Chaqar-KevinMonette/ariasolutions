# 04 — Event vocabulary

`events.jsonl` is the source of truth; `emit_event(flag, plane,
trace_id, payload)` appends atomically (<4KB lines; big payloads spill to
blobs). Suffixes: `-d` done/observed, `-x` failure (renders RED).

| Family | Meaning | Surface |
|---|---|---|
| trace-start/end-d | loop bookends | live pane |
| ingest-d | goal entered the loop | live + RunState |
| model-d / token-usage-d | model call + totals | status bar |
| tool-start-d / <tool>-d/-x | dispatch + result | live, last-tool, button pulse |
| prompt-diet-d | tools sent/registered, prompt chars | live (dim) |
| tool-paged-d | schemas attached mid-run | live |
| session-*/subtask-* | the engine lifecycle | run strip + rich lines |
| session-notes-d | queued operator messages delivered | rich line |
| scope-review-d / scope-drift-d | contract teeth | rich lines |
| work-* | file writes/edits/commands | atelier pane |
| qa-start-d / qa-d | her wondering | rich lines |
| workflow-designed-d | a draft exists | rich line |
| ingest-skip-x | corrupt event lines skipped | red |
| circuit-open-x | tool breaker opened | red + badge |
| reflect-d | a lesson written | live |

Renderers live in ONE place: `cockpit/run_surface.py` —
`render_rich_event` + `RunState`. Unknown flags fall through to the
generic color renderer. Add new families THERE.
