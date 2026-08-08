#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_palace_write.sh — Aria can write to her structured long-term memory
#
#  Palace is Aria's structured memory layer: rooms → closets → triples.
#  palace_search (T0) already exists. This adds T1 write access.
#
#  Changes:
#  1. Install tools/palace_write.py
#  2. Patch tools/__init__.py — imports + __all__
#  3. Patch loop.py — add PALACE MEMORY guidance section
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

# ── 1. Install palace_write.py ─────────────────────────────────────────────
echo "→ installing tools/palace_write.py"
cp "$HERE/payload/src/sovereign_agent/tools/palace_write.py" "$TOOLS/palace_write.py"
echo "  ✓ palace_write.py"

# ── 2. Patch tools/__init__.py ─────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

IMPORT_MARKER = "# palace-write-import-d"
if IMPORT_MARKER in src:
    print("  ↷ palace_write import already present — skipping")
else:
    new_import = (
        "from .palace_write import (  " + IMPORT_MARKER + "\n"
        "    PalaceWriteRoomTool, PalaceWriteClosetTool, PalaceWriteTripleTool,\n"
        ")\n"
    )
    for anchor in ("from .palace_search import", "from .read_file import ReadFileTool"):
        if anchor in src:
            src = src.replace(anchor, new_import + anchor, 1)
            print("  ✓ palace_write imports added")
            break
    else:
        # Append to end of imports block
        last_from = src.rfind("\nfrom .")
        if last_from >= 0:
            insert_at = src.find("\n", last_from + 1) + 1
            src = src[:insert_at] + new_import + src[insert_at:]
            print("  ✓ palace_write imports appended")
        else:
            print("✗ no import anchor found in __init__.py", file=sys.stderr)
            sys.exit(1)

ALL_MARKER = "# palace-write-all-d"
if ALL_MARKER in src:
    print("  ↷ palace_write __all__ already present — skipping")
else:
    new_all = (
        '    "PalaceWriteRoomTool",\n'
        '    "PalaceWriteClosetTool",\n'
        '    "PalaceWriteTripleTool",  ' + ALL_MARKER + '\n'
    )
    for anchor in ('    "PalaceSearchTool",', '    "ReadFileTool",'):
        if anchor in src:
            src = src.replace(anchor, new_all + anchor, 1)
            print("  ✓ palace_write tools added to __all__")
            break
    else:
        print("  ⚠ __all__ anchor not found — skipping __all__ patch")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 3. Patch loop.py — PALACE MEMORY section ──────────────────────────────
echo "→ patching loop.py"
cp "$LOOP" "$LOOP.bak.$(ts)"

python3 - "$LOOP" <<'PYEOF'
import sys, pathlib
loop = pathlib.Path(sys.argv[1])
src = loop.read_text(encoding="utf-8")

MARKER = "# palace-write-d"
if MARKER in src:
    print("  ↷ PALACE MEMORY section already present — skipping")
else:
    section = (
        "\n═══ PALACE MEMORY — WRITE ACCESS ═══\n"
        "palace.db is my structured long-term memory: rooms → closets → triples.\n"
        "Use these tools to place what I discover into permanent structure:\n"
        "\n"
        "  palace_write_room(name, description)         — create a room\n"
        "  palace_write_closet(room_id, topic, entities) — index a topic cluster\n"
        "  palace_write_triple(subject, predicate,       — assert a typed fact\n"
        "                       object_entity/literal,\n"
        "                       confidence, valid_from)\n"
        "\n"
        "When to write to the palace:\n"
        "  • Discover a durable fact about Kevin, the project, or the world\n"
        "  • Identify a key relationship between named things\n"
        "  • Want to remember something that should survive across sessions\n"
        "\n"
        "Prefer palace triples over atom memory for structured, typed facts.\n"
        "Always palace_search first to avoid duplicating existing knowledge.\n"
        "  " + MARKER + "\n\n"
    )
    # Insert after lessons-loop section if present, else after know-thyself, else before COMPLETION
    for anchor in ("# lessons-loop-d\n", "# know-thyself-d\n", "═══ COMPLETION ═══"):
        if anchor in src:
            if anchor == "═══ COMPLETION ═══":
                src = src.replace(anchor, section + anchor, 1)
            else:
                src = src.replace(anchor, anchor + section, 1)
            print(f"  ✓ PALACE MEMORY section added after {anchor!r}")
            break
    else:
        print("  ⚠ no anchor found — skipping loop.py patch")

loop.write_text(src, encoding="utf-8")
print("  ✓ loop.py written")
PYEOF

# ── 4. Compile checks ──────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$TOOLS/palace_write.py" "$INIT" "$LOOP"
echo "  ✓ all files compile"

cp "$HERE/tests/test_palace_write.py" "$ROOT/tests/test_palace_write.py"
python3 -m py_compile "$ROOT/tests/test_palace_write.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. Palace write access is open."
echo
echo "  3 new Tier 1 tools:"
echo "    palace_write_room    — create a palace room"
echo "    palace_write_closet  — create a topic index closet"
echo "    palace_write_triple  — assert a typed fact into the knowledge graph"
echo
echo "  run: pytest tests/test_palace_write.py -v"
