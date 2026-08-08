#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_command_invariants.sh — Aria's living command improvement registry
#
#  Delivers three Tier 0/1 tools:
#
#    list_command_invariants()           — list all commands with profiles
#    read_command_invariant(cmd, sec)    — read behavioral rules + improvements
#    write_command_note(cmd, content)    — Aria accumulates command knowledge
#
#  And one cockpit slash command:
#    /invariants [command]   — show profiles or read one in chat
#
#  HOW THE INVARIANT SYSTEM WORKS:
#    • Profiles live at data_dir/command-invariants/<name>/
#    • Each has: invariants.md, improvements.md, notes.md
#    • Completely separate from the source tree — never clutters code
#    • Aria adds to it autonomously as she identifies improvements
#    • The operator can browse it with /invariants in the cockpit
#
#  EXAMPLE WORKFLOW:
#    Aria runs sov doctor, notices it misses sentinel health.
#    She calls write_command_note("sov-doctor", "should check all sentinel
#      health levels before reporting ok", section="improvements").
#    Next time: read_command_invariant("sov-doctor") surfaces this.
#    She can build aria-sov-doctor-v2/ to implement the improvement.
#
#  Idempotent. Backs up __init__.py and app.py before patching.
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

# ── 1. Install tool file ───────────────────────────────────────────────────
echo "→ installing tools/command_invariants.py"
cp "$HERE/payload/src/sovereign_agent/tools/command_invariants.py" "$TOOLS/command_invariants.py"
echo "  ✓ tools/command_invariants.py"

# ── 2. Patch tools/__init__.py ─────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

if "from .command_invariants import" in src:
    print("  ↷ command_invariants import already present — skipping")
else:
    for anchor in ("from .read_file import ReadFileTool", "from .write_file import WriteFileTool"):
        if anchor in src:
            src = src.replace(
                anchor,
                "from .command_invariants import (\n"
                "    ListCommandInvariantsTool,\n"
                "    ReadCommandInvariantTool,\n"
                "    WriteCommandNoteTool,\n"
                ")\n"
                + anchor,
                1,
            )
            print("  ✓ command_invariants imports added")
            break
    else:
        print("✗ no anchor found in __init__.py", file=sys.stderr)
        sys.exit(1)

for name in ('"ListCommandInvariantsTool"', '"ReadCommandInvariantTool"', '"WriteCommandNoteTool"'):
    if name in src:
        continue
    for anchor_all in ('    "ReadFileTool",', '    "WriteFileTool",'):
        if anchor_all in src:
            src = src.replace(
                anchor_all,
                '    "ListCommandInvariantsTool",\n'
                '    "ReadCommandInvariantTool",\n'
                '    "WriteCommandNoteTool",\n'
                + anchor_all,
                1,
            )
            print("  ✓ command_invariant tools added to __all__")
            break
    break  # all three added together

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 3. Patch app.py — /invariants slash command ────────────────────────────
echo "→ patching cockpit/app.py (/invariants command)"
cp "$APP" "$APP.bak.$(ts)"

python3 - "$APP" <<'PYEOF'
import sys, pathlib
app_path = pathlib.Path(sys.argv[1])
src = app_path.read_text(encoding="utf-8")

SLASH_MARKER = "# command-invariants-slash-d"
if SLASH_MARKER in src:
    print("  ↷ /invariants already patched — skipping")
