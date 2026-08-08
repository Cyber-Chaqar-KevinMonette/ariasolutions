#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_git_eyes.sh — Tier 0 git read tools: git_log, git_diff, git_status,
#                      git_show, git_blame
#
#  All five tools are Tier 0 (read-only). Zero write risk.
#
#  Changes:
#  1. Install tools/git_tools.py
#  2. Patch tools/__init__.py — add imports + __all__ entries
#  3. Patch loop.py — add CODE AWARENESS section to system prompt
#
#  Idempotent. Backs up patched files before modifying.
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

# ── 1. Install git_tools.py ────────────────────────────────────────────────
echo "→ installing tools/git_tools.py"
cp "$HERE/payload/src/sovereign_agent/tools/git_tools.py" "$TOOLS/git_tools.py"
echo "  ✓ git_tools.py"

# ── 2. Patch tools/__init__.py ─────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

IMPORT_MARKER = "# git-eyes-import-d"
if IMPORT_MARKER in src:
    print("  ↷ git_tools import already present — skipping")
else:
    new_imports = (
        "from .git_tools import (\n"
        "    GitLogTool,\n"
        "    GitDiffTool,\n"
        "    GitStatusTool,\n"
        "    GitShowTool,\n"
        "    GitBlameTool,\n"
        ")  " + IMPORT_MARKER + "\n"
    )
    for anchor in ("from .read_file import ReadFileTool", "from .write_file import WriteFileTool"):
        if anchor in src:
            src = src.replace(anchor, new_imports + anchor, 1)
            print("  ✓ git_tools imports added")
            break
    else:
        print("✗ no import anchor found in __init__.py", file=sys.stderr)
        sys.exit(1)

ALL_MARKER = "# git-eyes-all-d"
if ALL_MARKER in src:
    print("  ↷ git_tools __all__ already present — skipping")
else:
    new_all = (
        '    "GitLogTool",\n'
        '    "GitDiffTool",\n'
        '    "GitStatusTool",\n'
        '    "GitShowTool",\n'
        '    "GitBlameTool",  ' + ALL_MARKER + '\n'
    )
    for anchor in ('    "ReadFileTool",', '    "WriteFileTool",'):
        if anchor in src:
            src = src.replace(anchor, new_all + anchor, 1)
            print("  ✓ git_tools added to __all__")
            break
    else:
        print("  ⚠ __all__ anchor not found — __all__ not updated")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 3. Patch loop.py — CODE AWARENESS section ─────────────────────────────
echo "→ patching loop.py"
cp "$LOOP" "$LOOP.bak.$(ts)"

python3 - "$LOOP" <<'PYEOF'
import sys, pathlib
loop = pathlib.Path(sys.argv[1])
src = loop.read_text(encoding="utf-8")

MARKER = "# git-eyes-loop-d"
if MARKER in src:
    print("  ↷ CODE AWARENESS section already present — skipping")
else:
    # Insert before ═══ COMPLETION ═══ (works whether or not Phase 1 patches are applied)
    COMPLETION = "═══ COMPLETION ═══"
    if COMPLETION not in src:
        print("  ⚠ COMPLETION anchor not found in loop.py — skipping prompt patch")
    else:
        insert = (
            "\n═══ CODE AWARENESS ═══\n"
            "Before any code-related task:\n"
            "  1. Call git_status() to see staged/unstaged state and current branch.\n"
            "  2. Call git_log(limit=10) to see what changed recently.\n"
            "  3. After writing or modifying files, call run_tests() to verify (if available).\n"
            "  4. Use git_diff(ref_a=HEAD) to review staged changes before proposing a commit.\n"
            "Git tools are Tier 0 — call them freely, no permission needed.\n"
            "  " + MARKER + "\n\n"
        )
        src = src.replace(COMPLETION, insert + COMPLETION, 1)
        print("  ✓ CODE AWARENESS section added to loop.py")

loop.write_text(src, encoding="utf-8")
print("  ✓ loop.py written")
PYEOF

# ── 4. Compile checks ──────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$TOOLS/git_tools.py" "$INIT" "$LOOP"
echo "  ✓ all files compile"

cp "$HERE/tests/test_git_tools.py" "$ROOT/tests/test_git_tools.py"
python3 -m py_compile "$ROOT/tests/test_git_tools.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. Aria now has git eyes."
echo
echo "  5 new Tier 0 tools: git_log, git_diff, git_status, git_show, git_blame"
echo "  loop.py: CODE AWARENESS section added to system prompt"
echo
echo "  run: pytest tests/test_git_tools.py -v"
