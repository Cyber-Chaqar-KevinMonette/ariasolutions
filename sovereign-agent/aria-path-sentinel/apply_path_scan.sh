#!/usr/bin/env bash
# apply_path_scan.sh — promote aria-path-sentinel into live src/.
#
# Ships:
#   • src/sovereign_agent/path_scan/      — the scanner package (+ __main__ CLI gate)
#   • registers PathSentinel              — one anchored import in stewardship/__init__.py
#   • wires safe_apply step-0 gate        — `python -m sovereign_agent.path_scan <slug>` before every apply
#
# Anatomy: guard (cockpit stopped + venv) → backup touched files → copy payload →
#          patch registration (anchored, idempotent) → wire gate (idempotent) → py_compile →
#          copy tests → run tests.  Reversible: backups under aria-path-sentinel/backups/<ts>.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-path-sentinel"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
STEW_INIT="$REPO_ROOT/src/sovereign_agent/stewardship/__init__.py"
SAFE_APPLY="$REPO_ROOT/scripts/safe_apply.sh"

echo "=== aria-path-sentinel apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$STEW_INIT" "$BACKUP_DIR/stewardship_init.py.bak"
[[ -f "$SAFE_APPLY" ]] && cp "$SAFE_APPLY" "$BACKUP_DIR/safe_apply.sh.bak"

# 1. copy payload package
mkdir -p "$REPO_ROOT/src/sovereign_agent/path_scan"
cp "$STAGING"/payload/src/sovereign_agent/path_scan/*.py "$REPO_ROOT/src/sovereign_agent/path_scan/"

# 2. register the sentinel (anchored + idempotent) — side-effect import in stewardship/__init__.py
"$VENV_PY" - "$STEW_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text(encoding="utf-8")
if "path-sentinel-import-d" in t:
    print("SKIP: stewardship already registers PathSentinel")
else:
    anchor = next(l for l in t.splitlines() if "resilience-sentinel-d" in l)
    add = "from sovereign_agent.path_scan.sentinel import PathSentinel as _path_sentinel  # noqa: F401  # path-sentinel-import-d"
    t = t.replace(anchor, anchor + "\n" + add, 1)
    p.write_text(t, encoding="utf-8")
    print("Patched stewardship/__init__.py — PathSentinel registered")
PYEOF

# 3. wire the false-path gate into safe_apply step 0 (idempotent)
if [[ -f "$SAFE_APPLY" ]]; then
  "$VENV_PY" - "$SAFE_APPLY" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text(encoding="utf-8")
if "path-scan-gate-d" in t:
    print("SKIP: safe_apply already wires the path-scan gate")
else:
    # Insert right after the shebang/`set -euo pipefail` line so it runs first.
    lines = t.splitlines()
    idx = next((i for i, l in enumerate(lines) if l.strip().startswith("set -")), 0)
    gate = [
        '',
        '# step 0 — false-path / anti-ghost / anti-zombie gate  # path-scan-gate-d',
        'SLUG="${1:-}"; SLUG="${SLUG#aria-}"',
        'if [[ -n "$SLUG" ]] && [[ "${*}" != *--no-path-scan* ]]; then',
        '  if ! "$(dirname "$0")/../.venv/bin/python" -m sovereign_agent.path_scan "$SLUG"; then',
        '    echo "⛔ path-scan: blocking false/ghost path in aria-$SLUG (override: --no-path-scan)"; exit 1',
        '  fi',
        'fi',
    ]
    lines[idx+1:idx+1] = gate
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Patched safe_apply.sh — path-scan gate at step 0")
PYEOF
fi

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/path_scan/*.py "$STEW_INIT"

# 4. copy + run tests
mkdir -p "$REPO_ROOT/tests"
cp "$STAGING/tests/test_path_scan.py" "$REPO_ROOT/tests/"
echo "Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT"/tests/test_path_scan.py -q || true

echo "=== aria-path-sentinel applied. Reversible: backups at $BACKUP_DIR 💛 ==="
echo "    try it:  $VENV_PY -m sovereign_agent.path_scan"
