#!/usr/bin/env bash
# apply_bloodwork.sh — install Gym #6: clear the sentinel board honestly.
#
# (a) locator ERROR (missing aegis dir): payload aegis/bootstrap.py +
#     doctor.py check_aegis(), plus a one-time real bootstrap at the end
#     of this script so the error clears immediately.
# (b) conformance 27x kill-switch-documented: honest docstring lines in the
#     12 live sentinel modules (real env var for the 8 registry sentinels,
#     truthful "none" for the 4 pre-registry ones) + rule scoped to src/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-bloodwork"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-bloodwork apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
for f in doctor.py stewardship/conformance_sentinel.py \
         temporal_sentinel.py integrity_sentinel.py skill_sentinel.py workflow_sentinel.py \
         stewardship/godtier_sentinel.py stewardship/resilience_sentinel.py \
         stewardship/peig_sentinel.py stewardship/tribunal_sentinel.py \
         stewardship/atoms_compact_sentinel.py stewardship/schedule_sentinel.py \
         stewardship/cache_sentinel.py stewardship/glyph_sentinel.py; do
  [[ -f "$SRC/$f" ]] || { echo "ERROR: $SRC/$f not found."; exit 1; }
  cp "$SRC/$f" "$BACKUP_DIR/$(basename "$f").bak"
done

echo "→ Patching (14 files, anchored, idempotent)..."
"$VENV_PY" - "$STAGING" "$SRC" <<'PYEOF'
import sys
from pathlib import Path

staging, src = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import (
    KILL_SWITCH_LINES, PatchError,
    patch_conformance, patch_doctor, patch_kill_switch_doc,
)

def _sentinel_path(basename: str) -> Path:
    p = src / basename
    return p if p.exists() else src / "stewardship" / basename

try:
    for basename in sorted(KILL_SWITCH_LINES):
        path = _sentinel_path(basename)
        text = path.read_text(encoding="utf-8")
        new_text, changed = patch_kill_switch_doc(basename, text)
        if changed:
            path.write_text(new_text, encoding="utf-8")
            print(f"  ✓ {basename}")
        else:
            print(f"  SKIP: {basename} (already documents SOV_NO_)")

    for name, path, fn in [
        ("conformance_sentinel.py", src / "stewardship" / "conformance_sentinel.py", patch_conformance),
        ("doctor.py", src / "doctor.py", patch_doctor),
    ]:
        text = path.read_text(encoding="utf-8")
        new_text, changed = fn(text)
        if changed:
            path.write_text(new_text, encoding="utf-8")
            print(f"  ✓ {name}")
        else:
            print(f"  SKIP: {name}")
except PatchError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF

echo "→ Copying aegis/bootstrap.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/aegis/bootstrap.py" "$SRC/aegis/bootstrap.py"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$SRC/doctor.py" "$SRC/stewardship/conformance_sentinel.py" "$SRC/aegis/bootstrap.py"
echo "  ✓ py_compile clean"

cp "$STAGING/tests/test_bloodwork_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: bloodwork_live (new), conformance + doctor + locator (pre-existing)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_bloodwork_live.py" \
  "$REPO_ROOT/tests/test_sentinel_crown.py" \
  "$REPO_ROOT/tests/test_conformance_sentinel.py" \
  "$REPO_ROOT/tests/test_doctor_ollama.py" \
  -q

echo "→ One-time real bootstrap (clears the live locator error now, not at next doctor run)..."
"$VENV_PY" -c "
from sovereign_agent.config import SETTINGS
from sovereign_agent.aegis.bootstrap import ensure_aegis_bootstrap
info = ensure_aegis_bootstrap(SETTINGS.paths.data_dir)
print('  ✓', info)
"

echo "=== aria-bloodwork applied. Reversible: restore the 14 files from $BACKUP_DIR (aegis dir/key are additive) 💛 ==="
