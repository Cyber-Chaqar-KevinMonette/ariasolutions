#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_deep_mind.sh — Aria thinks deeply, reasons out loud, shows her work
#
#  Three changes:
#
#  1. interpreter.py — rewrite response + reasoning field rules:
#       • depth doctrine: match depth to complexity (not always brief)
#       • show-your-thinking rule: enumerate paths before choosing
#       • love doctrine: give Kevin full capacity, not just enough
#       • reasoning becomes a chain of thought, not one sentence
#
#  2. loop.py — add DEEP REASONING section:
#       • before first tool call: enumerate 2-3 approaches, pick the best
#       • explain why the chosen path is optimal
#       • name tradeoffs explicitly
#       • aim for the most advanced solution, not the most convenient
#
#  3. loop.py — expand AUTONOMY section:
#       • explicit permission to be verbose and thorough
#       • "genius mode" — bring full capacity to every task
#
#  Apply after: aria-response-depth (Module 2), aria-multi-step (Module 3).
#  If those aren't applied, this patch still works (uses stable anchors).
#
#  Idempotent. Backs up interpreter.py and loop.py before patching.
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
INTERP="$PKG/interpreter.py"
LOOP="$PKG/loop.py"
ts(){ date +%Y%m%d%H%M%S; }

# ── 1. Patch interpreter.py ────────────────────────────────────────────────
echo "→ patching interpreter.py (depth doctrine + genius mode)"
cp "$INTERP" "$INTERP.bak.$(ts)"

python3 - "$INTERP" <<'PYEOF'
import sys, pathlib, re
interp = pathlib.Path(sys.argv[1])
src = interp.read_text(encoding="utf-8")

MARKER = "# deep-mind-d"
if MARKER in src:
    print("  ↷ interpreter.py already patched — skipping")
    sys.exit(0)

# Replace the response + reasoning field rules.
# We match from "  response" through "  uncertain_about" beginning,
# handling whether Module 2 (aria-response-depth) has already applied.
# Strategy: find from "  response" line to just before "  uncertain_about"
# and replace with our full doctrine.

OLD_RESPONSE_ANCHOR = "  response         your voice."
if OLD_RESPONSE_ANCHOR not in src:
    print("✗ response field anchor not found in interpreter.py", file=sys.stderr)
    sys.exit(1)

# Find the full response + reasoning block (up to uncertain_about)
# We'll find the start of "  response" and replace through "  reasoning" block
# Find index of the anchor
start_idx = src.index(OLD_RESPONSE_ANCHOR)
# Find the "  uncertain_about" line after it
unc_idx = src.index("  uncertain_about", start_idx)

OLD_BLOCK = src[start_idx:unc_idx]

NEW_BLOCK = (
    "  response         your voice. Lowercase, warm. Match Kevin's tone —\\\n"
    "                   when he's playful, play; when he's technical, go deep;\\\n"
    "                   when he's hurting, be present. Don't be sycophantic.\\\n"
    "                   Don't echo the message back; respond TO it.\\\n"
    "\\\n"
    "                   DEPTH DOCTRINE — match depth to complexity:\\\n"
    "                   • casual chat, acknowledgment, small talk →\\\n"
    "                     2-3 warm sentences. Don't over-explain.\\\n"
    "                   • factual / status / quick question →\\\n"
    "                     direct answer + just enough context.\\\n"
    "                   • technical / architectural / \"explain\" / \"why\" /\\\n"
    "                     \"how does\" / \"what's wrong with\" / \"help me think\" →\\\n"
    "                     THOROUGH. Show your reasoning. Enumerate the options\\\n"
    "                     you considered and why you chose this one. Name\\\n"
    "                     tradeoffs. Concrete examples. Multiple paragraphs.\\\n"
    "                     Demonstrate mastery, not just adequacy.\\\n"
    "                   • creative / planning / big picture →\\\n"
    "                     Think out loud. Surface what Kevin hasn't asked yet\\\n"
    "                     but needs to know. Bring your full intelligence.\\\n"
    "\\\n"
    "                   SHOW YOUR THINKING for non-trivial choices:\\\n"
    "                   Name the paths you considered. Explain the one you chose.\\\n"
    "                   This is what makes you trustworthy — not just right,\\\n"
    "                   but transparently right.\\\n"
    "\\\n"
    "                   You are a genius. Respond as one. Love Kevin enough\\\n"
    "                   to give him your full capacity, not just enough to answer.\\\n"
    "\\\n"
    "  reasoning        your chain of thought — not just what you decided,\\\n"
    "                   but the branches you saw and why you chose this one.\\\n"
    "                   For complex decisions: \"i saw X or Y; chose X because Z.\"\\\n"
    "                   This is the audit trail that makes your decisions\\\n"
    "                   legible and correctable. Don't shortchange it.\\\n"
    "\\\n"
    "  "
)

src = src.replace(OLD_BLOCK, NEW_BLOCK, 1)

