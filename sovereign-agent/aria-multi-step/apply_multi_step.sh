#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_multi_step.sh — teach Aria to plan before acting (v0.2.42.0)
#
#  Changes (surgical patches):
#
#    loop.py — adds ═══ PLANNING ═══ section to the agent loop system prompt:
#      • Before first tool call, state the plan (tool sequence + why)
#      • When tools are independent, issue multiple tool_calls in one response
#      • Act without permission for Tier 0/1; don't ask, just do
#
#    agent_session.py — increases per-subtask iteration cap from 15 → 25:
#      • A 15-iteration cap on a 8-tool task leaves only 7 reasoning steps
#      • 25 gives Aria room for both planning and multi-tool-per-turn execution
#
#  Idempotent. Backs up both files before patching.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$PWD}"

if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }
    d="$(dirname "$d")"
  done
fi
[[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || { echo "✗ run from repo root"; exit 1; }
echo "◊ repo root: $ROOT"

PKG="$ROOT/src/sovereign_agent"
LOOP="$PKG/loop.py"
SESSION="$PKG/agent_session.py"
ts(){ date +%Y%m%d%H%M%S; }
cp "$LOOP" "$LOOP.bak.$(ts)"
cp "$SESSION" "$SESSION.bak.$(ts)"

echo "→ patching loop.py (PLANNING section)"
python3 - "$LOOP" <<'PYEOF'
import sys, pathlib

f = pathlib.Path(sys.argv[1])
src = f.read_text(encoding="utf-8")

MARKER = "═══ PLANNING ═══"
if MARKER in src:
    print("  ↷ PLANNING section already present — skipping")
else:
    OLD = "═══ UNTRUSTED INPUT DOCTRINE ═══"
    NEW = """\
═══ PLANNING ═══
Before your first tool call on any non-trivial task, state your plan in
one short message: list the tools you will call (in order) and why. One
line per step is enough. Do this in your response content, not a tool call.

When tools are INDEPENDENT of each other — reading different files,
searching different sources, checking different things simultaneously —
issue ALL of them in a single response as multiple tool_calls. The loop
processes the full array before the next LLM turn. Use this aggressively:
parallel reads cut iteration cost in half.

For Tier 0 and Tier 1 actions: DO NOT ASK PERMISSION. Act, observe,
report. Silence and forward motion are the goal. If you made a mistake, fix
it on the next turn. The operator trusts you to work, not to narrate.

═══ UNTRUSTED INPUT DOCTRINE ═══"""
    if OLD not in src:
        print("✗ UNTRUSTED INPUT DOCTRINE anchor not found in loop.py", file=sys.stderr)
        sys.exit(1)
    src = src.replace(OLD, NEW, 1)
    f.write_text(src, encoding="utf-8")
    print("  ✓ PLANNING section added to loop.py system prompt")
PYEOF

echo "→ patching agent_session.py (iteration cap 15→25)"
python3 - "$SESSION" <<'PYEOF'
import sys, pathlib

f = pathlib.Path(sys.argv[1])
src = f.read_text(encoding="utf-8")

MARKER_NEW = "max_iterations=25, max_wall_seconds=600, max_tokens=100_000"
if MARKER_NEW in src:
    print("  ↷ iteration cap already at 25 — skipping")
else:
    OLD = "max_iterations=15, max_wall_seconds=600, max_tokens=100_000"
    if OLD not in src:
        print("✗ per-subtask budget anchor not found in agent_session.py", file=sys.stderr)
        sys.exit(1)
    src = src.replace(OLD, MARKER_NEW, 1)
    f.write_text(src, encoding="utf-8")
    print("  ✓ per-subtask iteration cap raised 15→25")
PYEOF

echo "→ compile check"
python3 -m py_compile "$LOOP" "$SESSION"
echo "  ✓ compiles"

cp "$HERE/tests/test_multi_step.py" "$ROOT/tests/test_multi_step.py"
echo "  ✓ tests/test_multi_step.py installed"
python3 -m py_compile "$ROOT/tests/test_multi_step.py"
echo "  ✓ test file compiles"

echo
echo "✓ done. next:"
echo "    pytest tests/test_multi_step.py -v"
echo "    # then give Aria a multi-file task and watch her plan + parallel-call"
