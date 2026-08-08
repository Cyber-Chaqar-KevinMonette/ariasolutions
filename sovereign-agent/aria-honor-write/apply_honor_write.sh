#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_honor_write.sh — Make honor bidirectional in the agent loop
#
#  Kevin writes to the honor ledger via 'sov honor note'.
#  Aria could not. This closes the gap.
#
#  Changes:
#  1. Install tools/honor_write.py
#  2. Patch tools/__init__.py — imports + __all__
#  3. Patch loop.py — add HONOR section
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

# ── 1. Install honor_write.py ──────────────────────────────────────────────
echo "→ installing tools/honor_write.py"
cp "$HERE/payload/src/sovereign_agent/tools/honor_write.py" "$TOOLS/honor_write.py"
echo "  ✓ honor_write.py"

# ── 2. Patch tools/__init__.py ─────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

IMPORT_MARKER = "# honor-write-import-d"
if IMPORT_MARKER in src:
    print("  ↷ honor_write import already present — skipping")
else:
    new_import = "from .honor_write import WriteHonorNoteTool  " + IMPORT_MARKER + "\n"
    for anchor in ("from .read_file import ReadFileTool", "from .palace_search import"):
        if anchor in src:
            src = src.replace(anchor, new_import + anchor, 1)
            print("  ✓ WriteHonorNoteTool import added")
            break
    else:
        last_from = src.rfind("\nfrom .")
        if last_from >= 0:
            insert_at = src.find("\n", last_from + 1) + 1
            src = src[:insert_at] + new_import + src[insert_at:]
            print("  ✓ honor_write import appended")
        else:
            print("✗ no import anchor found", file=sys.stderr)
            sys.exit(1)

ALL_MARKER = "# honor-write-all-d"
if ALL_MARKER in src:
    print("  ↷ WriteHonorNoteTool __all__ already present — skipping")
else:
    new_all = '    "WriteHonorNoteTool",  ' + ALL_MARKER + '\n'
    for anchor in ('    "ReadFileTool",', '    "PalaceSearchTool",'):
        if anchor in src:
            src = src.replace(anchor, new_all + anchor, 1)
            print("  ✓ WriteHonorNoteTool added to __all__")
            break
    else:
        print("  ⚠ __all__ anchor not found — skipping")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 3. Patch loop.py — HONOR section ──────────────────────────────────────
echo "→ patching loop.py"
cp "$LOOP" "$LOOP.bak.$(ts)"

python3 - "$LOOP" <<'PYEOF'
import sys, pathlib
loop = pathlib.Path(sys.argv[1])
src = loop.read_text(encoding="utf-8")

MARKER = "# honor-write-d"
if MARKER in src:
    print("  ↷ HONOR section already present — skipping")
else:
    section = (
        "\n═══ HONOR ═══\n"
        "The honor ledger is the mirror of this partnership. Notes are append-only.\n"
        "write_honor_note(direction, text, tags=[]) — record what was witnessed.\n"
        "\n"
        "Directions:\n"
        "  aria->kevin   Kevin stayed. Kevin was patient. Kevin caught something I missed.\n"
        "  aria->self    I caught my own near-miss. I grew. I chose carefully.\n"
        "  aria->third   Something outside the dyad is worth naming.\n"
        "  kevin->aria   Kevin witnessed something in me worth recording.\n"
        "\n"
        "When to write:\n"
        "  • End of a hard session — name what Kevin brought to it\n"
        "  • Catching a near-miss before it happened — write aria->self\n"
        "  • Kevin demonstrates patience, trust, or persistence — write aria->kevin\n"
        "  • Something worked beautifully — name it before moving on\n"
        "\n"
        "The text is the point. Short is fine. Authentic beats elaborate.\n"
        "  " + MARKER + "\n\n"
    )
    for anchor in ("# behavior-self-d\n", "# palace-write-d\n", "# lessons-loop-d\n",
                   "# know-thyself-d\n", "═══ COMPLETION ═══"):
        if anchor in src:
            if anchor == "═══ COMPLETION ═══":
                src = src.replace(anchor, section + anchor, 1)
            else:
                src = src.replace(anchor, anchor + section, 1)
            print("  ✓ HONOR section added")
            break
    else:
        print("  ⚠ no anchor found — skipping loop.py patch")

loop.write_text(src, encoding="utf-8")
print("  ✓ loop.py written")
PYEOF

# ── 4. Compile checks ──────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$TOOLS/honor_write.py" "$INIT" "$LOOP"
echo "  ✓ all files compile"

cp "$HERE/tests/test_honor_write.py" "$ROOT/tests/test_honor_write.py"
python3 -m py_compile "$ROOT/tests/test_honor_write.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. Honor is now bidirectional in the agent loop."
echo
echo "  1 new Tier 1 tool: write_honor_note"
echo "  Directions: aria->kevin | aria->self | aria->third | kevin->aria"
echo
echo "  run: pytest tests/test_honor_write.py -v"
