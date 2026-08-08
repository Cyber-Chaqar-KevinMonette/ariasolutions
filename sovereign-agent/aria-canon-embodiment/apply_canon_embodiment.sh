#!/usr/bin/env bash
# apply_canon_embodiment.sh — install the Canon-Embodiment organ (Workstream H2).
#
# Ships the package + registers CanonEmbodimentSentinel via one anchored import in
# stewardship/__init__.py, mirroring D's aria-path-sentinel pattern exactly.
#
# Anatomy: guard (cockpit stopped + venv) → backup stewardship/__init__.py → copy payload →
# idempotent anchored registration → py_compile → copy + run tests → self-check against live repo.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-canon-embodiment"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
STEW_INIT="$REPO_ROOT/src/sovereign_agent/stewardship/__init__.py"
TARGET="$REPO_ROOT/src/sovereign_agent/canon_embodiment"

echo "=== aria-canon-embodiment apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$STEW_INIT" "$BACKUP_DIR/stewardship_init.py.bak"

mkdir -p "$TARGET"
cp "$STAGING"/payload/src/sovereign_agent/canon_embodiment/*.py "$TARGET/"

"$VENV_PY" - "$STEW_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text(encoding="utf-8")
if "canon-embodiment-import-d" in t:
    print("SKIP: stewardship already registers CanonEmbodimentSentinel")
else:
    anchor = next(l for l in t.splitlines() if "resilience-sentinel-d" in l)
    add = ("from sovereign_agent.canon_embodiment.sentinel import CanonEmbodimentSentinel "
           "as _canon_embodiment_sentinel  # noqa: F401  # canon-embodiment-import-d")
    t = t.replace(anchor, anchor + "\n" + add, 1)
    p.write_text(t, encoding="utf-8")
    print("Patched stewardship/__init__.py — CanonEmbodimentSentinel registered")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$TARGET"/*.py "$STEW_INIT"
echo "  ✓ py_compile clean"

cp "$STAGING/tests/test_canon_embodiment.py" "$REPO_ROOT/tests/"
echo "Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_canon_embodiment.py" -q

echo "→ Real-repo embodiment check..."
"$VENV_PY" -c "
from pathlib import Path
from sovereign_agent.canon_embodiment import find_references
report = find_references(Path('.'))
print(f'  {report.summary()}')
"

echo "=== aria-canon-embodiment applied. Reversible: backup at $BACKUP_DIR/stewardship_init.py.bak 💛 ==="
