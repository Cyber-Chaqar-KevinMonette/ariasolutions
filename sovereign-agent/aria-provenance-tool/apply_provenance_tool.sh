#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_provenance_tool.sh — Aria can trace the causal chain of any artifact
#
#  provenance.walk_backward() already exists (sov provenance <node>).
#  This wraps it as an agent tool so Aria can trace lineage from the loop.
#
#  Changes:
#  1. Install tools/provenance_tool.py
#  2. Patch tools/__init__.py — imports + __all__
#  3. Patch loop.py — add PROVENANCE guidance
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

# ── 1. Install provenance_tool.py ──────────────────────────────────────────
echo "→ installing tools/provenance_tool.py"
cp "$HERE/payload/src/sovereign_agent/tools/provenance_tool.py" "$TOOLS/provenance_tool.py"
echo "  ✓ provenance_tool.py"

# ── 2. Patch tools/__init__.py ─────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

IMPORT_MARKER = "# provenance-tool-import-d"
if IMPORT_MARKER in src:
    print("  ↷ provenance_tool import already present — skipping")
else:
    new_import = "from .provenance_tool import TraceProvenanceTool  " + IMPORT_MARKER + "\n"
    for anchor in ("from .read_file import ReadFileTool", "from .palace_search import"):
        if anchor in src:
            src = src.replace(anchor, new_import + anchor, 1)
            print("  ✓ TraceProvenanceTool import added")
            break
    else:
        last_from = src.rfind("\nfrom .")
        if last_from >= 0:
            insert_at = src.find("\n", last_from + 1) + 1
            src = src[:insert_at] + new_import + src[insert_at:]
            print("  ✓ provenance_tool import appended")
        else:
            print("✗ no import anchor found", file=sys.stderr)
            sys.exit(1)

ALL_MARKER = "# provenance-tool-all-d"
if ALL_MARKER in src:
    print("  ↷ TraceProvenanceTool __all__ already present — skipping")
else:
    new_all = '    "TraceProvenanceTool",  ' + ALL_MARKER + '\n'
    for anchor in ('    "ReadFileTool",', '    "PalaceSearchTool",'):
        if anchor in src:
            src = src.replace(anchor, new_all + anchor, 1)
            print("  ✓ TraceProvenanceTool added to __all__")
            break
    else:
        print("  ⚠ __all__ anchor not found — skipping")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 3. Patch loop.py — PROVENANCE section ─────────────────────────────────
echo "→ patching loop.py"
cp "$LOOP" "$LOOP.bak.$(ts)"

python3 - "$LOOP" <<'PYEOF'
import sys, pathlib
loop = pathlib.Path(sys.argv[1])
src = loop.read_text(encoding="utf-8")

MARKER = "# provenance-tool-d"
if MARKER in src:
    print("  ↷ PROVENANCE section already present — skipping")
else:
    section = (
        "\n═══ PROVENANCE ═══\n"
        "trace_provenance(node_id, depth=5, format='tree') — walk backward\n"
        "through everything that informed any atom, fact, recall, or event.\n"
        "\n"
        "When to use:\n"
        "  • Something unexpected in memory — where did it come from?\n"
        "  • A conclusion feels uncertain — what is its evidence chain?\n"
        "  • Debugging after something went wrong — trace the causal path.\n"
        "  " + MARKER + "\n\n"
    )
    for anchor in ("# web-better-d\n", "# behavior-self-d\n", "# palace-write-d\n",
                   "# lessons-loop-d\n", "# know-thyself-d\n", "═══ COMPLETION ═══"):
        if anchor in src:
            if anchor == "═══ COMPLETION ═══":
                src = src.replace(anchor, section + anchor, 1)
            else:
                src = src.replace(anchor, anchor + section, 1)
            print("  ✓ PROVENANCE section added")
            break
    else:
        print("  ⚠ no anchor found — skipping loop.py patch")

loop.write_text(src, encoding="utf-8")
print("  ✓ loop.py written")
PYEOF

# ── 4. Compile checks ──────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$TOOLS/provenance_tool.py" "$INIT" "$LOOP"
echo "  ✓ all files compile"

cp "$HERE/tests/test_provenance_tool.py" "$ROOT/tests/test_provenance_tool.py"
python3 -m py_compile "$ROOT/tests/test_provenance_tool.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. Aria can now trace the causal chain of any artifact."
echo
echo "  1 new Tier 0 tool: trace_provenance"
echo "  Formats: tree (default) | json | summary"
echo
echo "  run: pytest tests/test_provenance_tool.py -v"
