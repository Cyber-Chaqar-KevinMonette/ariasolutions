#!/usr/bin/env bash
# apply_apply_dashboard.sh — Apply M81: cockpit Apply Dashboard (Ctrl+A + ⚙ apply button)
#
# Adds ApplyDashboardScreen to the cockpit: a visible "⚙ apply" button in the
# palette AND Ctrl+A keyboard shortcut. Lists all staged aria-*/apply_*.sh
# scripts with applied/pending status, runs the selected script with live
# streaming output.
#
# Changes to app.py (surgical, idempotent — 5 patches):
#   a. try/except import for ApplyDashboardScreen
#   b. Binding("ctrl+a", "apply_dashboard", "apply")  ← shows in footer
#   c. REFERENCE_BUTTONS entry  ← shows "⚙ apply" button in palette
#   d. on_button_pressed handler for action="apply_dashboard"
#   e. action_apply_dashboard() method
#
# Idempotent: each patch checks for a marker before inserting.
#
# 2026-08-02 (index-the-project pass — corrected same day): first wired this
# into app.py by hand (Ctrl+A opened the dashboard, verified via a real pilot
# run) before checking WHY it had never been wired. It had been superseded on
# purpose: ApplyDashboardScreen._run_script() runs an apply_*.sh via a raw
# `subprocess.Popen(["bash", script_path])` — no safe_apply.sh, no
# cockpit-stopped guard, no Tribunal gate, no rollback — while the cockpit
# itself is the live running process. aria-apply-queue (Ctrl+Shift+A,
# ApplyQueueScreen, already live) exists specifically to do this safely: it
# only SELECTS modules while the cockpit runs, and its own docstring says why
# — "you can't apply while the cockpit runs (that would mutate live src
# beneath it)". Kevin confirmed: revert the wiring rather than keep an
# unguarded live-apply path reachable by a keystroke. Reverted in app.py;
# this apply script now refuses to run rather than silently reintroduce it.
# If this is ever wanted back, do it by rewiring action_apply_dashboard() to
# call scripts/safe_apply.sh instead of raw subprocess.Popen — not by running
# this script as-is.
echo "✗ refusing: this module's Ctrl+A path runs apply scripts unguarded" \
     "while the cockpit is live — superseded by aria-apply-queue's safer" \
     "select-then-apply-after-close design. See this script's own header." >&2
exit 1

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="$REPO/aria-apply-dashboard"
PKG="$REPO/src/sovereign_agent"
APP="$PKG/cockpit/app.py"

echo "=== M81: Cockpit Apply Dashboard (Ctrl+A) ==="

# 1. Copy apply_screen.py — SKIPPED if live already has content this payload
#    lacks (a later module extended it after this one was staged).
if [[ -f "$PKG/cockpit/apply_screen.py" ]] && grep -q "_extract_script_info" "$PKG/cockpit/apply_screen.py" 2>/dev/null; then
  echo "  ↷ apply_screen.py already live with later extensions — not overwriting"
else
  echo "→ Copying apply_screen.py..."
  cp "$STAGING/payload/src/sovereign_agent/cockpit/apply_screen.py" \
     "$PKG/cockpit/apply_screen.py"
  echo "  ✓ apply_screen.py installed"
fi

# 2. Backup app.py
TS="$(date +%Y%m%d%H%M%S)"
cp "$APP" "${APP}.bak.${TS}"
echo "  ✓ app.py backed up to app.py.bak.${TS}"

# 3. Patch app.py (Python, surgical, idempotent)
echo "→ Patching app.py..."
.venv/bin/python - <<'PYEOF'
from pathlib import Path

app = Path("src/sovereign_agent/cockpit/app.py")
src = app.read_text(encoding="utf-8")

# ── a. Import guard ─────────────────────────────────────────────────────────
IMPORT_MARKER = "apply-dashboard-import-d"

if IMPORT_MARKER in src:
    print("  ↷ import already present — skipping")
