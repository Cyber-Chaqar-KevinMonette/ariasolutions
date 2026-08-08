#!/usr/bin/env bash
# aria_session_status.sh — the cold-start orienter for Claude Code.
# One screen of orientation so a fresh session doesn't re-derive the world:
#   staged vs applied modules · tests · tools · safety kernel · git cleanliness · the floor.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
VENV_PY="$REPO_ROOT/.venv/bin/python"

echo "════════════════════════════════════════════════════════════════"
echo "  ARIA — Claude Code session orientation   ($(date +%Y-%m-%d\ %H:%M))"
echo "════════════════════════════════════════════════════════════════"

staged=$(ls -d aria-*/ 2>/dev/null | wc -l | tr -d ' ')
applied_tools=$(grep -c -- "-import-d" src/sovereign_agent/tools/__init__.py 2>/dev/null || echo 0)
testfiles=$(ls tests/test_*.py 2>/dev/null | wc -l | tr -d ' ')
srcfiles=$(find src -name '*.py' 2>/dev/null | wc -l | tr -d ' ')
tools=$(grep -rh "class.*Tool" src/sovereign_agent/tools/*.py 2>/dev/null | grep -c "Tool" || echo 0)
echo "  Modules : ${staged} staged aria-* folders   ·   ${applied_tools} tool-modules registered live"
echo "  Code    : ${srcfiles} src files · ${testfiles} test files · ${tools} tools"

# Safety kernel (the floor's bedrock).
if [[ -x "$VENV_PY" ]]; then
  kernel=$("$VENV_PY" -c "from sovereign_agent.security.safety_kernel import kernel_scan; print(kernel_scan()['status'])" 2>/dev/null || echo "UNKNOWN")
else
  kernel="NO-VENV"
fi
echo "  Safety  : kernel ${kernel}   ·   DEFERRED_UNSAFE held · propose-don't-act"

# Git cleanliness.
changed=$(git status --short 2>/dev/null | wc -l | tr -d ' ')
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")
echo "  Git     : branch ${branch} · ${changed} changed path(s)"

# Floor (if present).
if [[ -x "$REPO_ROOT/scripts/floor_check.sh" ]]; then
  floor=$("$REPO_ROOT/scripts/floor_check.sh" --quiet 2>/dev/null && echo "MET" || echo "VIOLATED")
  echo "  Floor   : god-tier floor ${floor}   (scripts/floor_check.sh)"
fi

echo "────────────────────────────────────────────────────────────────"
echo "  Read first : CLAUDE.md (rules) · .claude/PLAYBOOK.md (how-to) · MEMORY index"
echo "  Skills     : /aria-new-module /aria-verify /aria-apply /aria-scrutinize /aria-status"
echo "  Recent staged systems: aria-tribunal · aria-frugality · aria-foresight · aria-own-mind"
echo "════════════════════════════════════════════════════════════════"
