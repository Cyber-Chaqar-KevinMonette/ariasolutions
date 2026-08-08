#!/usr/bin/env bash
# apply_quality_wing.sh — Quality round Q5: proving-ground wing + round close-out.
# guard → backup → copy payload (quality_wing.py) → patch (runner.py wiring,
# GOD_TIER_STANDARD.md, god_tier_floor.json) → compile → tests (0 skips
# expected post-patch) → full suite + smoke gates as the round's own close-out.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-quality-wing"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-quality-wing apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR/scripts/lib"
cp "$SRC/proving_ground/runner.py" "$BACKUP_DIR/runner.py.bak"
cp "$REPO_ROOT/GOD_TIER_STANDARD.md" "$BACKUP_DIR/GOD_TIER_STANDARD.md.bak"
cp "$REPO_ROOT/scripts/lib/god_tier_floor.json" "$BACKUP_DIR/scripts/lib/god_tier_floor.json.bak"

# 1. new payload file (a new submodule inside the already-live
#    proving_ground/ package)
cp "$STAGING/payload/src/sovereign_agent/proving_ground/quality_wing.py" \
  "$SRC/proving_ground/"

# 2. anchored, idempotent patches
"$VENV_PY" - "$STAGING" "$SRC" "$REPO_ROOT" <<'PYEOF'
import sys
from pathlib import Path
staging, src, repo = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(staging))
from patcher import ALL_PATCHES, DOC_PATCHES, FLOOR_JSON_PATCHES

for rel, fn in ALL_PATCHES.items():
    path = src / rel
    text = path.read_text(encoding="utf-8")
    new, changed = fn(text)
    if changed:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ {rel}")
    else:
        print(f"  SKIP {rel} (already patched)")

for rel, fn in DOC_PATCHES.items():
    path = repo / rel
    text = path.read_text(encoding="utf-8")
    new, changed = fn(text)
    if changed:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ {rel}")
    else:
        print(f"  SKIP {rel} (already patched)")

for rel, fn in FLOOR_JSON_PATCHES.items():
    path = repo / "scripts" / rel
    text = path.read_text(encoding="utf-8")
    new, changed = fn(text)
    if changed:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ scripts/{rel}")
    else:
        print(f"  SKIP scripts/{rel} (already patched)")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$SRC/proving_ground/runner.py" "$SRC/proving_ground/quality_wing.py"
"$VENV_PY" -c "
import json
json.load(open('$REPO_ROOT/scripts/lib/god_tier_floor.json'))
from sovereign_agent.proving_ground import runner
assert runner.SUITE_VERSION == 'v4'
print('  ✓ runner.py wired; SUITE_VERSION == v4; floor json still valid JSON')"

# 3. promote the live tests + run them; post-patch this file must run with
#    ZERO skips (the skips only exist pre-apply)
cp "$STAGING/tests/test_quality_wing_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_quality_wing_live.py" -q -rs | tee /tmp/quality_wing_pytest.out
if grep -q "SKIPPED" /tmp/quality_wing_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi

echo "→ Round close-out: the full offline proving suite..."
"$VENV_PY" -c "
import asyncio
from sovereign_agent.proving_ground import run_offline_suite
result = asyncio.run(run_offline_suite())
failed = {k: v for k, v in result.tasks.items() if not v['pass']}
assert not failed, failed
assert result.suite == 'v4'
print(f'  ✓ offline suite: {len(result.tasks)} task(s), all pass, suite={result.suite}')"

echo "=== aria-quality-wing applied. Reversible: backups at $BACKUP_DIR 💛 ==="
echo "→ Round close-out still needed by hand: full pytest suite, floor_check,"
echo "  sov truth, both smoke gates — then commit."
