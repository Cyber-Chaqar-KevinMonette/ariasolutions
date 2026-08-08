#!/usr/bin/env bash
# guard_loose_scripts.sh — Claude Code PreToolUse hook (Write). HARD-DENY new loose *.py files
# directly at the sovereign-agent repo root. This is the exact mechanism that corrupted the
# cockpit twice in one night (2026-08-01): ~40 one-off root-level patch scripts (raise_busy_tier.py,
# fix_cockpit.py, patch_loop.py, ...) ran unstaged against live src/, outside git, outside review.
# CLAUDE.md's staging doctrine already says features ship via aria-<name>/ folders + apply scripts —
# this hook makes that structural instead of relying on remembering it under pressure.
# Fail-open on parse error (never wedge the session); reversible: delete this file to disable.
input=$(cat)
fp=$(printf '%s' "$input" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin); ti=d.get('tool_input',{}) or {}
    print(ti.get('file_path') or ti.get('path') or '')
except Exception:
    print('')" 2>/dev/null)
[[ -z "$fp" ]] && exit 0

root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
dir="$(dirname "$fp")"
base="$(basename "$fp")"

if [[ "$dir" == "$root" && "$base" == *.py ]]; then
  cat >&2 <<EOF
⛔ BLOCKED by guard_loose_scripts: '$base' would land directly at the sovereign-agent repo root.
   This exact pattern (loose one-off patch scripts run unstaged against live src/) corrupted the
   cockpit twice on 2026-08-01. CLAUDE.md doctrine: ship as aria-<name>/ + apply_<name>.sh instead —
   use /aria-new-module or scaffold it by hand under aria-<name>/payload/.
   If this genuinely belongs at root (rare — e.g. a real setup/tooling entrypoint), ask Kevin to
   confirm, then he can disable this hook or move the file after the fact.
EOF
  exit 2
fi
exit 0
