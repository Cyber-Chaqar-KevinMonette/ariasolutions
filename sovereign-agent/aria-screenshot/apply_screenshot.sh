#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_screenshot.sh — Aria gains eyes on the screen
#
#  Delivers one new Tier 1 tool:
#
#    take_screenshot  — capture the Wayland screen or a specific monitor/
#                       region using grim. Saves PNG and returns path.
#                       Chain immediately with analyze_image.
#
#  Why grim: native Wayland screenshot, pre-installed on Pop!_OS COSMIC.
#  No X11 needed. No Python dependencies.
#
#  Usage pattern:
#    take_screenshot()              → /path/to/screenshot_1234.png
#    analyze_image(path="...", focus="all")   → describes what's on screen
#    extract_text_from_image(path="...")      → reads visible text
#
#  Prerequisites:
#    sudo apt install grim    # usually pre-installed on COSMIC
#    # WAYLAND_DISPLAY must be set (it is when launched from cockpit)
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

echo "→ installing tools/screenshot.py"
cp "$HERE/payload/src/sovereign_agent/tools/screenshot.py" "$TOOLS/screenshot.py"
echo "  ✓ tools/screenshot.py"

echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib

init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

if "from .screenshot import" in src:
    print("  ↷ screenshot import already present — skipping")
else:
    # Find a stable anchor: write_file is always present
    anchor = "from .write_file import WriteFileTool"
    if anchor not in src:
        print("✗ write_file anchor not found in __init__.py", file=sys.stderr)
        sys.exit(1)
    src = src.replace(
        anchor,
        "from .screenshot import TakeScreenshotTool\n" + anchor,
        1,
    )
    print("  ✓ TakeScreenshotTool import added")

if '"TakeScreenshotTool"' in src:
    print("  ↷ TakeScreenshotTool already in __all__ — skipping")
else:
    # Add to __all__ near WriteFileTool
    old_all = '    "WriteFileTool",'
    new_all = '    "TakeScreenshotTool",\n    "WriteFileTool",'
    if old_all in src:
        src = src.replace(old_all, new_all, 1)
        print("  ✓ TakeScreenshotTool added to __all__")
    else:
        print("  ⚠ could not locate __all__ anchor — add TakeScreenshotTool manually")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

echo "→ compile check"
python3 -m py_compile "$TOOLS/screenshot.py" "$INIT"
echo "  ✓ compiles"

cp "$HERE/tests/test_screenshot.py" "$ROOT/tests/test_screenshot.py"
echo "  ✓ tests/test_screenshot.py installed"
python3 -m py_compile "$ROOT/tests/test_screenshot.py"
echo "  ✓ test compiles"

echo
echo "✓ done. verify grim is installed:"
echo "    which grim || sudo apt install grim"
echo "    pytest tests/test_screenshot.py -v"
echo
echo "    # In cockpit (requires Wayland display):"
echo "    take_screenshot()"
echo "    analyze_image(path='<returned path>', focus='all')"
