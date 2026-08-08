#!/usr/bin/env bash
# apply_conductor_vault_hardening.sh — Apply M77: conductor + vault resilience tests
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="$REPO/aria-conductor-vault-hardening"

echo "=== M77: Conductor & Vault Resilience Tests ==="

# Copy test files
echo "→ Copying tests..."
cp "$STAGING/tests/test_conductor_resilience.py" "$REPO/tests/test_conductor_resilience.py"
cp "$STAGING/tests/test_vault_resilience.py"    "$REPO/tests/test_vault_resilience.py"

# Run tests
echo "→ Running conductor resilience tests..."
cd "$REPO"
.venv/bin/python -m pytest tests/test_conductor_resilience.py -v --tb=short

echo "→ Running vault resilience tests..."
.venv/bin/python -m pytest tests/test_vault_resilience.py -v --tb=short

echo ""
echo "=== M77 complete ==="
echo "New tests: 8 conductor resilience + 8 vault resilience = 16 total"