else:
    IMPORT_ANCHOR = (
        "try:\n"
        "    from . import cosmic_fitness as _cf\n"
        "except Exception:  # pragma: no cover — cosmic fitness is strictly optional\n"
        "    _cf = None\n"
    )
    IMPORT_INSERT = (
        "try:\n"
        "    from . import cosmic_fitness as _cf\n"
        "except Exception:  # pragma: no cover — cosmic fitness is strictly optional\n"
        "    _cf = None\n"
        "\n"
        "try:\n"
        "    from .apply_screen import ApplyDashboardScreen  # apply-dashboard-import-d\n"
        "except Exception:  # pragma: no cover — apply dashboard is strictly optional\n"
        "    ApplyDashboardScreen = None  # type: ignore[assignment,misc]\n"
    )
    if IMPORT_ANCHOR not in src:
        print("✗ import anchor not found — has app.py changed?", flush=True)
        raise SystemExit(1)
    src = src.replace(IMPORT_ANCHOR, IMPORT_INSERT, 1)
    print("  ✓ import guard inserted")

# ── b. Binding ───────────────────────────────────────────────────────────────
BINDING_MARKER = "apply-dashboard-binding-d"

if BINDING_MARKER in src:
    print("  ↷ binding already present — skipping")
else:
    BIND_ANCHOR = (
        '        Binding("ctrl+y", "yank_last",       "yank",    show=True,  priority=True),\n'
        '        Binding("ctrl+r", "toggle_recording",  "rec",  show=True,  priority=True),'
    )
    BIND_INSERT = (
        '        Binding("ctrl+y", "yank_last",       "yank",    show=True,  priority=True),\n'
        '        Binding("ctrl+a", "apply_dashboard", "apply",   show=True,  priority=True),  # apply-dashboard-binding-d\n'
        '        Binding("ctrl+r", "toggle_recording",  "rec",  show=True,  priority=True),'
    )
    if BIND_ANCHOR not in src:
        print("✗ binding anchor not found — has app.py changed?", flush=True)
        raise SystemExit(1)
    src = src.replace(BIND_ANCHOR, BIND_INSERT, 1)
    print("  ✓ Binding ctrl+a inserted")

# ── c. action method ─────────────────────────────────────────────────────────
ACTION_MARKER = "apply-dashboard-action-d"

if ACTION_MARKER in src:
    print("  ↷ action method already present — skipping")
else:
    # Insert after action_help() definition
    ACTION_ANCHOR = (
        "    def action_help(self) -> None:\n"
        "        # Toggle. If help is already open, close it — so pressing F1 (or\n"
        "        # clicking the help button) again dismisses it instead of stacking\n"
        "        # another copy on top. This is the fix for \"help won't close\".\n"
        "        if isinstance(self.screen, HelpScreen):\n"
        "            self.pop_screen()\n"
        "        else:\n"
        "            self.push_screen(HelpScreen())\n"
    )
    ACTION_INSERT = (
        "    def action_help(self) -> None:\n"
        "        # Toggle. If help is already open, close it — so pressing F1 (or\n"
        "        # clicking the help button) again dismisses it instead of stacking\n"
        "        # another copy on top. This is the fix for \"help won't close\".\n"
        "        if isinstance(self.screen, HelpScreen):\n"
        "            self.pop_screen()\n"
        "        else:\n"
        "            self.push_screen(HelpScreen())\n"
        "\n"
        "    def action_apply_dashboard(self) -> None:  # apply-dashboard-action-d\n"
        '        """Ctrl+A → open the Apply Dashboard modal (aria-*/apply_*.sh runner)."""\n'
        "        if ApplyDashboardScreen is None:  # pragma: no cover\n"
        '            self._write_meta("[yellow]Apply Dashboard unavailable[/yellow]")\n'
        "            return\n"
        "        try:\n"
        "            from pathlib import Path\n"
        "            import sovereign_agent\n"
        "            repo_root = Path(sovereign_agent.__file__).parent.parent.parent.parent\n"
        "            self.push_screen(ApplyDashboardScreen(repo_root))\n"
        "        except Exception as exc:  # noqa: BLE001\n"
        '            self._write_meta(f"[red]could not open Apply Dashboard: {exc!r}[/red]")\n'
    )
    if ACTION_ANCHOR not in src:
        print("✗ action anchor not found — has app.py changed?", flush=True)
        raise SystemExit(1)
    src = src.replace(ACTION_ANCHOR, ACTION_INSERT, 1)
    print("  ✓ action_apply_dashboard() inserted")

