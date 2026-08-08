#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_workout.sh — The Cosmic Gym finale. Aria knows her full repertoire.
#
#  Three changes:
#
#  1. tools/cockpit_commands.py — Tier 0 tool: list_cockpit_commands()
#     Returns the complete slash command map (30+ commands, grouped).
#     Aria calls this to suggest cockpit commands to the operator.
#
#  2. cockpit/app.py — /commands slash command:
#     /commands → pretty-print all slash commands inline in chat
#
#  3. cockpit/app.py — welcome banner gets a /boot hint:
#     Adds "type /boot to orient me, /commands to see what I can do"
#     as a dim hint line after the existing welcome text.
#
#  Apply last in the know-thyself sequence.
#  Idempotent. Backs up app.py and __init__.py before patching.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$PWD}"

if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }
    d="$(dirname "$d")"
  done
fi
[[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || { echo "✗ run from repo root"; exit 1; }
echo "◊ repo root: $ROOT"

PKG="$ROOT/src/sovereign_agent"
TOOLS="$PKG/tools"
INIT="$TOOLS/__init__.py"
APP="$PKG/cockpit/app.py"
ts(){ date +%Y%m%d%H%M%S; }

# ── 1. Install tool ────────────────────────────────────────────────────────
echo "→ installing tools/cockpit_commands.py"
cp "$HERE/payload/src/sovereign_agent/tools/cockpit_commands.py" "$TOOLS/cockpit_commands.py"
echo "  ✓ tools/cockpit_commands.py"

# ── 2. Patch tools/__init__.py ─────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

if "from .cockpit_commands import" in src:
    print("  ↷ cockpit_commands import already present — skipping")
else:
    for anchor in ("from .read_file import ReadFileTool", "from .write_file import WriteFileTool"):
        if anchor in src:
            src = src.replace(
                anchor,
                "from .cockpit_commands import ListCockpitCommandsTool\n" + anchor,
                1,
            )
            print("  ✓ ListCockpitCommandsTool import added")
            break
    else:
        print("✗ no anchor found in __init__.py for cockpit_commands", file=sys.stderr)
        sys.exit(1)

if '"ListCockpitCommandsTool"' not in src:
    for anchor_all in ('    "ReadFileTool",', '    "WriteFileTool",'):
        if anchor_all in src:
            src = src.replace(
                anchor_all,
                '    "ListCockpitCommandsTool",\n' + anchor_all,
                1,
            )
            print("  ✓ ListCockpitCommandsTool added to __all__")
            break
else:
    print("  ↷ ListCockpitCommandsTool already in __all__ — skipping")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 3. Patch app.py ───────────────────────────────────────────────────────
echo "→ patching cockpit/app.py"
cp "$APP" "$APP.bak.$(ts)"

python3 - "$APP" <<'PYEOF'
import sys, pathlib
app_path = pathlib.Path(sys.argv[1])
src = app_path.read_text(encoding="utf-8")

# ── 3a. Add /commands slash branch ────────────────────────────────────────
CMD_MARKER = "# workout-commands-d"
if CMD_MARKER in src:
    print("  ↷ /commands already patched — skipping")
else:
    # Insert before the final else or before know-thyself marker if present
    for old_anchor in (
        "        # know-thyself-slash-d\n"
        "        else:\n"
        '            self._write_meta(f"unknown command: /{verb}")',
        '        else:\n'
        '            self._write_meta(f"unknown command: /{verb}")',
    ):
        if old_anchor in src:
            new_branch = (
                '        elif verb in ("commands", "cmds", "help-all"):\n'
                '            # /commands → pretty-print all slash commands inline\n'
                '            self._show_cockpit_commands()\n'
                '        ' + CMD_MARKER + '\n'
                + old_anchor
            )
            src = src.replace(old_anchor, new_branch, 1)
            print("  ✓ /commands slash branch added")
            break
    else:
        print("✗ no suitable anchor for /commands branch", file=sys.stderr)
        sys.exit(1)

# ── 3b. Add _show_cockpit_commands method before _save_report ─────────────
METHOD_MARKER = "def _show_cockpit_commands(self)"
if METHOD_MARKER in src:
    print("  ↷ _show_cockpit_commands already present — skipping")
else:
    # Use _show_claude_md as anchor if know-thyself already applied,
    # otherwise fall back to _save_report
    for anchor in (
        "    def _show_claude_md(self)",
        "    def _save_report(self)",
    ):
        if anchor in src:
            new_method = (
                '\n'
                '    def _show_cockpit_commands(self) -> None:\n'
                '        """/ commands — display all slash commands grouped by category."""\n'
                '        try:\n'
                '            from sovereign_agent.tools.cockpit_commands import _COMMANDS, _CATEGORY_HEADERS\n'
                '            self._write_meta("[bold cyan]◊ cockpit slash commands[/bold cyan]")\n'
                '            prev_h = None\n'
                '            for cmd, hint, desc in _COMMANDS:\n'
                '                h = _CATEGORY_HEADERS.get(cmd)\n'
                '                if h and h != prev_h:\n'
                '                    self._write_meta(f"[dim]{h}[/dim]")\n'
                '                    prev_h = h\n'
                '                arg_str = f" {hint}" if hint else ""\n'
                '                self._write_meta(f"  [cyan]/{cmd}[/cyan]{arg_str:22s} [dim]{desc}[/dim]")\n'
                '        except Exception as exc:\n'
                '            self._write_meta(f"[red]command list error: {exc!r}[/red]")\n'
                '\n'
                + anchor
            )
            src = src.replace(anchor, new_method, 1)
            print("  ✓ _show_cockpit_commands method added")
            break
    else:
        print("✗ no anchor for _show_cockpit_commands", file=sys.stderr)
        sys.exit(1)

# ── 3c. Add /boot hint to welcome banner ──────────────────────────────────
BANNER_MARKER = "# workout-banner-d"
if BANNER_MARKER in src:
    print("  ↷ banner hint already patched — skipping")
else:
    OLD_BANNER_TAIL = (
        '        self._chat_log.write(\n'
        '            "[dim]F1 for help.[/dim]"\n'
        '        )\n'
        '        self._chat_log.write("")'
    )
    if OLD_BANNER_TAIL not in src:
        print("  ⚠ welcome banner anchor not found — skipping banner patch")
    else:
        NEW_BANNER_TAIL = (
            '        self._chat_log.write(\n'
            '            "[dim]F1 for help.[/dim]"\n'
            '        )\n'
            '        self._chat_log.write(\n'
            '            "[dim]type [cyan]/boot[/cyan] to orient me · '
            '[cyan]/commands[/cyan] to see what I can do · '
            '[cyan]/docs[/cyan] for operating doctrine[/dim]"\n'
            '        )  ' + BANNER_MARKER + '\n'
            '        self._chat_log.write("")'
        )
        src = src.replace(OLD_BANNER_TAIL, NEW_BANNER_TAIL, 1)
        print("  ✓ /boot hint added to welcome banner")

app_path.write_text(src, encoding="utf-8")
print("  ✓ cockpit/app.py written")
PYEOF

# ── 4. Compile checks ──────────────────────────────────────────────────────
echo "→ compile check"
python3 -m py_compile \
  "$TOOLS/cockpit_commands.py" \
  "$INIT" \
  "$APP"
echo "  ✓ all files compile"

# ── 5. Install tests ───────────────────────────────────────────────────────
cp "$HERE/tests/test_workout.py" "$ROOT/tests/test_workout.py"
python3 -m py_compile "$ROOT/tests/test_workout.py"
echo "  ✓ tests/test_workout.py installed + compiles"

echo
echo "✓ done. Aria knows her full repertoire."
echo
echo "  cockpit: /commands   → full slash command map"
echo "           /boot       → self-awareness snapshot"
echo "  agent:   list_cockpit_commands()  → same map available to agent"
echo
echo "  run: pytest tests/test_workout.py -v"
