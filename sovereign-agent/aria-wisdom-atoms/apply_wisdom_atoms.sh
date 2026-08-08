#!/usr/bin/env bash
# apply_wisdom_atoms.sh — Apply M83: seed Aria's operational wisdom atoms
# Idempotent: the seeding script checks for existing wisdom-seed atoms.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="$REPO/aria-wisdom-atoms"

echo "=== M83: Wisdom Atoms — Aria's operational self-knowledge ==="
echo ""

# 1. Run the seeding script
echo "→ Writing wisdom atoms to atoms.ndjson..."
cd "$REPO"
.venv/bin/python "$STAGING/payload/scripts/wisdom_atoms.py"

# 2. Copy tests
echo ""
echo "→ Copying tests..."
cp "$STAGING/tests/test_wisdom_atoms.py" "$REPO/tests/test_wisdom_atoms.py"

# 3. Run tests
echo "→ Running wisdom atom tests..."
.venv/bin/python -m pytest tests/test_wisdom_atoms.py -v --tb=short

echo ""
echo "=== M83 complete ==="
echo "12 operational wisdom atoms written:"
echo "  · Kevin's trust-and-disappear pattern"
echo "  · Stage and note; never block on apply"
echo "  · Staging tests are the gate: passing = done"
echo "  · Pre-apply injection: importlib.util.spec_from_file_location"
echo "  · Fix the test expectation when reality disagrees"
echo "  · Import markers enable idempotent apply scripts"
echo "  · When APPLIED is uncertain: grep, don't guess"
echo "  · Atom confidence ladder: match confidence to evidence type"
echo "  · Self-model loop: lineage → self-portrait → weekly reflection"
echo "  · Staged module lifecycle: build → test → note → apply → commit"
echo "  · When blocked: a clarifying question costs less than a wrong change"
echo "  · Boring reliability > clever capability"
