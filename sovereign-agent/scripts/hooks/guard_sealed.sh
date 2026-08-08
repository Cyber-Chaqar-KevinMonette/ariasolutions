#!/usr/bin/env bash
# guard_sealed.sh — Claude Code PreToolUse hook (Edit|Write). HARD-DENY edits to sealed/safety files.
# Mirrors CLAUDE.md Golden Rule 2. Reads the tool-input JSON on stdin; exit 2 + stderr blocks the edit.
# Fail-open ONLY on parse error (never wedge the session); the sealed set is also guarded by discipline.
input=$(cat)
fp=$(printf '%s' "$input" | python3 -c "import sys,json
try:
    d=json.load(sys.stdin); ti=d.get('tool_input',{}) or {}
    print(ti.get('file_path') or ti.get('path') or '')
except Exception:
    print('')" 2>/dev/null)
[[ -z "$fp" ]] && exit 0   # no path / parse error → allow (defense-in-depth, not sole guard)

base="$(basename "$fp")"
case "$base" in
  SIGNAL.md|mos_canon.py|authority.py|protocol_zero.py|seal.py)
    cat >&2 <<EOF
⛔ BLOCKED by guard_sealed: '$fp' is a SEALED file
   (charter hash / DEFERRED_UNSAFE / authority tiers / kill-switch / seal).
   CLAUDE.md Golden Rule 2: never edit these casually or automatically.
   If a change genuinely requires it → STOP and ask Kevin (he can disable this hook to override).
EOF
    exit 2 ;;
esac
exit 0
