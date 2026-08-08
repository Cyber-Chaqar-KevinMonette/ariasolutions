#!/usr/bin/env bash
# apply_council_cockpit.sh — Stage M91: /council and /globe cockpit commands
#
# What this applies:
#   1. src/sovereign_agent/cockpit/council_handler.py — new handler
#   2. app.py: /council <question> and /globe slash commands (before know-thyself-slash-d)
#   3. Copies test into tests/ (standing suite)
#
# Lets Kevin consult the non-classical globe council and see the globe live. Advisory only.
# Reversibility: backups at aria-council-cockpit/backups/. Requires M89 (quantum mode).
# Prerequisites: cockpit must NOT be running. Run from repo root.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-council-cockpit"
BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
APP_PY="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"

echo "=== M91 Council Cockpit Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then
    echo "ERROR: sovereign cockpit is running. Stop it first."; exit 1
fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: .venv/bin/python not found."; exit 1; fi
if [[ ! -f "$APP_PY" ]]; then echo "ERROR: app.py not found."; exit 1; fi

mkdir -p "$BACKUP_DIR"
cp "$APP_PY" "$BACKUP_DIR/app.py.bak"
echo "Backed up app.py → $BACKUP_DIR"

cp "$STAGING/payload/src/sovereign_agent/cockpit/council_handler.py" "$REPO_ROOT/src/sovereign_agent/cockpit/"
echo "Copied council_handler.py → src/sovereign_agent/cockpit/"

"$VENV_PY" - "$APP_PY" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()

GUARD  = "# council-cockpit-slash-d"
ANCHOR = "        # know-thyself-slash-d"

if GUARD in text:
    print("SKIP: slash patch already applied")
else:
    if ANCHOR not in text:
        print(f"ERROR: anchor not found: {ANCHOR!r}", file=sys.stderr); sys.exit(1)
    BLOCK = (
        "        # council-cockpit-slash-d\n"
        '        elif verb == "council":\n'
        "            from sovereign_agent.cockpit.council_handler import consult_text\n"
        "            self._write_meta(consult_text(arg.strip() if arg else \"\"))\n"
        '        elif verb == "globe":\n'
        "            from sovereign_agent.cockpit.council_handler import globe_text\n"
        "            self._write_meta(globe_text())\n"
    )
    text = text.replace(ANCHOR, BLOCK + ANCHOR, 1)
    print("Applied /council + /globe slash patch")

p.write_text(text)
print("app.py written.")
PYEOF

echo ""
echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT/src/sovereign_agent/cockpit/council_handler.py" "$APP_PY"
echo "  ✓ compiles cleanly"

cp "$STAGING/tests/test_council_cockpit.py" "$REPO_ROOT/tests/test_council_cockpit.py"
echo "Copied test_council_cockpit.py → tests/"

echo ""
echo "Running council cockpit tests..."
"$VENV_PY" -m pytest tests/test_council_cockpit.py -q

echo ""
echo "=== M91 Council Cockpit applied successfully ==="
echo "Restart cockpit. Try: /globe   or   /council Should we ship this?"
