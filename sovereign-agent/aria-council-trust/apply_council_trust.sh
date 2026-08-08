#!/usr/bin/env bash
# apply_council_trust.sh — Stage M94: Council Trust Ledger (witnessing track record)
#
# What this applies:
#   1. src/sovereign_agent/quantum/trust.py — the ledger
#   2. src/sovereign_agent/tools/council_trust_tools.py — council_record_outcome (T1), council_calibration (T0)
#   3. tools/__init__.py: imports + __all__
#   4. quantum_consult_tool.py: auto-log each consult + return consult_id
#   5. Copies test into tests/
#
# The non-classical council earns trust by being VERIFIED against reality. Advisory; the only writes
# are the trust ledger. Requires M89. Reversibility: backups at aria-council-trust/backups/.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-council-trust"
BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"
CONSULT="$REPO_ROOT/src/sovereign_agent/tools/quantum_consult_tool.py"

echo "=== M94 Council Trust Ledger Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then
    echo "ERROR: sovereign cockpit is running. Stop it first."; exit 1
fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: .venv/bin/python not found."; exit 1; fi

mkdir -p "$BACKUP_DIR"
cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"
cp "$CONSULT" "$BACKUP_DIR/quantum_consult_tool.py.bak"
echo "Backed up tools/__init__.py + quantum_consult_tool.py → $BACKUP_DIR"

cp "$STAGING/payload/src/sovereign_agent/quantum/trust.py" "$REPO_ROOT/src/sovereign_agent/quantum/"
cp "$STAGING/payload/src/sovereign_agent/tools/council_trust_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied trust.py + council_trust_tools.py"

# ── Patch tools/__init__.py ──────────────────────────────────────────────────
"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()
if "# council-trust-import-d" in text:
    print("SKIP: tools init already patched")
else:
    anchor = "from .quantum_evolve_tool import QuantumEvolveTool"
    line = [l for l in text.splitlines() if anchor in l]
    if not line:
        # fall back to any quantum tool import
        anchor = "from .quantum_consult_tool import QuantumConsultTool"
        line = [l for l in text.splitlines() if anchor in l]
    a = line[0]
    text = text.replace(a, a + "\nfrom .council_trust_tools import CouncilRecordOutcomeTool, CouncilCalibrationTool  # council-trust-import-d", 1)
    # __all__
    if '"QuantumConsultTool",  # quantum-mode-all-d' in text:
        text = text.replace('"QuantumConsultTool",  # quantum-mode-all-d',
                            '"QuantumConsultTool",  # quantum-mode-all-d\n    "CouncilRecordOutcomeTool",  # council-trust-all-d\n    "CouncilCalibrationTool",', 1)
    p.write_text(text)
    print("Patched tools/__init__.py (council trust tools)")
PYEOF

# ── Patch quantum_consult_tool.py — auto-log + return consult_id ──────────────
"$VENV_PY" - "$CONSULT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()
if "# council-trust-log-d" in text:
    print("SKIP: consult auto-log already patched")
else:
    anchor = "        return ToolResult(ok=True, output=result, metadata={\"source\": \"quantum_consult\"})"
    if anchor not in text:
        print("ERROR: consult return anchor not found", file=sys.stderr); sys.exit(1)
    block = (
        "        # council-trust-log-d — log this consult so its outcome can be verified later\n"
        "        try:\n"
        "            from sovereign_agent.config import SETTINGS\n"
        "            from sovereign_agent.quantum.trust import log_consult\n"
        "            _logged = log_consult(SETTINGS.paths.data_dir, question=result[\"question\"],\n"
        "                                  lean=result[\"lean\"], disposition=result[\"disposition\"],\n"
        "                                  coherence=result.get(\"self_coherence\", 0.0))\n"
        "            result[\"consult_id\"] = _logged[\"consult_id\"]\n"
        "        except Exception:\n"
        "            pass\n"
    )
    text = text.replace(anchor, block + anchor, 1)
    p.write_text(text)
    print("Patched quantum_consult_tool.py (auto-log + consult_id)")
PYEOF

echo ""
echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT/src/sovereign_agent/quantum/trust.py" \
  "$REPO_ROOT/src/sovereign_agent/tools/council_trust_tools.py" "$TOOLS_INIT" "$CONSULT"
echo "  ✓ compiles cleanly"

cp "$STAGING/tests/test_council_trust.py" "$REPO_ROOT/tests/test_council_trust.py"
echo "Copied test_council_trust.py → tests/"

echo ""
echo "Running council trust tests..."
"$VENV_PY" -m pytest tests/test_council_trust.py -q

echo ""
echo "=== M94 Council Trust Ledger applied successfully ==="
echo "The council now logs its advice and earns trust by being verified. council_calibration to read."
