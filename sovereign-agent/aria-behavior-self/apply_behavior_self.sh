#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_behavior_self.sh — Aria reads and writes her own behavior patterns
#
#  The BehaviorPatternStore is the self-perception layer. The interpreter
#  already loads patterns. This adds agent-loop tools for browsing and
#  contributing new patterns.
#
#  Changes:
#  1. Install tools/behavior_tools.py
#  2. Patch tools/__init__.py — imports + __all__
#  3. Patch loop.py — add SELF-PERCEPTION section
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

# ── 1. Install behavior_tools.py ───────────────────────────────────────────
echo "→ installing tools/behavior_tools.py"
cp "$HERE/payload/src/sovereign_agent/tools/behavior_tools.py" "$TOOLS/behavior_tools.py"
echo "  ✓ behavior_tools.py"

# ── 2. Patch tools/__init__.py ─────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

IMPORT_MARKER = "# behavior-self-import-d"
if IMPORT_MARKER in src:
    print("  ↷ behavior_tools import already present — skipping")
else:
    new_import = (
        "from .behavior_tools import (  " + IMPORT_MARKER + "\n"
        "    ReadBehaviorPatternsTool, WriteBehaviorPatternTool,\n"
        ")\n"
    )
    for anchor in ("from .read_file import ReadFileTool", "from .palace_search import"):
        if anchor in src:
            src = src.replace(anchor, new_import + anchor, 1)
            print("  ✓ behavior_tools imports added")
            break
    else:
        last_from = src.rfind("\nfrom .")
        if last_from >= 0:
            insert_at = src.find("\n", last_from + 1) + 1
            src = src[:insert_at] + new_import + src[insert_at:]
            print("  ✓ behavior_tools imports appended")
        else:
            print("✗ no import anchor found", file=sys.stderr)
            sys.exit(1)

ALL_MARKER = "# behavior-self-all-d"
if ALL_MARKER in src:
    print("  ↷ behavior_tools __all__ already present — skipping")
else:
    new_all = (
        '    "ReadBehaviorPatternsTool",\n'
        '    "WriteBehaviorPatternTool",  ' + ALL_MARKER + '\n'
    )
    for anchor in ('    "ReadFileTool",', '    "PalaceSearchTool",'):
        if anchor in src:
            src = src.replace(anchor, new_all + anchor, 1)
            print("  ✓ behavior_tools added to __all__")
            break
    else:
        print("  ⚠ __all__ anchor not found — skipping")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 3. Patch loop.py — SELF-PERCEPTION section ────────────────────────────
echo "→ patching loop.py"
cp "$LOOP" "$LOOP.bak.$(ts)"

python3 - "$LOOP" <<'PYEOF'
import sys, pathlib
loop = pathlib.Path(sys.argv[1])
src = loop.read_text(encoding="utf-8")

MARKER = "# behavior-self-d"
if MARKER in src:
    print("  ↷ SELF-PERCEPTION section already present — skipping")
else:
    section = (
        "\n═══ SELF-PERCEPTION — BEHAVIOR PATTERNS ═══\n"
        "My behavior patterns are crystallized good work — past sessions where\n"
        "a shape worked well, distilled into reusable guidance. The interpreter\n"
        "auto-loads matching patterns each turn. I can also browse and add them:\n"
        "\n"
        "  read_behavior_patterns()                   — browse active patterns\n"
        "  read_behavior_patterns(context='evening')  — filter by keyword\n"
        "  write_behavior_pattern(name, description,  — record a new pattern\n"
        "                          action_shape, ...)   when I notice good work\n"
        "\n"
        "When to write a pattern:\n"
        "  • I just handled something complex well — same shape will recur\n"
        "  • I notice a trigger + good response shape + outcome = consistent\n"
        "  • A lesson suggests a general behavioral shape I should memorize\n"
        "  " + MARKER + "\n\n"
    )
    for anchor in ("# palace-write-d\n", "# lessons-loop-d\n", "# know-thyself-d\n", "═══ COMPLETION ═══"):
        if anchor in src:
            if anchor == "═══ COMPLETION ═══":
                src = src.replace(anchor, section + anchor, 1)
            else:
                src = src.replace(anchor, anchor + section, 1)
            print(f"  ✓ SELF-PERCEPTION section added")
            break
    else:
        print("  ⚠ no anchor found — skipping loop.py patch")

loop.write_text(src, encoding="utf-8")
print("  ✓ loop.py written")
PYEOF

# ── 4. Compile checks ──────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$TOOLS/behavior_tools.py" "$INIT" "$LOOP"
echo "  ✓ all files compile"

cp "$HERE/tests/test_behavior_self.py" "$ROOT/tests/test_behavior_self.py"
python3 -m py_compile "$ROOT/tests/test_behavior_self.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. Aria's self-perception loop is open."
echo
echo "  2 tools:"
echo "    read_behavior_patterns  (T0) — browse active behavior patterns"
echo "    write_behavior_pattern  (T1) — propose a new pattern from good work"
echo
echo "  run: pytest tests/test_behavior_self.py -v"
