#!/usr/bin/env bash
# apply_cosmic_fitness_restore.sh — FULL restore of cockpit/app.py to its last-known-good state.
#
# THE REGRESSION: commit 8fc7267 ("Add AA-Aria and Genesis-Seeds as part of project", 2026-06-25)
# rewrote cockpit/app.py: 122 insertions(+), 2254 deletions(-). Its commit message is entirely about
# adding project folders — nothing about the cockpit — so this was almost certainly an accidental
# overwrite (a stale copy of app.py dragged into that same commit), not a deliberate redesign.
# It silently destroyed: CosmicFitnessScreen, WorkflowsScreen, GlyphButton, the ripple-glow border
# effects (RippleFrame/RippleBorderMixin), the third reference-button row (legend/rec/cosmic/grow/
# apply_dashboard/workflows), voice push-to-talk, screen recording, self-practice ("grow"), and
# sentinel-chat transition alerts. `cockpit/__init__.py` still imports symbols this left behind,
# which is why `sov chat` crashed outright.
#
# THE FIX: `git log --follow` shows NOTHING has touched cockpit/app.py since the regression except
# the regression commit itself. Commit 0fdcdbd09b992ab535304e5ef5102fb960b64f89 (2026-06-20, "QoL +
# playwright: boot sequence, auto-notify, voice Ctrl-P, browser JS, slash commands") is therefore the
# complete, git-authoritative, last-known-good version — not a loose .bak snapshot, the actual
# committed history. Restoring app.py to that exact commit is a clean, whole-file, zero-guesswork fix.
#
# VERIFIED before this script was written (see aria-cosmic-fitness-restore/tests/ + session record):
#   • py_compile clean · full shadow-package import clean · CockpitApp() instantiates
#   • headless Textual boot test: chat-log + glyph-picker both present, no exception
#   • tests/test_cosmic_fitness.py: 71/71 PASS (up from 68/71 against the smaller interim patch)
#   • the 20 other cockpit-touching test files: the only 8 failures are CONFIRMED PRE-EXISTING on
#     current live (unrelated to this restore — vessel_status.py / mos_surface version-string issues)
#
# Anatomy: guard (cockpit stopped + venv) → backup current app.py → restore from git history →
# py_compile → import check → run test_cosmic_fitness.py. Fully reversible: the backup is a plain
# file copy, and `git show 0fdcdbd:...` is itself permanent, replayable history.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
GIT_ROOT="$(cd "$REPO_ROOT/.." && pwd)"
STAGING="$REPO_ROOT/aria-cosmic-fitness-restore"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
APP="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
RESTORE_COMMIT="0fdcdbd09b992ab535304e5ef5102fb960b64f89"

echo "=== aria-cosmic-fitness-restore: FULL restore of cockpit/app.py ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$APP" ]] || { echo "ERROR: $APP not found."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$APP" "$BACKUP_DIR/app.py.bak"
echo "  ✓ backup of current app.py → $BACKUP_DIR/app.py.bak"

echo "→ Restoring from git history ($RESTORE_COMMIT)..."
( cd "$GIT_ROOT" && git show "$RESTORE_COMMIT:sovereign-agent/src/sovereign_agent/cockpit/app.py" ) > "$APP"
echo "  ✓ restored ($(wc -l < "$APP") lines, was $(wc -l < "$BACKUP_DIR/app.py.bak"))"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$APP"
echo "  ✓ py_compile clean"

echo "→ Import check (the actual crash Kevin hit)..."
"$VENV_PY" -c "
from sovereign_agent.cockpit import CockpitApp, CosmicFitnessScreen, HelpScreen, WorkflowsScreen, run
print('  ✓ full cockpit import chain OK')
app = CockpitApp()
print('  ✓ CockpitApp() instantiates cleanly')
"

echo "Running tests/test_cosmic_fitness.py (should be 71/71, not 68/71 — the inline picker is back)..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_cosmic_fitness.py" -q

echo "=== aria-cosmic-fitness-restore applied. Reversible: backup at $BACKUP_DIR/app.py.bak 💛 ==="
echo "    Next: relaunch  sov chat  (or  sov cockpit)  and confirm it boots clean with all effects back."
