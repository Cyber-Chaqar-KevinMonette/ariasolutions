# aria-git-flow — safe, efficient git work (FABLE II · M8)

> Kevin: *"work safely and efficiently with her git tools — robust and
> resilient."* Audit found two real gaps, closed here. Absence, not
> discouragement: no tool in this module has ever had reset/clean/force,
> and the shared helper now refuses them mechanically too.

## Never-main discipline
`GitCommitTool` and `GitCheckpointTool` never let a commit land on a
default branch (main/master, or whatever the remote's HEAD resolves to):
if HEAD is on one, the tool auto-branches to `aria/<slug>-<timestamp>`
FIRST, then commits there. Committing to a default branch is refused —
the refusal never surfaces because the tool resolves it before the
commit runs.

## `git_checkpoint` — one gated action, not two
Status → add → commit as ONE Tier-2 approval (the M7 graduated-trust
spirit: fewer round-trips for a routine, low-risk sequence). Refuses on
a clean diff (`nothing_changed`) and during an in-progress
merge/rebase/cherry-pick (`merge_in_progress`) — a checkpoint mid-conflict
would be confusing, not helpful. Message composes RESULT-style
(`summary`, blank line, optional `body`).

## Garden-aware
When a garden is planted (`scope: dir:` on `/work`), every git tool here
refuses unless the repo IS the garden or the garden is inside the repo —
the same wall `pathguard` already enforces for file writes.

## Resilience
- `errors="replace"` on every subprocess call in this module (git_tools.py
  read-only helpers already had it; git_write.py's write helper now does too).
- The shared `_git()` in **both** git_write.py and git_tools.py refuses
  `reset`, `clean`, `filter-branch`/`filter-repo`, any force flag
  (`--force`/`-f`/`--force-with-lease`), and `branch -D` — mechanically,
  before the subprocess even runs. No tool ever passes these; the check
  is a backstop against a future bug, not a policy on paper.
- `git_checkpoint`'s dirty-tree guard refuses mid-merge/rebase.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-git-flow
./scripts/safe_apply.sh aria-git-flow
```
