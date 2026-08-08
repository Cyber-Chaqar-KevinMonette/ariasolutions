#!/usr/bin/env bash
# scripts/golden_path_smoke.sh — the "finished, complete, whole" end-to-end
# gate. Boots the agent loop headless (no TUI), sends one representative
# operator turn all the way through `sov run`, and asserts:
#   1. the process exits 0 — no unhandled exception
#   2. the final response is non-empty — a coherent reply, not silence
#   3. events.jsonl grew with fresh trace/settle events — the event
#      stream is alive, not stalled
#
# Run this once after every workstream lands, and once more at the very
# end as the standing proof. Deliberately NOT part of `pytest tests/` —
# it makes a REAL Ollama call (network + LLM dependency, ~30-40s), which
# would make the otherwise-deterministic, offline, fast test suite
# flaky/slow. This is a separate, deliberate, manual gate — see
# tests/test_golden_path_smoke.py for the lightweight structural checks
# that DO run in the normal suite (script exists, is executable, valid
# bash syntax) plus an honestly-skipped-if-unreachable real invocation.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SOVEREIGN="$REPO_ROOT/.venv/bin/sovereign"
GOAL="${1:-Say hello and confirm you are working.}"

echo "=== Golden Path smoke test ==="

# ── preflight: Ollama must be reachable, or this gate is meaningless ──────
if ! curl -s -o /dev/null --max-time 3 "http://localhost:11434/api/tags" 2>/dev/null; then
  echo "✗ Ollama unreachable at localhost:11434 — cannot run a real end-to-end turn."
  echo "  (This is an honest FAILURE, not a skip: the Golden Path gate requires a live model.)"
  exit 1
fi
echo "  ✓ Ollama reachable"

# ── snapshot events.jsonl's current line count (today's rotated file) ─────
EVENTS_FILE="$("$VENV_PY" -c "from sovereign_agent.config import SETTINGS; print(SETTINGS.paths.events_jsonl)")"
LINES_BEFORE=0
[[ -f "$EVENTS_FILE" ]] && LINES_BEFORE=$(wc -l < "$EVENTS_FILE")

# ── the actual end-to-end turn ─────────────────────────────────────────────
echo "→ Running: sov run \"$GOAL\""
set +e
OUTPUT="$("$SOVEREIGN" --json --quiet run "$GOAL" --max-iter 3 --max-wall 60 2>&1)"
EXIT_CODE=$?
set -e

if [[ $EXIT_CODE -ne 0 ]]; then
  echo "✗ agent_loop exited non-zero ($EXIT_CODE) — unhandled exception:"
  echo "$OUTPUT"
  exit 1
fi
echo "  ✓ agent_loop completed without raising"

# ── assert a coherent response (non-empty final_message) ──────────────────
JSON_LINE="$(echo "$OUTPUT" | grep '^{' | tail -1)"
FINAL_MESSAGE="$(echo "$JSON_LINE" | "$VENV_PY" -c "
import json, sys
try:
    d = json.loads(sys.stdin.read())
    print(d.get('final_message', ''))
except Exception:
    print('')
")"
if [[ -z "$FINAL_MESSAGE" ]]; then
  echo "✗ final_message is empty — not a coherent response."
  echo "  Full output: $OUTPUT"
  exit 1
fi
echo "  ✓ coherent final response: ${FINAL_MESSAGE:0:100}"

# ── assert events.jsonl grew (the event stream is alive) ──────────────────
LINES_AFTER=0
[[ -f "$EVENTS_FILE" ]] && LINES_AFTER=$(wc -l < "$EVENTS_FILE")
if [[ "$LINES_AFTER" -le "$LINES_BEFORE" ]]; then
  echo "✗ events.jsonl did not grow ($LINES_BEFORE -> $LINES_AFTER lines) — event stream may be stalled."
  exit 1
fi
echo "  ✓ events.jsonl grew ($LINES_BEFORE -> $LINES_AFTER lines)"

echo
echo "=== Golden Path: PASS — the agent loop is finished, complete, whole. ==="
