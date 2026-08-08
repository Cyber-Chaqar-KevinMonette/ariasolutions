#!/usr/bin/env bash
# apply_git_experience.sh — M61: git commit reflection loop
# Idempotent. Safe to re-run.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PAYLOAD="$REPO/aria-git-experience/payload"

echo "=== M61 Git Experience: commit reflection + week summary tools ==="

# ── 1. Copy tool file ─────────────────────────────────────────────────────────
cp "$PAYLOAD/src/sovereign_agent/tools/git_reflect.py" \
   "$REPO/src/sovereign_agent/tools/git_reflect.py"
echo "  ✓ git_reflect.py"

# ── 2. Register in tools/__init__.py ─────────────────────────────────────────
TOOLS_INIT="$REPO/src/sovereign_agent/tools/__init__.py"

if grep -q "M61-git-experience-d" "$TOOLS_INIT"; then
  echo "  ✓ git-experience tools already registered (skipping)"
else
  python3 "$REPO/aria-git-experience/patch_tools_init.py" "$TOOLS_INIT"
  echo "  ✓ tools/__init__.py patched"
fi

# ── 3. Copy tests ─────────────────────────────────────────────────────────────
cp "$REPO/aria-git-experience/tests/test_git_experience.py" \
   "$REPO/tests/test_git_experience.py"
echo "  ✓ tests/test_git_experience.py"

# ── 4. Run tests ──────────────────────────────────────────────────────────────
echo ""
echo "=== Running git-experience tests ==="
cd "$REPO"
.venv/bin/python -m pytest tests/test_git_experience.py -v --tb=short

echo ""
echo "=== M61 git-experience applied ==="
echo "  GitCommitReflectTool (T0) — write experience atom after every git_commit()"
echo "  GitWeekSummaryTool (T0) — commit→reflection coverage for last 7 days"
echo "  Doctrine: call git_commit_reflect() immediately after every git_commit()."
