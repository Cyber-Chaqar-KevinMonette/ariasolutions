#!/usr/bin/env bash
# apply_people_health_privacy.sh — People-Health round PH3: retrieval
# privacy + real registration + doctor sync.
# guard → backup → patch (mem_channels/__init__.py registration,
# retrieval/filter.py privacy gate, doctor.py channel count — all
# in-place edits, no new payload) → compile → tests (0 skips expected
# post-patch).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-people-health-privacy"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-people-health-privacy apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$SRC/mem_channels/__init__.py" "$BACKUP_DIR/mem_channels_init.py.bak"
cp "$SRC/retrieval/filter.py" "$BACKUP_DIR/filter.py.bak"
cp "$SRC/doctor.py" "$BACKUP_DIR/doctor.py.bak"

# anchored, idempotent patches (no new payload files this round)
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
"$VENV_PY" -m py_compile "$SRC/mem_channels/__init__.py" "$SRC/retrieval/filter.py" "$SRC/doctor.py"
"$VENV_PY" -c "
from sovereign_agent import mem_channels
from sovereign_agent.channels import list_channels
names = {spec.name for spec in list_channels()}
assert 'people_health' in names
from sovereign_agent.retrieval import filter as filter_mod
assert 'people_health' in filter_mod._PRIVATE_CHANNELS
from sovereign_agent import doctor
result = doctor.check_channels()
assert result.level == 'ok', result.detail
print(f'  ✓ people_health registered ({len(names)} channels total); '
      f'privacy-gated; sov doctor channel check: {result.level}')"

# promote the live tests + run them; post-patch this file must run with
# ZERO skips (the skips only exist pre-apply)
cp "$STAGING/tests/test_people_health_privacy.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_people_health_privacy.py" -q -rs | tee /tmp/people_health_privacy_pytest.out
if grep -q "SKIPPED" /tmp/people_health_privacy_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi

echo "=== aria-people-health-privacy applied. Reversible: backups at $BACKUP_DIR 💛 ==="
