#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_git_write.sh — Aria can stage and commit her own work (T2, confirmed)
#
#  git_add, git_commit, git_create_branch — all Tier 2.
#  Operator sees "ok or /cancel" before any write executes.
#  No force-push. No push to remote. No rebase or reset.
#
#  Changes:
#  1. Install tools/git_write.py
#  2. Patch tools/__init__.py — imports + __all__
#  3. Patch loop.py — add GIT WRITE guidance
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

# ── 1. Install git_write.py ───────────────────────────────────────────────
echo "→ installing tools/git_write.py"
cp "$HERE/payload/src/sovereign_agent/tools/git_write.py" "$TOOLS/git_write.py"
echo "  ✓ git_write.py"

# ── 2. Patch tools/__init__.py ─────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

IMPORT_MARKER = "# git-write-import-d"
if IMPORT_MARKER in src:
    print("  ↷ git_write import already present — skipping")
else:
    new_import = (
        "from .git_write import (  " + IMPORT_MARKER + "\n"
        "    GitAddTool, GitCommitTool, GitCreateBranchTool,\n"
        ")\n"
    )
    for anchor in ("from .read_file import ReadFileTool", "from .palace_search import"):
        if anchor in src:
            src = src.replace(anchor, new_import + anchor, 1)
            print("  ✓ git_write imports added")
            break
    else:
        last_from = src.rfind("\nfrom .")
        if last_from >= 0:
            insert_at = src.find("\n", last_from + 1) + 1
            src = src[:insert_at] + new_import + src[insert_at:]
            print("  ✓ git_write imports appended")
        else:
            print("✗ no import anchor", file=sys.stderr); sys.exit(1)

ALL_MARKER = "# git-write-all-d"
if ALL_MARKER in src:
    print("  ↷ git_write __all__ already present — skipping")
else:
    new_all = (
        '    "GitAddTool",\n'
        '    "GitCommitTool",\n'
        '    "GitCreateBranchTool",  ' + ALL_MARKER + '\n'
    )
    for anchor in ('    "ReadFileTool",', '    "PalaceSearchTool",'):
        if anchor in src:
            src = src.replace(anchor, new_all + anchor, 1)
            print("  ✓ git_write added to __all__")
            break
    else:
        print("  ⚠ __all__ anchor not found")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 3. Patch loop.py — GIT WRITE section ──────────────────────────────────
echo "→ patching loop.py"
cp "$LOOP" "$LOOP.bak.$(ts)"

python3 - "$LOOP" <<'PYEOF'
import sys, pathlib
loop = pathlib.Path(sys.argv[1])
src = loop.read_text(encoding="utf-8")

MARKER = "# git-write-d"
if MARKER in src:
    print("  ↷ GIT WRITE section already present — skipping")
else:
    section = (
        "\n═══ GIT WRITE (Tier 2 — operator confirmed) ═══\n"
        "I can stage and commit my own work. Each tool requires operator approval.\n"
        "\n"
        "  git_add(paths=[...])           — stage files (T2)\n"
        "  git_commit(message='...')      — commit staged changes (T2)\n"
        "  git_create_branch(name='...')  — create + switch branch (T2)\n"
        "\n"
        "Pattern for committing module work:\n"
        "  1. git_status() — see what changed (T0)\n"
        "  2. git_diff() — review changes (T0)\n"
        "  3. git_add(paths=[...]) — stage (T2, operator confirms)\n"
        "  4. git_commit(message='...') — commit (T2, operator confirms)\n"
        "\n"
        "Never: force-push, push to remote, rebase, reset, or delete branches.\n"
        "  " + MARKER + "\n\n"
    )
    for anchor in ("# provenance-tool-d\n", "# web-better-d\n", "# behavior-self-d\n",
                   "# palace-write-d\n", "# lessons-loop-d\n", "═══ COMPLETION ═══"):
        if anchor in src:
            if anchor == "═══ COMPLETION ═══":
                src = src.replace(anchor, section + anchor, 1)
            else:
                src = src.replace(anchor, anchor + section, 1)
            print("  ✓ GIT WRITE section added")
            break
    else:
        print("  ⚠ no anchor found")

loop.write_text(src, encoding="utf-8")
print("  ✓ loop.py written")
PYEOF

# ── 4. Compile checks ──────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$TOOLS/git_write.py" "$INIT" "$LOOP"
echo "  ✓ all files compile"

cp "$HERE/tests/test_git_write.py" "$ROOT/tests/test_git_write.py"
python3 -m py_compile "$ROOT/tests/test_git_write.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. Aria can now stage and commit her own work (T2, confirmed)."
echo
echo "  3 new Tier 2 tools:"
echo "    git_add            — stage files"
echo "    git_commit         — create a commit"
echo "    git_create_branch  — create and switch branch"
echo
echo "  run: pytest tests/test_git_write.py -v"
