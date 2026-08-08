#!/usr/bin/env bash
# apply_protocol_zero_hardening.sh — M64: Protocol Zero hardening + Mode Controller fix
# Idempotent. Safe to re-run.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== M64 Protocol Zero Hardening ==="

# ── 1. Patch mode_controller.py — silent schedule injection → auditable event ──
MODE_CTRL="$REPO/src/sovereign_agent/mode_controller.py"
python3 "$REPO/aria-protocol-zero-hardening/patch_mode_controller.py" "$MODE_CTRL"
echo "  ✓ mode_controller.py patched (schedule-inject-error-d)"

# ── 2. Patch loop.py — git-reflect-d doctrine comment ────────────────────────
LOOP_PY="$REPO/src/sovereign_agent/loop.py"
if [ -f "$LOOP_PY" ]; then
  python3 "$REPO/aria-protocol-zero-hardening/patch_loop_doctrine.py" "$LOOP_PY"
  echo "  ✓ loop.py patched (git-reflect-d doctrine comment)"
else
  echo "  ! loop.py not found — skipping doctrine comment"
fi

# ── 3. Copy test files ────────────────────────────────────────────────────────
cp "$REPO/aria-protocol-zero-hardening/tests/test_protocol_zero_hardening.py" \
   "$REPO/tests/test_protocol_zero_hardening.py"
echo "  ✓ tests/test_protocol_zero_hardening.py"

cp "$REPO/aria-protocol-zero-hardening/tests/test_mode_controller_hardening.py" \
   "$REPO/tests/test_mode_controller_hardening.py"
echo "  ✓ tests/test_mode_controller_hardening.py"

# ── 4. Run tests ──────────────────────────────────────────────────────────────
echo ""
echo "=== Running protocol zero tests ==="
cd "$REPO"
.venv/bin/python -m pytest tests/test_protocol_zero_hardening.py -v --tb=short

echo ""
echo "=== Running mode controller hardening tests ==="
.venv/bin/python -m pytest tests/test_mode_controller_hardening.py -v --tb=short

echo ""
echo "=== M64 protocol-zero-hardening applied ==="
echo "  mode_controller.py: schedule injection failure now emits 'schedule-inject-error-d'."
echo "  loop.py: git-reflect-d doctrine comment added."
echo "  22 new tests covering: arm/disarm/HALT file/signal/concurrent/poison cascade."
