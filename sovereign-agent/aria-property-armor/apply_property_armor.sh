#!/usr/bin/env bash
# apply_property_armor.sh — install Gym #10: Hypothesis property tests.
# Test-only module: promotes one test file. (The one real bug the first
# fuzz pass found — scan_all_exports crashing on unparseable input — was
# fixed directly in scanner_tier_a/scanner.py as a small live bug fix.)
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-property-armor"
VENV_PY="$REPO_ROOT/.venv/bin/python"

echo "=== aria-property-armor apply ==="
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }

cp "$STAGING/tests/test_property_armor_live.py" "$REPO_ROOT/tests/"
echo "Running: property armor (new) + the fuzzed scanners' pre-existing suites..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_property_armor_live.py" \
  "$REPO_ROOT/tests/test_scanner_tier_a.py" \
  "$REPO_ROOT/tests/test_path_scan.py" \
  -q

echo "=== aria-property-armor applied. Reversible: rm tests/test_property_armor_live.py 💛 ==="
