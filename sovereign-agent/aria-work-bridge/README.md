# aria-work-bridge

Keys round K4 — THE KEYSTONE. Plugs the finished, tested, never-called
autonomous engine into the natural-language front door. (Folder named
`aria-work-bridge` because `aria-session-bridge` was already taken by the
historical M83 session-portrait module — the live payload module is still
`session_bridge.py`.)

## The one-line truth (research, 2026-07-04)

`agent_session.run_session` — Gates 1-4 (PROTOCOL-ZERO →
operator-interrupt → session-budget-with-margin → authority),
`NEXT_SUBTASK` decomposition, per-subtask `agent_loop` execution, atomic
checkpoint after every subtask — was **finished, tested, and had zero live
callers**. `cockpit_modes.autonomous_loops_allowed()` was defined and
never called; `/mode work` was cosmetic.

## What ships

- **`session_bridge.py`** (new): `start_goal_session(goal)` — the call
  site that never existed (`new_session` + `run_session` with the full
  tool registry and a Workstream-N-shaped budget: 1h wall + 360s safety
  margin). Sessions default to `Mode.BUSY` (tier ceiling 1) so any Tier-2+
  subtask makes Gate 4 PAUSE for operator approval — the load-bearing
  safety default. Plus `queue_operator_message` / `drain_operator_messages`
  (tagged `session-queued`; notes left via `sov requests tell` untouched).
- **`/work <goal>`** — the deliberate, deterministic entry. A design
  choice, stated plainly: plain chat text does NOT silently start
  autonomous work even in work mode — one explicit token of intent guards
  against a casual "thanks!" spawning a session. (An LLM-classified `goal`
  intent can ride later.) Work mode runs; **chat mode proposes and
  waits** — tells Kevin exactly what would happen and how to arm it.
- **Kevin's no-interrupt rule, both sides**: while a session runs,
  `_dispatch_turn`'s busy branch QUEUES his text (previously it was
  *dropped* with a "still working" notice) with a "queued for her next
  safe checkpoint 💛" meta-line; inside the engine, each subtask start —
  a safe boundary by construction — folds the queued messages into her
  context (`═══ OPERATOR MESSAGES ═══` section + a `session-notes-d`
  event). `/halt` (PROTOCOL-ZERO) is a slash verb and bypasses the queue
  entirely: safety outranks politeness.
- **Observability for free**: the engine's `session-*`/`subtask-*` events
  flow through events.jsonl into K1's run strip + rich live-pane renders.

## Safety properties (each one tested)

- Chat mode NEVER auto-runs (`test_chat_mode_work_verb_proposes_and_never_runs`).
- The four gates' bodies are byte-identical pre/post patch (`test_gates_untouched`).
- Queued messages deliver at the subtask boundary, never mid-iteration
  (`test_queued_messages_fold_into_the_subtask_goal`).
- Untagged inbox notes stay for ReadInboxTool (`test_drain_leaves_untagged_inbox_notes_alone`).
- `/halt` bypasses the queue (`test_halt_verb_bypasses_the_queue`).
- The budget carries the safety margin (`test_budget_carries_the_safety_margin`).

## Verify / Apply

```
.venv/bin/python -m pytest aria-work-bridge/tests/test_patcher.py -q
./aria-work-bridge/apply_work_bridge.sh
```

Reversible: restore `agent_session.py` + `cockpit/app.py` from the
timestamped `backups/` dir and remove `session_bridge.py`.