# ── d. REFERENCE_BUTTONS palette entry ─────────────────────────────────────
REFBTN_MARKER = "apply-dashboard-refbtn-d"

if REFBTN_MARKER in src:
    print("  ↷ REFERENCE_BUTTONS entry already present — skipping")
else:
    # 2026-08-02: REFERENCE_BUTTONS reordered since staging (cosmic's own
    # entry, with its description line, is the stable anchor now — the
    # original anchor assumed cosmic was the tuple's first entry, which
    # stopped being true).
    REFBTN_ANCHOR = (
        '    PaletteCommand("\\u25CA cosmic", "", "cosmic",\n'
        '                   "Cosmic Fitness: test every glyph + see the special effects.",\n'
        '                   action="cosmic"),\n'
    )
    REFBTN_INSERT = (
        '    PaletteCommand("\\u2699 apply", "", "apply",  # apply-dashboard-refbtn-d\n'
        '                   "Open the Apply Dashboard — browse & run staged modules "\n'
        '                   "(also Ctrl+A · Esc to close)",\n'
        '                   action="apply_dashboard"),\n'
        '    PaletteCommand("\\u25CA cosmic", "", "cosmic",\n'
        '                   "Cosmic Fitness: test every glyph + see the special effects.",\n'
        '                   action="cosmic"),\n'
    )
    if REFBTN_ANCHOR not in src:
        print("✗ REFERENCE_BUTTONS anchor not found — has app.py changed?", flush=True)
        raise SystemExit(1)
    src = src.replace(REFBTN_ANCHOR, REFBTN_INSERT, 1)
    print("  ✓ ⚙ apply button added to REFERENCE_BUTTONS palette")

# ── e. on_button_pressed handler ─────────────────────────────────────────────
HANDLER_MARKER = "apply-dashboard-handler-d"

if HANDLER_MARKER in src:
    print("  ↷ on_button_pressed handler already present — skipping")
else:
    HANDLER_ANCHOR = (
        "            elif cmd.action == \"workflows\":\n"
        "                self._show_workflows()\n"
    )
    HANDLER_INSERT = (
        "            elif cmd.action == \"workflows\":\n"
        "                self._show_workflows()\n"
        "            elif cmd.action == \"apply_dashboard\":  # apply-dashboard-handler-d\n"
        "                self.action_apply_dashboard()\n"
    )
    if HANDLER_ANCHOR not in src:
        print("✗ on_button_pressed anchor not found — has app.py changed?", flush=True)
        raise SystemExit(1)
    src = src.replace(HANDLER_ANCHOR, HANDLER_INSERT, 1)
    print("  ✓ on_button_pressed handler for apply_dashboard inserted")

app.write_text(src, encoding="utf-8")
print("  ✓ app.py written")
PYEOF

# 4. Compile check
echo "→ Compile check..."
.venv/bin/python -m py_compile "$PKG/cockpit/apply_screen.py" "$APP"
echo "  ✓ compiles"

# 5. Copy and run tests
echo "→ Copying tests..."
cp "$STAGING/tests/test_apply_screen.py" "$REPO/tests/test_apply_screen.py"

echo "→ Running tests..."
.venv/bin/python -m pytest tests/test_apply_screen.py -v --tb=short

echo ""
echo "=== M81 complete ==="
echo "New file: src/sovereign_agent/cockpit/apply_screen.py"
echo "New button: '⚙ apply' in cockpit palette (right side, row 3)"
echo "New binding: Ctrl+A → Apply Dashboard"
echo "New tests: 9"
echo ""
echo "Usage: sovereign cockpit  →  click '⚙ apply'  or  press Ctrl+A"
