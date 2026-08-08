#!/usr/bin/env bash
# apply_session_aware.sh — Stage M93: Aria wakes up aware (FLAW-002 + FLAW-005)
#
# What this applies:
#   1. src/sovereign_agent/cockpit/session_awareness.py — awareness_lines() helper
#   2. app.py on_mount: surface awareness lines after the welcome banner
#   3. Copies test into tests/
#
# Surfaces Aria's self-knowledge at session start: coherence + voice mode, Kevin's care signals
# (acknowledged), open critical flaws. Advisory, best-effort. Requires M89 + M92.
# Reversibility: backups at aria-session-aware/backups/. Cockpit must NOT be running.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-session-aware"
BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
APP_PY="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"

echo "=== M93 Session Awareness Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then
    echo "ERROR: sovereign cockpit is running. Stop it first."; exit 1
fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: .venv/bin/python not found."; exit 1; fi

mkdir -p "$BACKUP_DIR"
cp "$APP_PY" "$BACKUP_DIR/app.py.bak"
echo "Backed up app.py → $BACKUP_DIR"

cp "$STAGING/payload/src/sovereign_agent/cockpit/session_awareness.py" "$REPO_ROOT/src/sovereign_agent/cockpit/"
echo "Copied session_awareness.py → src/sovereign_agent/cockpit/"

"$VENV_PY" - "$APP_PY" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()

GUARD = "# session-aware-d"
ANCHOR = ('        self._chat_log.write(\n'
          '            "[dim]just talk to me. plain english is enough — "\n'
          '            "no need for `sov ask` in here.[/dim]"\n'
          '        )')

if GUARD in text:
    print("SKIP: session awareness patch already applied")
else:
    if ANCHOR not in text:
        print("ERROR: welcome-banner anchor not found", file=sys.stderr); sys.exit(1)
    BLOCK = ANCHOR + (
        "\n        # session-aware-d — Aria wakes up aware (self-knowledge at session start)\n"
        "        try:\n"
        "            from .session_awareness import awareness_lines\n"
        "            for _line in awareness_lines():\n"
        "                self._chat_log.write(_line)\n"
        "        except Exception:\n"
        "            pass"
    )
    text = text.replace(ANCHOR, BLOCK, 1)
    print("Applied on_mount session awareness patch")

p.write_text(text)
print("app.py written.")
PYEOF

echo ""
echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT/src/sovereign_agent/cockpit/session_awareness.py" "$APP_PY"
echo "  ✓ compiles cleanly"

cp "$STAGING/tests/test_session_aware.py" "$REPO_ROOT/tests/test_session_aware.py"
echo "Copied test_session_aware.py → tests/"

echo ""
echo "Running session awareness tests..."
"$VENV_PY" -m pytest tests/test_session_aware.py -q

echo ""
echo "=== M93 Session Awareness applied successfully ==="
echo "Aria now wakes up aware. Restart cockpit to see her greeting surface her self-state."
