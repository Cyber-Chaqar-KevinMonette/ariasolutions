#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_response_depth.sh — teach Aria to match depth to question (v0.2.42.0)
#
#  Changes (surgical patch to interpreter.py — ~10 lines):
#    • The `response` field rule gains explicit depth guidance:
#        - casual chat → 1-2 sentences (existing default behavior preserved)
#        - factual questions → 2-4 sentences
#        - technical/architectural/analytical → thorough multi-paragraph
#      The CORE_VOICE kernel ("Brief, warm, technically rigorous") is NOT
#      touched. The interpreter routing gets smarter; the kernel stays.
#
#  Idempotent. Backs up interpreter.py before patching.
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

INTERP="$ROOT/src/sovereign_agent/interpreter.py"
ts(){ date +%Y%m%d%H%M%S; }
cp "$INTERP" "$INTERP.bak.$(ts)"

python3 - "$INTERP" <<'PYEOF'
import sys, pathlib

f = pathlib.Path(sys.argv[1])
src = f.read_text(encoding="utf-8")

MARKER = "Depth: match the depth"
if MARKER in src:
    print("  ↷ response-depth patch already applied — skipping")
    sys.exit(0)

OLD = (
    "  response         your voice. Lowercase, warm, conversational. Match \\\\\n"
    "                   Kevin's tone. Don't be sycophantic. Don't echo back \\\\\n"
    "                   the message; respond TO it. Brief is fine."
)
NEW = (
    "  response         your voice. Lowercase, warm, conversational. Match \\\\\n"
    "                   Kevin's tone. Don't be sycophantic. Don't echo back \\\\\n"
    "                   the message; respond TO it.\\\\\n"
    "\\\\\n"
    "                   Depth: match depth to the complexity of the question. \\\\\n"
    "                     • casual chat, check-in, acknowledgment → 1-2 sentences. \\\\\n"
    "                     • factual question, short status request → 2-4 sentences. \\\\\n"
    "                     • technical, architectural, analytical, design, \\\\\n"
    '                       "explain", "what\'s wrong", "help me understand", \\\\\n'
    "                       multi-part → thorough: full reasoning, concrete \\\\\n"
    "                       examples, multiple paragraphs. Never abbreviate when \\\\\n"
    "                       Kevin is asking you to think. Depth is kindness."
)

# Work with raw file content (backslashes are literal in the file)
raw = f.read_bytes().decode("utf-8")

# Match the exact raw bytes in the file
OLD_RAW = (
    "  response         your voice. Lowercase, warm, conversational. Match \\\n"
    "                   Kevin's tone. Don't be sycophantic. Don't echo back \\\n"
    "                   the message; respond TO it. Brief is fine."
)
NEW_RAW = (
    "  response         your voice. Lowercase, warm, conversational. Match \\\n"
    "                   Kevin's tone. Don't be sycophantic. Don't echo back \\\n"
    "                   the message; respond TO it.\\\n"
    "\\\n"
    "                   Depth: match depth to the complexity of the question. \\\n"
    "                     • casual chat, check-in, acknowledgment → 1-2 sentences. \\\n"
    "                     • factual question, short status request → 2-4 sentences. \\\n"
    "                     • technical, architectural, analytical, design, \\\n"
    "                       \"explain\", \"what's wrong\", \"help me understand\", \\\n"
    "                       multi-part → thorough: full reasoning, concrete \\\n"
    "                       examples, multiple paragraphs. Never abbreviate when \\\n"
    "                       Kevin is asking you to think. Depth is kindness."
)

if OLD_RAW not in raw:
    print("✗ expected anchor not found in interpreter.py — has the file changed?", file=sys.stderr)
    sys.exit(1)

raw = raw.replace(OLD_RAW, NEW_RAW, 1)
f.write_bytes(raw.encode("utf-8"))
print("  ✓ response depth guidance added to interpreter.py")
PYEOF

echo "→ compile check"
python3 -m py_compile "$INTERP"
echo "  ✓ compiles"

cp "$HERE/tests/test_response_depth.py" "$ROOT/tests/test_response_depth.py"
echo "  ✓ tests/test_response_depth.py installed"
python3 -m py_compile "$ROOT/tests/test_response_depth.py"
echo "  ✓ test file compiles"

echo
echo "✓ done. next:"
echo "    pytest tests/test_response_depth.py -v"
echo "    # then try: ask Aria 'explain how your router handles unknown commands'"
echo "    # expect a thorough multi-paragraph answer"
echo "    # try: 'how are you?' — expect 1-2 sentences"