else:
    # Find a stable insertion point — before the final else
    for old_anchor in (
        "        # workout-commands-d\n",
        "        # know-thyself-slash-d\n",
    ):
        if old_anchor in src:
            idx = src.index(old_anchor)
            src = (
                src[:idx]
                + "        elif verb in (\"invariants\", \"inv\", \"invariant\"):\n"
                  "            # /invariants [command] — show command invariant profiles\n"
                  "            self._show_command_invariants(arg.strip())\n"
                  "        " + SLASH_MARKER + "\n"
                + src[idx:]
            )
            print("  ✓ /invariants slash branch added")
            break
    else:
        # Fallback: insert before the else block
        old_else = ('        else:\n'
                    '            self._write_meta(f"unknown command: /{verb}")')
        if old_else in src:
            src = src.replace(
                old_else,
                "        elif verb in (\"invariants\", \"inv\", \"invariant\"):\n"
                "            # /invariants [command] — show command invariant profiles\n"
                "            self._show_command_invariants(arg.strip())\n"
                "        " + SLASH_MARKER + "\n"
                + old_else,
                1,
            )
            print("  ✓ /invariants slash branch added (fallback anchor)")
        else:
            print("✗ no anchor found for /invariants branch", file=sys.stderr)
            sys.exit(1)

# Add the _show_command_invariants method
METHOD_MARKER = "def _show_command_invariants(self"
if METHOD_MARKER in src:
    print("  ↷ _show_command_invariants already present — skipping")
else:
    for anchor in (
        "    def _show_cockpit_commands(self)",
        "    def _show_boot_status(self)",
        "    def _save_report(self)",
    ):
        if anchor in src:
            new_method = (
                '\n'
                '    @work(exclusive=False, group="cli")\n'
                '    async def _show_command_invariants(self, command: str = "") -> None:\n'
                '        """/ invariants [command] — show the invariant profile for a command."""\n'
                '        if command:\n'
                '            self._write_meta(f"[bold cyan]◊ invariants: {command}[/bold cyan]")\n'
                '            try:\n'
                '                from sovereign_agent.tools.command_invariants import ReadCommandInvariantTool\n'
                '                tool = ReadCommandInvariantTool()\n'
                '                result = await tool.execute(\n'
                '                    tool.Args(command=command), trace_id="inv"\n'
                '                )\n'
                '                if result.ok:\n'
                '                    for line in result.output.splitlines():\n'
                '                        self._write_meta(line)\n'
                '                else:\n'
                '                    self._write_meta(f"[yellow]{result.error}[/yellow]")\n'
                '            except Exception as exc:\n'
                '                self._write_meta(f"[red]invariant read error: {exc!r}[/red]")\n'
                '        else:\n'
                '            self._write_meta("[bold cyan]◊ command invariant profiles[/bold cyan]")\n'
                '            try:\n'
                '                from sovereign_agent.tools.command_invariants import ListCommandInvariantsTool\n'
                '                tool = ListCommandInvariantsTool()\n'
                '                result = await tool.execute(tool.Args(), trace_id="inv-list")\n'
                '                if result.ok:\n'
                '                    for line in result.output.splitlines():\n'
                '                        self._write_meta(line)\n'
                '                else:\n'
                '                    self._write_meta(f"[yellow]{result.error}[/yellow]")\n'
                '            except Exception as exc:\n'
                '                self._write_meta(f"[red]invariant list error: {exc!r}[/red]")\n'
                '\n'
                + anchor
            )
            src = src.replace(anchor, new_method, 1)
            print("  ✓ _show_command_invariants method added")
            break
    else:
        print("✗ no anchor for _show_command_invariants", file=sys.stderr)
        sys.exit(1)

app_path.write_text(src, encoding="utf-8")
print("  ✓ cockpit/app.py written")
PYEOF

# ── 4. Compile checks ──────────────────────────────────────────────────────
echo "→ compile check"
python3 -m py_compile \
  "$TOOLS/command_invariants.py" \
  "$INIT" \
  "$APP"
echo "  ✓ all files compile"

cp "$HERE/tests/test_command_invariants.py" "$ROOT/tests/test_command_invariants.py"
python3 -m py_compile "$ROOT/tests/test_command_invariants.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. Aria now has a living command improvement registry."
echo
echo "  cockpit: /invariants          → list all profiles"
echo "           /invariants sov-ask  → read a specific profile"
echo "  agent:   list_command_invariants()  → same list"
echo "           write_command_note(cmd, note, section='improvements')"
echo "  store:   data_dir/command-invariants/<name>/"
