#!/usr/bin/env bash
# scripts/golden_reflex_smoke.sh — the REFLEX gate: an end-to-end turn that
# must actually CALL A TOOL. The golden-path gate (golden_path_smoke.sh)
# proves a plain conversational turn; this proves the deeper loop —
# authority gate → tool dispatch → tool result feeding back → a coherent
# final answer built on it. Asserted from events.jsonl, not from the
# model's prose:
#   1. process exits 0
#   2. a `tool-start-d` event was emitted during THIS run (real dispatch)
#   3. a matching `<tool>-d` result event followed (the result fed back)
#   4. final_message is non-empty
#
# Same discipline as the golden-path gate: a REAL Ollama call, deliberately
# NOT part of `pytest tests/` (see tests/test_golden_reflex_smoke.py for
# the structural checks that do run offline).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SOVEREIGN="$REPO_ROOT/.venv/bin/sovereign"
GOAL="${1:-Call the read_lessons tool now to read your recent lessons, then tell me one thing you learned.}"

echo "=== Golden Reflex smoke test (tool-calling gate) ==="

if ! curl -s -o /dev/null --max-time 3 "http://localhost:11434/api/tags" 2>/dev/null; then
  echo "✗ Ollama unreachable at localhost:11434 — cannot run a real end-to-end turn."
  echo "  (Honest FAILURE, not a skip: this gate requires a live model.)"
  exit 1
fi
echo "  ✓ Ollama reachable"

EVENTS_FILE="$("$VENV_PY" -c "from sovereign_agent.config import SETTINGS; print(SETTINGS.paths.events_jsonl)")"
LINES_BEFORE=0
[[ -f "$EVENTS_FILE" ]] && LINES_BEFORE=$(wc -l < "$EVENTS_FILE")

echo "→ Running: sov run \"$GOAL\""
set +e
OUTPUT="$("$SOVEREIGN" --json --quiet run "$GOAL" --max-iter 4 --max-wall 90 2>&1)"
EXIT_CODE=$?
set -e

if [[ $EXIT_CODE -ne 0 ]]; then
  echo "✗ agent_loop exited non-zero ($EXIT_CODE):"
  echo "$OUTPUT"
  exit 1
fi
echo "  ✓ agent_loop completed without raising"

# ── the reflex assertions: dispatch + result feedback, from the events ────
NEW_EVENTS="$(tail -n +"$((LINES_BEFORE + 1))" "$EVENTS_FILE" 2>/dev/null || true)"
REFLEX="$(printf '%s' "$NEW_EVENTS" | "$VENV_PY" -c "
import json, sys
dispatched = []
results = []
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        e = json.loads(line)
    except ValueError:
        continue
    flag = e.get('flag', '')
    if flag == 'tool-start-d':
        dispatched.append(e.get('payload', {}).get('tool', '?'))
    elif dispatched and flag in (f'{dispatched[-1]}-d', f'{dispatched[-1]}-x'):
        results.append(flag)
print(json.dumps({'dispatched': dispatched, 'results': results}))
")"
DISPATCHED_COUNT="$(echo "$REFLEX" | "$VENV_PY" -c "import json,sys; print(len(json.load(sys.stdin)['dispatched']))")"
RESULTS_COUNT="$(echo "$REFLEX" | "$VENV_PY" -c "import json,sys; print(len(json.load(sys.stdin)['results']))")"

if [[ "$DISPATCHED_COUNT" -lt 1 ]]; then
  echo "✗ no tool-start-d event in this run — the model never dispatched a tool."
  echo "  New events: $(printf '%s' "$NEW_EVENTS" | wc -l) lines; reflex: $REFLEX"
  exit 1
fi
echo "  ✓ tool dispatched ($REFLEX)"

if [[ "$RESULTS_COUNT" -lt 1 ]]; then
  echo "✗ no tool result event followed the dispatch — the result never fed back."
  exit 1
fi
echo "  ✓ tool result fed back into the loop"

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
  echo "✗ final_message is empty — the tool round-trip did not produce a coherent answer."
  exit 1
fi
echo "  ✓ coherent final response: ${FINAL_MESSAGE:0:100}"

echo
echo "=== Golden Reflex: PASS — authority gate → dispatch → feedback → answer, end to end. ==="
