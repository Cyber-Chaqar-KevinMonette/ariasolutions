#!/usr/bin/env bash
# apply_authority_fidelity.sh — M65: authority gate fidelity + VRAM lock event
# Idempotent. Safe to re-run.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== M65 Authority Fidelity: gate edge cases + VRAM timeout event ==="

# ── 1. Patch vram.py — emit event on timeout ─────────────────────────────────
VRAM_PY="$REPO/src/sovereign_agent/vram.py"
python3 "$REPO/aria-authority-fidelity/patch_vram.py" "$VRAM_PY"
echo "  ✓ vram.py patched (vram-lock-timeout-d event on timeout)"

# ── 2. Copy test file ─────────────────────────────────────────────────────────
cp "$REPO/aria-authority-fidelity/tests/test_authority_fidelity.py" \
   "$REPO/tests/test_authority_fidelity.py"
echo "  ✓ tests/test_authority_fidelity.py"

# ── 3. Run tests ──────────────────────────────────────────────────────────────
echo ""
echo "=== Running authority fidelity tests ==="
cd "$REPO"
.venv/bin/python -m pytest tests/test_authority_fidelity.py -v --tb=short

echo ""
echo "=== M65 authority-fidelity applied ==="
echo "  authority.py: tier filtering per mode, T3 approval, duplicate registration tested."
echo "  vram.py: VRAM lock timeout now emits 'vram-lock-timeout-d' event before raising."
echo "  15 new tests covering: tier ceiling, AuthorityViolation, VRAM timeout."
