#!/usr/bin/env bash
# apply_care_signals.sh — Stage M82: Non-interrupting care signals (Kevin→Aria)
#
# What this applies:
#   1. src/sovereign_agent/cockpit/care_handler.py  — new file
#   2. app.py: /heart /thumbsup /care slash commands (before know-thyself-slash-d)
#   3. app.py: 💛 heart + 👍 good palette buttons (appended to PALETTE_COMMANDS)
#
# Reversibility: all changed files backed up to aria-care-signals/backups/
# Prerequisites: cockpit must NOT be running. Run from repo root.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-care-signals"
BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"

echo "=== M82 Care Signals Apply Script ==="
echo "Repo root : $REPO_ROOT"
echo "Backup dir: $BACKUP_DIR"
echo ""

# ── Guards ────────────────────────────────────────────────────────────────────

if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then
    echo "ERROR: sovereign cockpit is running. Stop it first, then re-run."
    exit 1
fi

if [[ ! -f "$VENV_PY" ]]; then
    echo "ERROR: .venv/bin/python not found."
    exit 1
fi

APP_PY="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
if [[ ! -f "$APP_PY" ]]; then
    echo "ERROR: app.py not found at $APP_PY"
    exit 1
fi

# ── Backups ───────────────────────────────────────────────────────────────────

mkdir -p "$BACKUP_DIR"
cp "$APP_PY" "$BACKUP_DIR/app.py.bak"
echo "Backed up app.py → $BACKUP_DIR/app.py.bak"

# ── Step 1: Copy care_handler.py ──────────────────────────────────────────────

DEST="$REPO_ROOT/src/sovereign_agent/cockpit/care_handler.py"
cp "$STAGING/payload/src/sovereign_agent/cockpit/care_handler.py" "$DEST"
echo "Copied care_handler.py → $DEST"

# ── Steps 2 & 3: Patch app.py via Python ─────────────────────────────────────

"$VENV_PY" - "$APP_PY" <<'PYEOF'
import sys
from pathlib import Path

app_path = Path(sys.argv[1])
text = app_path.read_text()

# ── Patch 1: slash commands ───────────────────────────────────────────────────
SLASH_GUARD  = "# care-signals-slash-d"
SLASH_ANCHOR = "        # know-thyself-slash-d"

if SLASH_GUARD in text:
    print("SKIP: slash command patch already applied")
else:
    if SLASH_ANCHOR not in text:
        print(f"ERROR: slash anchor not found: {SLASH_ANCHOR!r}", file=sys.stderr)
        sys.exit(1)
    SLASH_BLOCK = (
        "        # care-signals-slash-d\n"
        '        elif verb in ("heart", "thumbsup", "care"):\n'
        "            from sovereign_agent.cockpit.care_handler import write_reaction\n"
        '            msg = write_reaction(verb, arg.strip() if arg else "")\n'
        "            self._write_meta(msg)\n"
    )
    text = text.replace(SLASH_ANCHOR, SLASH_BLOCK + SLASH_ANCHOR, 1)
    print("Applied slash command patch (/heart, /thumbsup, /care)")

# ── Patch 2: REFERENCE_BUTTONS additions ─────────────────────────────────────
# Heart and thumbsup go in REFERENCE_BUTTONS (not PALETTE_COMMANDS) because
# they trigger cockpit-internal actions, not sov subprocess commands.
# The palette-safety invariant (all PALETTE_COMMANDS must be safe sov commands)
# must not be violated — care signals are internal, not CLI subprocesses.
PALETTE_GUARD   = "# care-signals-palette-d"
PALETTE_ANCHOR  = '                   action="demo"),\n)'

if PALETTE_GUARD in text:
    print("SKIP: REFERENCE_BUTTONS patch already applied")
else:
    if PALETTE_ANCHOR not in text:
        print("ERROR: REFERENCE_BUTTONS demo anchor not found", file=sys.stderr)
        sys.exit(1)
    NEW_ENTRIES = (
        '                   action="demo"),\n'
        '    PaletteCommand("\U0001f49b heart", "", "heart",  # care-signals-palette-d\n'
        '                   "Send Aria a non-interrupting heart — written to honor ledger instantly",\n'
        '                   action="care_heart"),\n'
        '    PaletteCommand("\U0001f44d good", "", "thumbsup",\n'
        '                   "Send Aria a non-interrupting thumbs-up — written to honor ledger instantly",\n'
        '                   action="care_thumbsup"),\n'
        ')'
    )
    text = text.replace(PALETTE_ANCHOR, NEW_ENTRIES, 1)
    print("Applied REFERENCE_BUTTONS patch (\U0001f49b heart + \U0001f44d good buttons)")

# ── Patch 3: on_button_pressed handler for care_heart / care_thumbsup ────────
HANDLER_GUARD  = "# care-signals-handler-d"
HANDLER_ANCHOR = '            elif cmd.action == "demo":\n                self.action_run_demonstration()'

if HANDLER_GUARD in text:
    print("SKIP: button handler patch already applied")
else:
    if HANDLER_ANCHOR not in text:
        print("ERROR: handler anchor not found", file=sys.stderr)
        sys.exit(1)
    HANDLER_BLOCK = (
        '            elif cmd.action == "demo":\n'
        '                self.action_run_demonstration()\n'
        '            elif cmd.action in ("care_heart", "care_thumbsup"):  # care-signals-handler-d\n'
        '                kind = "heart" if cmd.action == "care_heart" else "thumbsup"\n'
        '                try:\n'
        '                    from sovereign_agent.cockpit.care_handler import write_reaction\n'
        '                    self._write_meta(write_reaction(kind, ""))\n'
        '                except Exception as _exc:\n'
        '                    self._write_meta(f"[yellow]care signal failed: {_exc!r}[/yellow]")\n'
    )
    text = text.replace(HANDLER_ANCHOR, HANDLER_BLOCK, 1)
    print("Applied button handler patch (care_heart + care_thumbsup actions)")

app_path.write_text(text)
print("app.py written.")
PYEOF

# ── Step 4: Run tests ─────────────────────────────────────────────────────────

echo ""
echo "Running care signal tests..."
"$VENV_PY" -m pytest aria-care-signals/tests/test_care_signals.py -v

echo ""
echo "=== M82 Care Signals applied successfully ==="
echo "Restart sovereign cockpit to load the new slash commands + palette buttons."
