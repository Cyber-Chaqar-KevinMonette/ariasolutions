# aria-workflow-champion

Keys round K8 — Kevin: *"Make her a workflow champion and designer"* —
with scoping for her designing and architecting (K10).

- **`design_workflow`** (T1, PROPOSE-ONLY): goal → a structured draft —
  steps each with their tool, concrete VERIFICATION, and risk+recovery; a
  full ScopeContract (in/out, done_when, observe, security — K10's
  dimensions); platform notes per the PLATFORM_STANDARDS checklist (K7).
  Drafts persist atomically to `data_dir/workflow_drafts/` — her design
  portfolio.
- **The championship loop closes losslessly** (tested): the draft's
  `handoff` field is a ready-to-paste `/work <goal> | scope: ...` line
  that parses back into K10's ScopeContract exactly — design → human
  review → gated execution through K4. The tool itself never runs
  anything (proven by a test that booby-traps run_session/agent_loop).
- `workflow-designed-d` renders richly in the live pane.
- Deferred honestly: the WorkflowsScreen drafts-view upgrade (drafts are
  durable + listable; the screen is UI polish for a future pass).

## Verify / Apply
```
./aria-workflow-champion/apply_workflow_champion.sh
```
