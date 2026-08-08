#!/usr/bin/env bash
# apply_risk_register.sh — M57: Risk Register read + propose tools + status updates
# Idempotent. Safe to re-run.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PAYLOAD="$REPO/aria-risk-register/payload"

echo "=== M57 Risk Register: tools + RISK-004/008/011 → MITIGATING ==="

# ── 1. Copy tool file ─────────────────────────────────────────────────────────
cp "$PAYLOAD/src/sovereign_agent/tools/risk_tools.py" \
   "$REPO/src/sovereign_agent/tools/risk_tools.py"
echo "  ✓ risk_tools.py"

# ── 2. Register in tools/__init__.py ─────────────────────────────────────────
TOOLS_INIT="$REPO/src/sovereign_agent/tools/__init__.py"

if grep -q "M57-risk-register-d" "$TOOLS_INIT"; then
  echo "  ✓ risk tools already registered (skipping)"
else
  python3 "$REPO/aria-risk-register/patch_tools_init.py" "$TOOLS_INIT"
  echo "  ✓ tools/__init__.py patched"
fi

# ── 3. Update risk register statuses ─────────────────────────────────────────
REGISTER="$REPO/docs/Aria_Weakness_Risk_Register.md"
echo "  Updating risk register statuses..."
python3 "$REPO/aria-risk-register/patch_risk_register_md.py" "$REGISTER"

# ── 4. Copy tests ─────────────────────────────────────────────────────────────
cp "$REPO/aria-risk-register/tests/test_risk_tools.py" \
   "$REPO/tests/test_risk_tools.py"
echo "  ✓ tests/test_risk_tools.py"

# ── 5. Run tests ──────────────────────────────────────────────────────────────
echo ""
echo "=== Running risk-register tests ==="
cd "$REPO"
.venv/bin/python -m pytest tests/test_risk_tools.py -v --tb=short

echo ""
echo "=== M57 risk-register applied ==="
echo "  RiskRegisterReadTool (T0) + RiskRegisterProposeTool (T1) registered."
echo "  RISK-004, RISK-008, RISK-011 flipped to MITIGATING."
echo "  Run: risk_register_read() to verify all 14 entries parse correctly."
