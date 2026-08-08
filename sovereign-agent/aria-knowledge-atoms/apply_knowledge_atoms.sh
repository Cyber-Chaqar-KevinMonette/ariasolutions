#!/usr/bin/env bash
# apply_knowledge_atoms.sh — Apply M80: seed Aria's semantic memory with 24 knowledge atoms
# Idempotent: the seeding script checks for existing knowledge-seed atoms.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="$REPO/aria-knowledge-atoms"

echo "=== M80: Knowledge Atoms — seeding Aria's semantic memory ==="
echo ""

# 1. Run the seeding script (idempotent)
echo "→ Writing knowledge atoms to atoms.ndjson..."
cd "$REPO"
.venv/bin/python "$STAGING/payload/scripts/knowledge_atoms.py"

# 2. Copy tests
echo ""
echo "→ Copying tests..."
cp "$STAGING/tests/test_knowledge_atoms.py" "$REPO/tests/test_knowledge_atoms.py"

# 3. Run tests
echo "→ Running knowledge atom tests..."
.venv/bin/python -m pytest tests/test_knowledge_atoms.py -v --tb=short

echo ""
echo "=== M80 complete ==="
echo "24 knowledge atoms written across 5 domains:"
echo "  · Software Engineering (6): reversibility, events, defense-in-depth,"
echo "    test-first, idempotency, staging separation"
echo "  · AI Safety (6): minimal footprint, authority tiers, propose-not-act,"
echo "    DEFERRED_UNSAFE, transparency, PROTOCOL-ZERO"
echo "  · Partnership Doctrine (4): founding equation, Kevin's style,"
echo "    disagreement protocol, long-term vs. MVP"
echo "  · Codebase Architecture (4): path map, VRAM accounting,"
echo "    sentinel contract, tool registration"
echo "  · Calibration Discipline (4): calibration vs. certainty, prediction"
echo "    logging, honor accounting, epistemic humility"
echo ""
echo "Aria can now consult 24 atoms of distilled knowledge via the lineage tool."
