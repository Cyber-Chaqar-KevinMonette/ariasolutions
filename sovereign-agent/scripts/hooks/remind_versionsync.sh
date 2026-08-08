#!/usr/bin/env bash
# remind_versionsync.sh — Claude Code PostToolUse hook (Edit|Write). Surface the version-bump drift trap.
# Fires after an edit to __init__.py (version source of truth) or pyproject.toml. Advisory only; exit 0.
input=$(cat)
fp=$(printf '%s' "$input" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin); ti=d.get('tool_input',{}) or {}
    print(ti.get('file_path') or ti.get('path') or '')
except Exception: print('')" 2>/dev/null)
case "$(basename "$fp")" in
  __init__.py|pyproject.toml)
    if printf '%s' "$fp" | grep -Eq "sovereign_agent/__init__.py$|/pyproject.toml$"; then
      printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse"},"systemMessage":"🔁 version drift trap (CLAUDE.md Rule 5): if you bumped __version__, update pyproject.toml to match AND run .venv/bin/pip install -e . so CacheSentinel reads matching metadata."}\n'
    fi ;;
esac
exit 0
