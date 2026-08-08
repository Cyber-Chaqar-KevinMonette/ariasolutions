#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_game_dev_helpers.sh — closes two real gaps found live 2026-08-03
#  while running Aria's actual live agent loop against Ember Keep.
#
#  Delivers three new tools:
#
#    read_game_file / edit_game_file (Tier 0 / Tier 1)
#      — path-safe file access scoped by project_slug, same pattern as
#        scan_game_project/godot_check/place_game_sprite. Closes the exact
#        gap that broke her first real edit attempt: she guessed a wrong
#        absolute path instead of resolving it.
#
#    game_input (Tier 1)
#      — real synthetic mouse/keyboard input via ydotool (click, click_at,
#        move_relative, move_absolute, key). Lets her actually playtest a
#        running game herself (click to tend the fire, F5 to launch Play),
#        the same mechanism proven live by hand this session. Kevin's
#        explicit choice: Tier 1, no per-call approval gate, after being
#        told this is NOT sandboxed to the game window — it's real
#        desktop-wide input.
#
#  Prerequisites for game_input to actually work at runtime (not required
#  to apply/import — it fails loudly with daemon_unreachable if missing):
#    sudo apt install ydotool ydotoold
#    sudo usermod -aG input $USER   # re-login required
#    ydotoold &                     # background daemon
#
#  Idempotent. Backs up __init__.py before patching.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# root-detect-safety-d (found live 2026-08-03): an explicit $1 that
# didn't have the marker file used to fall through to the upward-search
# below, which silently resolves to $PWD's real repo instead — a
# disposable-worktree verify run ended up writing this module's tool
# into the LIVE repo instead of the worktree, undetected until manually
# checked. An explicit root is now trusted-or-refused, never silently
# overridden.
if [[ -n "${1:-}" ]]; then
  ROOT="$1"
  [[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || {
    echo "✗ given root $ROOT has no src/sovereign_agent/cli.py — refusing to guess elsewhere"
    exit 1
  }
else
  ROOT="$PWD"
  if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
    d="$PWD"
    while [[ "$d" != "/" ]]; do
      [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }
      d="$(dirname "$d")"
    done
  fi
  [[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || { echo "✗ run from repo root"; exit 1; }
fi
echo "◊ repo root: $ROOT"

PKG="$ROOT/src/sovereign_agent"
TOOLS="$PKG/tools"
INIT="$TOOLS/__init__.py"
ts(){ date +%Y%m%d%H%M%S; }

echo "→ installing tools/game_file_tools.py"
cp "$HERE/payload/src/sovereign_agent/tools/game_file_tools.py" "$TOOLS/game_file_tools.py"
echo "  ✓ tools/game_file_tools.py"

echo "→ installing tools/game_input.py"
cp "$HERE/payload/src/sovereign_agent/tools/game_input.py" "$TOOLS/game_input.py"
echo "  ✓ tools/game_input.py"

echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib

init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")
anchor = "from .write_file import WriteFileTool"
if anchor not in src:
    print("✗ write_file anchor not found in __init__.py", file=sys.stderr)
    sys.exit(1)

imports = [
    ("from .game_file_tools import", "from .game_file_tools import ReadGameFileTool, EditGameFileTool\n"),
    ("from .game_input import", "from .game_input import GameInputTool\n"),
]
prefix = ""
for marker, line in imports:
    if marker in src:
        print(f"  ↷ {line.strip()} already present — skipping import")
    else:
        prefix += line
if prefix:
    src = src.replace(anchor, prefix + anchor, 1)
    print("  ✓ imports added")

all_entries = ["ReadGameFileTool", "EditGameFileTool", "GameInputTool"]
old_all = '    "WriteFileTool",'
new_all_lines = "".join(f'    "{name}",\n' for name in all_entries if f'"{name}"' not in src)
if new_all_lines:
    if old_all not in src:
        print("✗ could not locate __all__ anchor — add tools manually", file=sys.stderr)
        sys.exit(1)
    src = src.replace(old_all, new_all_lines + old_all, 1)
    print("  ✓ __all__ entries added")
else:
    print("  ↷ __all__ entries already present — skipping")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

echo "→ compile check"
python3 -m py_compile "$TOOLS/game_file_tools.py" "$TOOLS/game_input.py" "$INIT"
echo "  ✓ compiles"

cp "$HERE/tests/test_game_file_tools.py" "$ROOT/tests/test_game_file_tools.py"
cp "$HERE/tests/test_game_input.py" "$ROOT/tests/test_game_input.py"
echo "  ✓ tests installed"
python3 -m py_compile "$ROOT/tests/test_game_file_tools.py" "$ROOT/tests/test_game_input.py"
echo "  ✓ tests compile"

echo
echo "✓ done. verify:"
echo "    .venv/bin/python -m pytest tests/test_game_file_tools.py tests/test_game_input.py -v"
echo
echo "    # game_input needs the ydotool daemon actually running:"
echo "    pgrep -af ydotoold || (sudo apt install -y ydotool ydotoold && ydotoold &)"
