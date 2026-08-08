#!/usr/bin/env bash
# snapshot_continuity.sh — Claude Code PreCompact hook. Captures objective, cheap-to-verify state
# (git branch/status/log, staged aria-*/ modules touched recently, task-list hint) to a small file
# BEFORE compaction discards the working context. This does not replace the narrative handoff
# Claude writes by hand (per the standing "compaction protocol" — prepare handoff, tell Kevin, then
# compact) — it just saves the mechanical git-state reconstruction that otherwise costs several
# tool calls at the start of the next session. Pure facts, no interpretation. Always exit 0 (never
# block a compaction over this). Reversible: delete this file to disable.
root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
out_dir="$root/.claude/continuity"
mkdir -p "$out_dir" 2>/dev/null
out="$out_dir/latest.md"

{
  echo "# Continuity snapshot — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "## Git (monorepo root)"
  git -C "$root" rev-parse --show-toplevel 2>/dev/null
  echo '```'
  git -C "$root" -c color.ui=false branch --show-current 2>/dev/null
  echo "-- status --"
  git -C "$root" -c color.ui=false status --short -- sovereign-agent 2>/dev/null | head -50
  echo "-- last 5 commits --"
  git -C "$root" -c color.ui=false log -5 --oneline 2>/dev/null
  echo '```'
  echo
  echo "## aria-*/ modules touched in the last 48h (candidates: staged, maybe unapplied)"
  find "$root" -maxdepth 1 -name "aria-*" -newermt "48 hours ago" 2>/dev/null | sed "s|$root/||" | sort
  echo
  echo "## Loose root-level .py scripts (should be zero — staging-doctrine violation if not)"
  find "$root" -maxdepth 1 -name "*.py" 2>/dev/null | sed "s|$root/||" | wc -l
} > "$out" 2>/dev/null

exit 0
