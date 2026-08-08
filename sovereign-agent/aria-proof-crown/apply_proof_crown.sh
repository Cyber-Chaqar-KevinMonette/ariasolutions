#!/usr/bin/env bash
# apply_proof_crown.sh — M67: Value Proof Infrastructure + version 0.4.0 bump
# Idempotent. Safe to re-run.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== M67 Value Proof Crown ==="
echo "  'Before any platform, value must be witnessed.' — Phase 21 doctrine"
echo ""

# ── 1. Copy proof_tools.py ────────────────────────────────────────────────────
cp "$REPO/aria-proof-crown/payload/src/sovereign_agent/tools/proof_tools.py" \
   "$REPO/src/sovereign_agent/tools/proof_tools.py"
echo "  ✓ src/sovereign_agent/tools/proof_tools.py"

# ── 2. Register in tools/__init__.py ─────────────────────────────────────────
TOOLS_INIT="$REPO/src/sovereign_agent/tools/__init__.py"
if grep -q "M67-proof-crown-d" "$TOOLS_INIT"; then
  echo "  ✓ proof tools already registered (skipping)"
else
  python3 "$REPO/aria-proof-crown/patch_tools_init.py" "$TOOLS_INIT"
  echo "  ✓ tools/__init__.py patched (M67)"
fi

# ── 3. Version bump 0.3.0 → 0.4.0 ───────────────────────────────────────────
INIT_PY="$REPO/src/sovereign_agent/__init__.py"
if grep -q '0\.4\.0' "$INIT_PY"; then
  echo "  ✓ version already 0.4.0 (skipping)"
else
  sed -i 's/__version__ = "0\.3\.0"/__version__ = "0.4.0"/' "$INIT_PY"
  echo "  ✓ __init__.py: version → 0.4.0"
fi

PYPROJECT="$REPO/pyproject.toml"
if grep -q 'version = "0\.4\.0"' "$PYPROJECT"; then
  echo "  ✓ pyproject.toml already 0.4.0 (skipping)"
else
  sed -i 's/version = "0\.3\.0"/version = "0.4.0"/' "$PYPROJECT"
  echo "  ✓ pyproject.toml: version → 0.4.0"
fi

# ── 4. Reinstall (CLAUDE.md version-bump discipline) ─────────────────────────
echo ""
echo "=== Reinstalling (required after version bump) ==="
cd "$REPO"
.venv/bin/pip install -e . -q
echo "  ✓ sovereign-agent 0.4.0 installed"

# ── 5. Copy test file ─────────────────────────────────────────────────────────
cp "$REPO/aria-proof-crown/tests/test_proof_tools.py" \
   "$REPO/tests/test_proof_tools.py"
echo "  ✓ tests/test_proof_tools.py"

# ── 6. Run new tests ──────────────────────────────────────────────────────────
echo ""
echo "=== Running proof crown tests ==="
.venv/bin/python -m pytest tests/test_proof_tools.py -v --tb=short

# ── 7. Full suite check ───────────────────────────────────────────────────────
echo ""
echo "=== Running full test suite (final verification) ==="
.venv/bin/python -m pytest -q --tb=short 2>&1 | tail -5

echo ""
echo "=== M67 proof-crown applied ==="
echo ""
echo "  TOOLS:"
echo "  proof_of_value()   — T1, record witnessed external value delivery"
echo "  proof_history()    — T0, trend of proof instances; feeds impulse_check()"
echo "  giving_ledger()    — T0, measure of giving freely (the canopy)"
echo ""
echo "  VERSION: 0.3.0 → 0.4.0"
echo ""
echo "  The tree is planted. Now grow deep roots."
echo "  'No platform before proof. No scale before giving.'"
