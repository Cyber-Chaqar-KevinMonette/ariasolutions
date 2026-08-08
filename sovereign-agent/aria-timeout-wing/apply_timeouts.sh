#!/usr/bin/env bash
# apply_timeouts.sh — Timeout round T4: proving wing wiring + close-out.
# guard → backup → copy payload (timeout_wing.py) → patch (runner.py
# wiring) → compile → tests (0 skips expected post-patch) → full offline
# suite as its own final check.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-timeout-wing"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-timeout-wing apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/proving_ground/runner.py" "$BACKUP_DIR/runner.py.bak"

cp "$STAGING/payload/src/sovereign_agent/proving_ground/timeout_wing.py" "$SRC/proving_ground/"

"$VENV_PY" - "$STAGING" "$SRC" <<'PYEOF'
import sys
from pathlib import Path
staging, src = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import ALL_PATCHES

for rel, fn in ALL_PATCHES.items():
    path = src / rel
    text = path.read_text(encoding="utf-8")
    new, changed = fn(text)
    if changed:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ {rel}")
    else:
        print(f"  SKIP {rel} (already patched)")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$SRC/proving_ground/runner.py" "$SRC/proving_ground/timeout_wing.py"
"$VENV_PY" -c "
from sovereign_agent.proving_ground import runner
assert runner.SUITE_VERSION == 'v8'
print('  ✓ runner.py wired; SUITE_VERSION == v8')"

cp "$STAGING/tests/test_timeout_wing_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_timeout_wing_live.py" -q -rs | tee /tmp/timeout_wing_pytest.out
if grep -q "SKIPPED" /tmp/timeout_wing_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi

echo "→ Round close-out: the full offline proving suite..."
"$VENV_PY" -c "
import asyncio
from sovereign_agent.proving_ground import run_offline_suite
result = asyncio.run(run_offline_suite())
failed = {k: v for k, v in result.tasks.items() if not v['pass']}
assert not failed, failed
assert result.suite == 'v8'
print(f'  ✓ offline suite: {len(result.tasks)} task(s), all pass, suite={result.suite}')"

echo "=== aria-timeout-wing applied. Reversible: backups at $BACKUP_DIR 💛 ==="
