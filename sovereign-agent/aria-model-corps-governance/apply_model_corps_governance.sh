#!/usr/bin/env bash
# apply_model_corps_governance.sh — Model Corps round MC3-MC6: the persisted
# registry ledger, the standing sentinel, the mechanically-scored eval +
# gate, and the optional non-classical confidence tie-in.
#
# guard (cockpit stopped + venv present) → backup touched files → copy
# payload (model_corps_governance/ + stewardship/model_corps_sentinel.py) →
# patch stewardship/__init__.py (anchored, idempotent) → py_compile → copy
# tests → run tests → run one real registry snapshot + eval pass (seeds the
# ledgers so latest_registry()/latest_eval() aren't empty on first look).
# Reversible: backups under aria-model-corps-governance/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-model-corps-governance"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
STEWARDSHIP_INIT="$REPO_ROOT/src/sovereign_agent/stewardship/__init__.py"

echo "=== aria-model-corps-governance apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"; cp "$STEWARDSHIP_INIT" "$BACKUP_DIR/stewardship_init.py.bak"

# 1. copy payload: the new model_corps_governance package + the new sentinel
#    file inside the EXISTING stewardship package
mkdir -p "$REPO_ROOT/src/sovereign_agent/model_corps_governance"
cp "$STAGING"/payload/src/sovereign_agent/model_corps_governance/*.py \
  "$REPO_ROOT/src/sovereign_agent/model_corps_governance/"
cp "$STAGING/payload/src/sovereign_agent/stewardship/model_corps_sentinel.py" \
  "$REPO_ROOT/src/sovereign_agent/stewardship/"

# 2. register the sentinel (anchored on wellbeing_sentinel's tail import, idempotent)
"$VENV_PY" - "$STEWARDSHIP_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1])
t = p.read_text(encoding="utf-8")
if "model-corps-sentinel-d" in t:
    print("SKIP: already patched")
else:
    anchor = next(l for l in t.splitlines() if "wellbeing-sentinel-d" in l)
    new_line = "from . import model_corps_sentinel as _model_corps_sentinel  # noqa: F401  # model-corps-sentinel-d"
    t = t.replace(anchor, anchor + "\n" + new_line, 1)
    p.write_text(t, encoding="utf-8")
    print("Patched stewardship/__init__.py")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile \
  "$REPO_ROOT"/src/sovereign_agent/model_corps_governance/*.py \
  "$REPO_ROOT/src/sovereign_agent/stewardship/model_corps_sentinel.py" \
  "$STEWARDSHIP_INIT"

# 3. promote + run tests
cp "$STAGING/tests/test_model_corps_governance.py" "$REPO_ROOT/tests/"
echo "→ Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_model_corps_governance.py" -q

# 4. seed the ledgers for real: one registry snapshot + one live eval pass
#    (this actually calls each aria-<role> model over Ollama — real
#    machinery, not a fixture; takes roughly 1-3 minutes)
echo "→ Seeding the registry ledger..."
"$VENV_PY" -c "
from sovereign_agent.model_corps_governance import record_registry_snapshot
snap = record_registry_snapshot()
print(f'  snapshot {snap.snapshot_id}: {len(snap.entries)} role(s)')"

echo "→ Running the first live model-corps eval pass (calls all 6 aria-<role> models)..."
"$VENV_PY" -c "
from sovereign_agent.model_corps_governance import run_corps_eval, gate
result = run_corps_eval()
print(f'  eval pass {result.pass_id}: value={result.value:.2f}')
for r in result.roles:
    print(f'    {r.role}: {r.cases_passed}/{r.cases_run}' + (f' — failed: {r.failures}' if r.failures else ''))
verdict = gate()
print(f'  gate verdict: {verdict.verdict} ({verdict.reason})')"

echo "=== aria-model-corps-governance applied. Reversible: backups at $BACKUP_DIR 💛 ==="