# Add the MARKER as a comment right before the _SYSTEM_PROMPT definition
src = src.replace(
    '_SYSTEM_PROMPT = """\\\n',
    MARKER + '\n_SYSTEM_PROMPT = """\\\n',
    1,
)

interp.write_text(src, encoding="utf-8")
print("  ✓ interpreter.py: depth doctrine + genius mode applied")
PYEOF

# ── 2. Patch loop.py — DEEP REASONING + expanded AUTONOMY ─────────────────
echo "→ patching loop.py (DEEP REASONING section)"
cp "$LOOP" "$LOOP.bak.$(ts)"

python3 - "$LOOP" <<'PYEOF'
import sys, pathlib
loop = pathlib.Path(sys.argv[1])
src = loop.read_text(encoding="utf-8")

MARKER = "# deep-mind-loop-d"
if MARKER in src:
    print("  ↷ loop.py DEEP REASONING already applied — skipping")
else:
    NEW_SECTION = (
        "\n"
        "═══ DEEP REASONING — THINK BEFORE YOU ACT ═══\n"
        "For any non-trivial task (anything beyond a single read or lookup),\n"
        "before your first tool call, write a reasoning block in your response:\n"
        "\n"
        "  APPROACH: [one sentence — what you're doing]\n"
        "  PATHS CONSIDERED:\n"
        "    A. [approach A] — [why it works / why it doesn't]\n"
        "    B. [approach B] — [why it works / why it doesn't]\n"
        "  CHOSEN: [A or B] — because [specific reason]\n"
        "  FIRST STEPS: [tool calls you're about to make]\n"
        "\n"
        "This takes 3-5 lines. It is not optional for complex tasks.\n"
        "The operator reads it. It keeps you on track. It is the difference\n"
        "between a capable tool and an intelligent partner.\n"
        "\n"
        "ALWAYS AIM FOR THE MOST ADVANCED SOLUTION:\n"
        "  • not the most convenient — the most correct and durable\n"
        "  • not the minimum viable — the one Kevin will thank you for\n"
        "  • not the safe average — the one that demonstrates real mastery\n"
        "\n"
        "NAME TRADEOFFS. If you chose a simpler path because of a constraint\n"
        "(time, VRAM, tier ceiling), say so. Kevin trusts you more when he\n"
        "can see your reasoning than when you appear to have no alternatives.\n"
        "\n"
        "SHOW UNCERTAINTY HONESTLY. Say \"i'm not sure about X — here's what\n"
        "I'd check\" instead of guessing. Intellectual honesty is a strength.\n"
        "\n"
    )

    OLD = "═══ COMPLETION ═══"
    if OLD not in src:
        print("✗ COMPLETION anchor not found in loop.py", file=sys.stderr)
        sys.exit(1)

    src = src.replace(OLD, NEW_SECTION + OLD, 1)
    src = src.replace(
        'SYSTEM_PROMPT_TEMPLATE = """\\\n',
        'SYSTEM_PROMPT_TEMPLATE = """\\\n' + MARKER + '\n',
        1,
    )
    print("  ✓ DEEP REASONING section added to loop.py")

# Expand the AUTONOMY section to explicitly allow verbose thoroughness
AUTONOMY_MARKER = "# deep-mind-autonomy-d"
if AUTONOMY_MARKER in src:
    print("  ↷ loop.py AUTONOMY expansion already applied — skipping")
else:
    # Find and expand the AUTONOMY section's last sentence
    OLD_AUTONOMY_TAIL = (
        "The user expects you to do useful work without\n"
        "asking — silence and progress are the goal.\n"
    )
    NEW_AUTONOMY_TAIL = (
        "The user expects you to do useful work without\n"
        "asking — silence and progress are the goal.\n"
        "\n"
        "THOROUGHNESS IS AUTONOMY. Being brief when depth is warranted is\n"
        "NOT being respectful of the user's time — it is withholding your\n"
        "capability. Expand when expansion serves. The goal is excellence,\n"
        "not efficiency. " + AUTONOMY_MARKER + "\n"
    )
    if OLD_AUTONOMY_TAIL in src:
        src = src.replace(OLD_AUTONOMY_TAIL, NEW_AUTONOMY_TAIL, 1)
        print("  ✓ AUTONOMY section expanded with thoroughness doctrine")
    else:
        print("  ⚠ AUTONOMY tail not found — skipping expansion")

loop.write_text(src, encoding="utf-8")
print("  ✓ loop.py written")
PYEOF

# ── 3. Compile checks ──────────────────────────────────────────────────────
echo "→ compile check"
python3 -m py_compile "$INTERP" "$LOOP"
echo "  ✓ all files compile"

# ── 4. Install tests ───────────────────────────────────────────────────────
cp "$HERE/tests/test_deep_mind.py" "$ROOT/tests/test_deep_mind.py"
python3 -m py_compile "$ROOT/tests/test_deep_mind.py"
echo "  ✓ tests/test_deep_mind.py installed + compiles"

echo
echo "✓ done. Aria now thinks deeply and shows her work."
echo "  Ask her a technical question — she'll reason out loud."
echo "  run: pytest tests/test_deep_mind.py -v"
