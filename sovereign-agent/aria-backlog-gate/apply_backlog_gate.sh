#!/usr/bin/env bash
# apply_backlog_gate.sh — M60: backlog quality pre-flight gate
# Idempotent. Safe to re-run.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PAYLOAD="$REPO/aria-backlog-gate/payload"

echo "=== M60 Backlog Gate: quality pre-flight for autonomous sessions ==="

# ── 1. Copy backlog_gate.py to src ───────────────────────────────────────────
cp "$PAYLOAD/src/sovereign_agent/backlog_gate.py" \
   "$REPO/src/sovereign_agent/backlog_gate.py"
echo "  ✓ backlog_gate.py"

# ── 2. Copy backlog_tools.py to src ──────────────────────────────────────────
cp "$PAYLOAD/src/sovereign_agent/tools/backlog_tools.py" \
   "$REPO/src/sovereign_agent/tools/backlog_tools.py"
echo "  ✓ backlog_tools.py"

# ── 3. Register in tools/__init__.py ─────────────────────────────────────────
TOOLS_INIT="$REPO/src/sovereign_agent/tools/__init__.py"

if grep -q "M60-backlog-gate-d" "$TOOLS_INIT"; then
  echo "  ✓ backlog-gate tools already registered (skipping)"
else
  python3 "$REPO/aria-backlog-gate/patch_tools_init.py" "$TOOLS_INIT"
  echo "  ✓ tools/__init__.py patched"
fi

# ── 4. Copy tests ─────────────────────────────────────────────────────────────
cp "$REPO/aria-backlog-gate/tests/test_backlog_gate.py" \
   "$REPO/tests/test_backlog_gate.py"
echo "  ✓ tests/test_backlog_gate.py"

# ── 5. Run tests ──────────────────────────────────────────────────────────────
echo ""
echo "=== Running backlog-gate tests ==="
cd "$REPO"
.venv/bin/python -m pytest tests/test_backlog_gate.py -v --tb=short

echo ""
echo "=== M60 backlog-gate applied ==="
echo "  BacklogGate logic in backlog_gate.py"
echo "  BacklogReadTool (T0) + BacklogGateTool (T1) registered"
echo "  Run: backlog_gate(dry_run=True) before any auto session"
