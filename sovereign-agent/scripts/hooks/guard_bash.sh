#!/usr/bin/env bash
# guard_bash.sh — Claude Code PreToolUse hook (Bash). WARN (never block) on venv/cockpit doctrine slips.
# Bash is never blocked (too risky); this only surfaces an advisory so I self-correct. Always exit 0.
input=$(cat)
cmd=$(printf '%s' "$input" | python3 -c "import sys,json
try: print((json.load(sys.stdin).get('tool_input',{}) or {}).get('command',''))
except Exception: print('')" 2>/dev/null)
[[ -z "$cmd" ]] && exit 0

warn=""
# pip install not targeting the venv → PEP-668 / venv discipline (CLAUDE.md Rule 4)
if printf '%s' "$cmd" | grep -Eq "(^|[^/])pip[0-9]* install" && ! printf '%s' "$cmd" | grep -q "\.venv/bin/pip"; then
  warn="venv discipline: use .venv/bin/pip (never system pip — PEP-668 protected)."
fi
# editing live src/ while a cockpit is running
if printf '%s' "$cmd" | grep -Eq "(>|cp|mv|sed -i|tee).*src/sovereign_agent/" && pgrep -f "sovereign cockpit" >/dev/null 2>&1; then
  warn="${warn:+$warn  }cockpit is RUNNING — do not mutate live src/ beneath it; stop it first."
fi

if [[ -n "$warn" ]]; then
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"},"systemMessage":"⚠ guard_bash: %s"}\n' "$warn"
fi
exit 0
