#!/usr/bin/env bash
# apply_dual_inbox.sh — install Workstream O: dual inbox (Aria -> human,
# human -> Aria).
#
# Ships:
#   - src/sovereign_agent/workflow/requests.py — full-file replacement.
#     Adds `direction` (to_human|to_aria, default to_human — every existing
#     row's meaning preserved exactly) plus send_to_human()/tell_aria()/
#     list_for_aria() convenience methods. Self-contained, low risk.
#   - src/sovereign_agent/cli.py — anchored span replacement of the
#     `requests_app` typer sub-app only (NOT a full-file replace — cli.py is
#     10,949 lines and evolves fast). Adds `--direction` filter to `list`
#     and a new `tell` command for the reverse direction.
#   - src/sovereign_agent/cockpit/app.py — anchored span replacement of
#     `_refresh_inbox_pane`'s method body only. Splits the pane into
#     "waiting on you" (to_human, unchanged in substance) and "-> Aria"
#     (to_aria, new).
#   - src/sovereign_agent/tools/__init__.py — anchored import + __all__
#     patch (both in one step, per the lesson from H4/L about missing
#     __all__ exports being a real, recurring bug class).
#   - src/sovereign_agent/tools/inbox_tools.py — NEW file: SendToHumanTool,
#     ReadInboxTool.
#
# Anatomy: guard (cockpit stopped + venv) → backup all 4 touched files →
# patch/copy (anchored, idempotent, py_compile-verified) → copy tests → run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-dual-inbox"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
REQUESTS="$REPO_ROOT/src/sovereign_agent/workflow/requests.py"
CLI="$REPO_ROOT/src/sovereign_agent/cli.py"
APP="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"
INBOX_TOOLS="$REPO_ROOT/src/sovereign_agent/tools/inbox_tools.py"

echo "=== aria-dual-inbox apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
for f in "$REQUESTS" "$CLI" "$APP" "$TOOLS_INIT"; do
  [[ -f "$f" ]] || { echo "ERROR: $f not found."; exit 1; }
done
mkdir -p "$BACKUP_DIR"
cp "$REQUESTS" "$BACKUP_DIR/requests.py.bak"
cp "$CLI" "$BACKUP_DIR/cli.py.bak"
cp "$APP" "$BACKUP_DIR/app.py.bak"
cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

echo "→ Copying requests.py (full-file — self-contained, adds 'direction')..."
cp "$STAGING/payload/src/sovereign_agent/workflow/requests.py" "$REQUESTS"

echo "→ Patching cli.py, app.py, tools/__init__.py (anchored, idempotent)..."
"$VENV_PY" - "$STAGING" "$CLI" "$APP" "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path

staging, cli_path, app_path, tools_init_path = (Path(p) for p in sys.argv[1:5])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_app_inbox, patch_cli, patch_tools_init

new_cli_block = (staging / "payload" / "cli_requests_block.py").read_text(encoding="utf-8")
new_app_block = (staging / "payload" / "app_inbox_pane_block.py").read_text(encoding="utf-8")

jobs = [
    (cli_path, lambda t: patch_cli(t, new_cli_block)),
    (app_path, lambda t: patch_app_inbox(t, new_app_block)),
    (tools_init_path, patch_tools_init),
]
for path, patch_fn in jobs:
    text = path.read_text(encoding="utf-8")
    try:
        new_text, changed = patch_fn(text)
    except PatchError as e:
        print(f"ERROR: {path.name}: {e}", file=sys.stderr)
        sys.exit(1)
    if changed:
        path.write_text(new_text, encoding="utf-8")
        print(f"  ✓ patched {path.name}")
    else:
        print(f"  SKIP: {path.name} already patched")
PYEOF

echo "→ Copying inbox_tools.py (new file)..."
cp "$STAGING/payload/src/sovereign_agent/tools/inbox_tools.py" "$INBOX_TOOLS"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REQUESTS" "$CLI" "$APP" "$TOOLS_INIT" "$INBOX_TOOLS"
echo "  ✓ py_compile clean"

echo "→ Import + smoke check..."
"$VENV_PY" -c "
from sovereign_agent.workflow.requests import RequestStore, DIRECTION_TO_HUMAN, DIRECTION_TO_ARIA
from sovereign_agent.tools.inbox_tools import SendToHumanTool, ReadInboxTool
from sovereign_agent.cockpit import CockpitApp
print('  ✓ imports cleanly (requests, inbox_tools, cockpit)')
"

cp "$STAGING/tests/test_dual_inbox.py" "$REPO_ROOT/tests/"
echo "Running test suites: dual_inbox (new), requests (pre-existing), tools __all__ sanity..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_dual_inbox.py" \
  "$REPO_ROOT/tests/test_requests.py" \
  -q

echo "=== aria-dual-inbox applied. Reversible: restore the 4 files from $BACKUP_DIR and rm tools/inbox_tools.py 💛 ==="
