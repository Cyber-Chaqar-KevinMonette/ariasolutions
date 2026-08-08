#!/usr/bin/env bash
# apply_golden_reflex.sh — install Gym #8: the tool-calling end-to-end gate.
#
# Ships scripts/golden_reflex_smoke.sh (a sibling of golden_path_smoke.sh):
# a `sov run` turn whose goal forces a tool call, asserted from
# events.jsonl (tool-start-d dispatch + <tool>-d result feedback) plus a
# non-empty final_message. Built BEFORE the prompt diet so the diet has a
# reflex gate to pass. The apply ends by running the real gate once.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-golden-reflex"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SCRIPT="$REPO_ROOT/scripts/golden_reflex_smoke.sh"

echo "=== aria-golden-reflex apply ==="
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }

echo "→ Copying scripts/golden_reflex_smoke.sh (new file)..."
cp "$STAGING/payload/scripts/golden_reflex_smoke.sh" "$SCRIPT"
chmod +x "$SCRIPT"

cp "$STAGING/tests/test_golden_reflex_smoke.py" "$REPO_ROOT/tests/"
echo "Running structural tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_golden_reflex_smoke.py" -q

echo "→ Running the REAL reflex gate once (live Ollama call, ~60s)..."
bash "$SCRIPT"

echo "=== aria-golden-reflex applied. Reversible: rm scripts/golden_reflex_smoke.sh 💛 ==="
