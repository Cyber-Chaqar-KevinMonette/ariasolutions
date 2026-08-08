#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_record_screen.sh — Aria gains real screen VIDEO capture
#
#  Delivers one new Tier 1 tool:
#
#    record_screen  — record the Wayland screen (or a region) to an MP4
#                     using wf-recorder, for a bounded duration (1-120s).
#                     Saves to data_dir/recordings/screen_video/ and
#                     returns the path.
#
#  Why wf-recorder: the video sibling of the grim screenshot tool (same
#  tool family/author). Scriptable/headless-friendly — the answer for an
#  AI-driven tool call, unlike OBS Studio (GUI-first, for Kevin's own
#  manual showcase recording — installed separately, not wired as a tool).
#
#  Usage pattern:
#    record_screen(duration_seconds=15)  → /path/to/recording_1234.mp4
#
#  Prerequisites:
#    sudo apt install wf-recorder   # already installed + verified this session
#    # WAYLAND_DISPLAY must be set (it is when launched from cockpit)
#
#  Idempotent. Backs up __init__.py before patching.
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
ts(){ date +%Y%m%d%H%M%S; }

echo "→ installing tools/record_screen.py"
cp "$HERE/payload/src/sovereign_agent/tools/record_screen.py" "$TOOLS/record_screen.py"
echo "  ✓ tools/record_screen.py"

echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib

init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

if "from .record_screen import" in src:
    print("  ↷ record_screen import already present — skipping")
else:
    # Same stable anchor screenshot's own apply script uses.
    anchor = "from .write_file import WriteFileTool"
    if anchor not in src:
        print("✗ write_file anchor not found in __init__.py", file=sys.stderr)
        sys.exit(1)
    src = src.replace(
        anchor,
        "from .record_screen import RecordScreenTool\n" + anchor,
        1,
    )
    print("  ✓ RecordScreenTool import added")

if '"RecordScreenTool"' in src:
    print("  ↷ RecordScreenTool already in __all__ — skipping")
else:
    old_all = '    "WriteFileTool",'
    new_all = '    "RecordScreenTool",\n    "WriteFileTool",'
    if old_all in src:
        src = src.replace(old_all, new_all, 1)
        print("  ✓ RecordScreenTool added to __all__")
    else:
        print("  ⚠ could not locate __all__ anchor — add RecordScreenTool manually")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

echo "→ compile check"
python3 -m py_compile "$TOOLS/record_screen.py" "$INIT"
echo "  ✓ compiles"

cp "$HERE/tests/test_record_screen.py" "$ROOT/tests/test_record_screen.py"
echo "  ✓ tests/test_record_screen.py installed"
python3 -m py_compile "$ROOT/tests/test_record_screen.py"
echo "  ✓ test compiles"

echo
echo "✓ done. verify wf-recorder is installed:"
echo "    which wf-recorder || sudo apt install wf-recorder"
echo "    pytest tests/test_record_screen.py -v"
echo
echo "    # In cockpit (requires Wayland display):"
echo "    record_screen(duration_seconds=10)"
echo
