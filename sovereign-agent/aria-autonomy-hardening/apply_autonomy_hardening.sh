#!/usr/bin/env bash
# apply_autonomy_hardening.sh — Apply M78: autonomy execution resilience tests
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="$REPO/aria-autonomy-hardening"

echo "=== M78: Autonomy & Execution Resilience Tests ==="

# Copy test files
echo "→ Copying tests..."
cp "$STAGING/tests/test_shell_handler.py"          "$REPO/tests/test_shell_handler.py"
cp "$STAGING/tests/test_dream_runner.py"           "$REPO/tests/test_dream_runner.py"
cp "$STAGING/tests/test_natural_language_handler.py" "$REPO/tests/test_natural_language_handler.py"

# Run tests
echo "→ Running shell handler tests..."
cd "$REPO"
.venv/bin/python -m pytest tests/test_shell_handler.py -v --tb=short

echo "→ Running dream runner tests..."
.venv/bin/python -m pytest tests/test_dream_runner.py -v --tb=short

echo "→ Running NL handler tests..."
.venv/bin/python -m pytest tests/test_natural_language_handler.py -v --tb=short

echo ""
echo "=== M78 complete ==="
echo "New tests: 7 shell handler + 7 dream runner + 7 NL handler = 21 total"
