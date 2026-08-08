#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_lessons_loop.sh — Close the Reflector loop: Aria reads her lessons
#
#  The Reflector writes one lesson per completed task. Aria cannot read them.
#  This adds read_lessons (Tier 0) and wires it into the KNOW THYSELF boot
#  sequence in loop.py.
#
#  Changes:
#  1. Install tools/lessons_tool.py
#  2. Patch tools/__init__.py — imports + __all__
#  3. Patch loop.py — add WHAT I HAVE LEARNED section to KNOW THYSELF
#
#  Idempotent. Backs up patched files.
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
LOOP="$PKG/loop.py"
ts(){ date +%Y%m%d%H%M%S; }

# ── 1. Install lessons_tool.py ─────────────────────────────────────────────
echo "→ installing tools/lessons_tool.py"
cp "$HERE/payload/src/sovereign_agent/tools/lessons_tool.py" "$TOOLS/lessons_tool.py"
echo "  ✓ lessons_tool.py"

# ── 2. Patch tools/__init__.py ─────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

IMPORT_MARKER = "# lessons-loop-import-d"
if IMPORT_MARKER in src:
    print("  ↷ lessons_tool import already present — skipping")
else:
    new_import = "from .lessons_tool import ReadLessonsTool  " + IMPORT_MARKER + "\n"
    for anchor in ("from .read_file import ReadFileTool", "from .write_file import WriteFileTool"):
        if anchor in src:
            src = src.replace(anchor, new_import + anchor, 1)
            print("  ✓ ReadLessonsTool import added")
            break
    else:
        print("✗ no import anchor found in __init__.py", file=sys.stderr)
        sys.exit(1)

ALL_MARKER = "# lessons-loop-all-d"
if ALL_MARKER in src:
    print("  ↷ ReadLessonsTool __all__ already present — skipping")
else:
    new_all = '    "ReadLessonsTool",  ' + ALL_MARKER + '\n'
    for anchor in ('    "ReadFileTool",', '    "WriteFileTool",'):
        if anchor in src:
            src = src.replace(anchor, new_all + anchor, 1)
            print("  ✓ ReadLessonsTool added to __all__")
            break
    else:
        print("  ⚠ __all__ anchor not found")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 3. Patch loop.py — WHAT I HAVE LEARNED section ────────────────────────
echo "→ patching loop.py"
cp "$LOOP" "$LOOP.bak.$(ts)"

python3 - "$LOOP" <<'PYEOF'
import sys, pathlib
loop = pathlib.Path(sys.argv[1])
src = loop.read_text(encoding="utf-8")

MARKER = "# lessons-loop-d"
if MARKER in src:
    print("  ↷ WHAT I HAVE LEARNED section already present — skipping")
else:
    lessons_section = (
        "\n═══ WHAT I HAVE LEARNED ═══\n"
        "At the start of every session, after aria_status(), call:\n"
        "  read_lessons(limit=5)   — the 5 most recent distilled lessons\n"
        "These come from my own past work — more reliable than intuition.\n"
        "Apply them. If this session produces a new insight worth keeping,\n"
        "the Reflector will write a lesson automatically when we finish.\n"
        "For a specific domain, call: read_lessons(topic='timeout') etc.\n"
        "  " + MARKER + "\n\n"
    )
    # Insert after KNOW THYSELF section (from know-thyself module) if present,
    # else insert before COMPLETION
    KNOW_THYSELF_MARKER = "# know-thyself-d"
    COMPLETION = "═══ COMPLETION ═══"

    if KNOW_THYSELF_MARKER in src:
        src = src.replace(
            KNOW_THYSELF_MARKER + "\n",
            KNOW_THYSELF_MARKER + "\n" + lessons_section,
            1,
        )
        print("  ✓ WHAT I HAVE LEARNED added after KNOW THYSELF section")
    elif COMPLETION in src:
        src = src.replace(COMPLETION, lessons_section + COMPLETION, 1)
        print("  ✓ WHAT I HAVE LEARNED added before COMPLETION")
    else:
        print("  ⚠ no anchor found in loop.py — skipping prompt patch")

loop.write_text(src, encoding="utf-8")
print("  ✓ loop.py written")
PYEOF

# ── 4. Compile checks ──────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$TOOLS/lessons_tool.py" "$INIT" "$LOOP"
echo "  ✓ all files compile"

cp "$HERE/tests/test_lessons_tool.py" "$ROOT/tests/test_lessons_tool.py"
python3 -m py_compile "$ROOT/tests/test_lessons_tool.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. The Reflector loop is closed."
echo
echo "  1 new Tier 0 tool: read_lessons"
echo "  loop.py: WHAT I HAVE LEARNED section added to boot sequence"
echo "  Aria will now call read_lessons() at the start of each session"
echo
echo "  run: pytest tests/test_lessons_tool.py -v"
