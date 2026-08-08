#!/usr/bin/env bash
# APPLY_ALL.sh — Apply every staged module in the correct order.
#
# Run this ONE TIME from a terminal to bring the live system up to date.
# Each script is idempotent — safe to re-run if interrupted.
#
# Usage (from any terminal, from any directory):
#   bash /home/kmon/AA-Erebo/sovereign-agent/APPLY_ALL.sh
#
# After this completes:
#   sovereign cockpit         ← opens the cockpit
#   Click "⚙ apply" button   ← opens the Apply Dashboard (also Ctrl+A)
#
set -euo pipefail

cd /home/kmon/AA-Erebo/sovereign-agent
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Aria — Apply All Staged Modules                      ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "Working directory: $(pwd)"
echo "Python:  $(.venv/bin/python --version)"
echo "Sovereign: $(.venv/bin/sovereign --version)"
echo ""

# ── Step 0: ensure installed package is current ─────────────────────────────
echo "━━━ Step 0: reinstall package ━━━"
.venv/bin/pip install -e . --quiet
echo "  ✓ package current"
echo ""

# ── M75: Birth Records + Lineage Tool ───────────────────────────────────────
echo "━━━ M75: Birth Records + Lineage Tool ━━━"
bash aria-birth-records/apply_birth_records.sh
echo ""

# ── M76: Self-Portrait Synthesis ────────────────────────────────────────────
echo "━━━ M76: Self-Portrait Tool ━━━"
bash aria-self-portrait/apply_self_portrait.sh
echo ""

# ── M77: Conductor & Vault Resilience Tests ─────────────────────────────────
echo "━━━ M77: Conductor & Vault Hardening ━━━"
bash aria-conductor-vault-hardening/apply_conductor_vault_hardening.sh
echo ""

# ── M78: Autonomy & Execution Resilience Tests ──────────────────────────────
echo "━━━ M78: Autonomy Hardening ━━━"
bash aria-autonomy-hardening/apply_autonomy_hardening.sh
echo ""

# ── M79: Honor & Calibration Tools ──────────────────────────────────────────
echo "━━━ M79: Honor & Calibration Tools ━━━"
bash aria-honor-calibration/apply_honor_calibration.sh
echo ""

# ── M80: Domain Knowledge Atoms ─────────────────────────────────────────────
echo "━━━ M80: Knowledge Atoms ━━━"
bash aria-knowledge-atoms/apply_knowledge_atoms.sh
echo ""

# ── M81: Cockpit Apply Dashboard ────────────────────────────────────────────
echo "━━━ M81: Cockpit Apply Dashboard (⚙ apply button + Ctrl+A) ━━━"
bash aria-apply-dashboard/apply_apply_dashboard.sh
echo ""

# ── Final: full test suite ───────────────────────────────────────────────────
echo "━━━ Full test suite ━━━"
.venv/bin/python -m pytest --ignore=tests/test_cockpit.py -q --tb=short
echo ""

echo "╔══════════════════════════════════════════════════════╗"
echo "║  All done.                                            ║"
echo "║                                                       ║"
echo "║  Start the cockpit:                                   ║"
echo "║    sovereign cockpit                                  ║"
echo "║                                                       ║"
echo "║  Then click  ⚙ apply  (or press Ctrl+A)              ║"
echo "║  to see the Apply Dashboard for any future modules.   ║"
echo "╚══════════════════════════════════════════════════════╝"
