#!/usr/bin/env bash
# apply_golden_path_smoke.sh — install the Golden Path smoke test: the
# plan's own standing "finished, complete, whole" end-to-end gate.
#
# Ships: scripts/golden_path_smoke.sh — a NEW file, not a patch to
# anything existing. Boots the agent loop headless (no TUI) via `sov run`,
# sends one representative operator turn, and asserts: no unhandled
# exception, a coherent (non-empty) final response, and events.jsonl
# growing (the event stream is alive).
#
# This apply also runs the script for REAL once (Ollama is reachable on
# this machine) as the final proof — not just a copy-and-hope.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-golden-path-smoke"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SCRIPT="$REPO_ROOT/scripts/golden_path_smoke.sh"

echo "=== aria-golden-path-smoke apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
[[ -f "$SCRIPT" ]] && cp "$SCRIPT" "$BACKUP_DIR/golden_path_smoke.sh.bak"

echo "→ Installing scripts/golden_path_smoke.sh..."
cp "$STAGING/payload/scripts/golden_path_smoke.sh" "$SCRIPT"
chmod +x "$SCRIPT"
echo "  ✓ installed"

echo "→ Syntax check..."
bash -n "$SCRIPT"
echo "  ✓ valid bash"

# NOTE: no shadow-copy dance needed for this module's tests — the script
# is plain bash invoked via subprocess, no Python import/sys.modules risk
# at all (the exact class of bug this session hit repeatedly elsewhere
# doesn't apply here).
cp "$STAGING/tests/test_golden_path_smoke_live.py" "$REPO_ROOT/tests/"
echo "Running structural tests (always) + the real end-to-end run (Ollama is reachable here)..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_golden_path_smoke_live.py" -q

echo
echo "→ Running the actual Golden Path gate now, as the final proof..."
bash "$SCRIPT"

echo "=== aria-golden-path-smoke applied. Reversible: restore scripts/golden_path_smoke.sh from $BACKUP_DIR (or just delete it) 💛 ==="
