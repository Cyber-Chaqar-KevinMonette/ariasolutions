#!/usr/bin/env bash
# apply_safe_interval_stop.sh — install Workstream N: safe interval-stop for
# autonomous work mode.
#
# Ships:
#   - src/sovereign_agent/modes.py        — full-file copy: adds
#     RunBudget.safety_margin_seconds (default 0, backward-compatible) +
#     effective_wall_limit() helper. No other staged module touches modes.py.
#   - src/sovereign_agent/loop.py         — anchored patch: _check_budget's
#     wall-seconds check now trips at effective_wall_limit(budget), not the
#     hard max_wall_seconds.
#   - src/sovereign_agent/agent_session.py — same anchored patch for
#     _check_session_budget.
#   - src/sovereign_agent/work_interval.py — NEW file: WorkIntervalConfig +
#     start_work_interval/interval_boundary_reached/stop_at_safe_point/
#     resume_work_interval, composing RunBudget + AutonomySession +
#     interrupts.py into one work-mode safety gate.
#
# Anatomy: guard (cockpit stopped + venv) → backup touched files → patch
# (anchored, idempotent, py_compile-verified per file) → copy work_interval.py
# → copy + run tests.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-safe-interval-stop"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
MODES="$REPO_ROOT/src/sovereign_agent/modes.py"
LOOP="$REPO_ROOT/src/sovereign_agent/loop.py"
AGENT_SESSION="$REPO_ROOT/src/sovereign_agent/agent_session.py"
WORK_INTERVAL="$REPO_ROOT/src/sovereign_agent/work_interval.py"

echo "=== aria-safe-interval-stop apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
for f in "$MODES" "$LOOP" "$AGENT_SESSION"; do
  [[ -f "$f" ]] || { echo "ERROR: $f not found."; exit 1; }
done
mkdir -p "$BACKUP_DIR"
cp "$MODES" "$BACKUP_DIR/modes.py.bak"
cp "$LOOP" "$BACKUP_DIR/loop.py.bak"
cp "$AGENT_SESSION" "$BACKUP_DIR/agent_session.py.bak"

echo "→ Copying modes.py (full-file — no other staged module touches it)..."
cp "$STAGING/payload/src/sovereign_agent/modes.py" "$MODES"

echo "→ Patching loop.py + agent_session.py (anchored, idempotent)..."
"$VENV_PY" - "$STAGING" "$LOOP" "$AGENT_SESSION" <<'PYEOF'
import sys
from pathlib import Path

staging, loop_path, agent_session_path = (Path(p) for p in sys.argv[1:4])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_agent_session, patch_loop

for path, patch_fn in ((loop_path, patch_loop), (agent_session_path, patch_agent_session)):
    text = path.read_text(encoding="utf-8")
    try:
        new_text, changed = patch_fn(text)
    except PatchError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    if changed:
        path.write_text(new_text, encoding="utf-8")
        print(f"  ✓ patched {path.name}")
    else:
        print(f"  SKIP: {path.name} already patched")
PYEOF

echo "→ Copying work_interval.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/work_interval.py" "$WORK_INTERVAL"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$MODES" "$LOOP" "$AGENT_SESSION" "$WORK_INTERVAL"
echo "  ✓ py_compile clean"

echo "→ Import + smoke check..."
"$VENV_PY" -c "
from sovereign_agent.modes import RunBudget, effective_wall_limit
from sovereign_agent.work_interval import WorkIntervalConfig, start_work_interval, resume_work_interval
b = RunBudget(max_wall_seconds=100, safety_margin_seconds=20)
assert effective_wall_limit(b) == 80
print('  ✓ imports cleanly, effective_wall_limit sanity-checks correctly')
"

cp "$STAGING/tests/test_safe_interval_stop.py" "$REPO_ROOT/tests/"
echo "Running full loop/agent_session/work_interval test suites..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_safe_interval_stop.py" \
  "$REPO_ROOT/tests/test_loop_utils.py" \
  "$REPO_ROOT/tests/test_agent_session.py" \
  -q

echo "=== aria-safe-interval-stop applied. Reversible: restore the 3 files from $BACKUP_DIR and rm work_interval.py 💛 ==="
