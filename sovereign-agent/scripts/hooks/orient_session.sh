#!/usr/bin/env bash
# orient_session.sh — Claude Code SessionStart hook. Injects a compact, factual orientation
# (branch, uncommitted files, last commit, loose-script count, most recent continuity snapshot)
# as additionalContext, so a fresh session doesn't have to spend tool calls re-discovering git
# state before starting real work — a real, recurring cost in this project's marathon-session
# working style. Pure facts, capped small. Always exit 0. Reversible: delete this file to disable.
root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

branch=$(git -C "$root" branch --show-current 2>/dev/null)
dirty=$(git -C "$root" status --short -- sovereign-agent 2>/dev/null | wc -l | tr -d ' ')
last_commit=$(git -C "$root" log -1 --format='%h %ad %s' --date=short 2>/dev/null)
loose=$(find "$root" -maxdepth 1 -name "*.py" 2>/dev/null | wc -l | tr -d ' ')
snap="$root/.claude/continuity/latest.md"
snap_line="(no prior continuity snapshot)"
[[ -f "$snap" ]] && snap_line="prior snapshot: $snap ($(head -1 "$snap" 2>/dev/null))"

ctx="Aria (sovereign-agent) orientation — branch '$branch', $dirty uncommitted file(s) under sovereign-agent/, last commit: $last_commit. Loose root-level .py scripts: $loose (should be 0 — see guard_loose_scripts hook / CLAUDE.md staging doctrine). $snap_line"

python3 - "$ctx" <<'PYEOF'
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))
PYEOF
exit 0
