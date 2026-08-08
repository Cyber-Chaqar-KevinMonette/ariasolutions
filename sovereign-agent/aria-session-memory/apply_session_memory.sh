#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_session_memory.sh — improve Aria's cross-subtask memory (v0.2.42.0)
#
#  Changes:
#
#    agent_session.py — increase cross-subtask summary budget 2000→4000 chars.
#      The 2000-char bridge was the primary cause of "persistence flakiness":
#      Aria forgot how she solved prior subtasks and had to rediscover.
#
#    loop.py — add read_session guidance to the MEMORY section:
#      "At the start of a resumed session, call read_session to review prior
#       work before beginning."
#
#    tools/session_review.py (new) — Tier 0 ReadSessionTool:
#      Aria can call read_session() mid-execution to inspect her own session:
#      goal, subtask list, result summaries, progress, errors.
#
#    tools/__init__.py — import ReadSessionTool (auto-registers)
#
#  Idempotent. Backs up modified files before patching.
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
SESSION="$PKG/agent_session.py"
LOOP="$PKG/loop.py"
INIT="$PKG/tools/__init__.py"
TOOLS="$PKG/tools"
ts(){ date +%Y%m%d%H%M%S; }

# ── 1. Copy new tool file ────────────────────────────────────────────────────
echo "→ installing tools/session_review.py"
cp "$HERE/payload/src/sovereign_agent/tools/session_review.py" "$TOOLS/session_review.py"
echo "  ✓ tools/session_review.py"

# ── 2. Patch tools/__init__.py ───────────────────────────────────────────────
echo "→ patching tools/__init__.py"
python3 - "$INIT" <<'PYEOF'
import sys, pathlib

init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

if "from .session_review import" in src:
    print("  ↷ session_review import already present — skipping")
else:
    OLD = "from .write_file import WriteFileTool"
    NEW = "from .session_review import ReadSessionTool\nfrom .write_file import WriteFileTool"
    if OLD not in src:
        print("✗ write_file import anchor not found in __init__.py", file=sys.stderr)
        sys.exit(1)
    src = src.replace(OLD, NEW, 1)
    print("  ✓ ReadSessionTool import added")

if '"ReadSessionTool"' in src:
    print("  ↷ __all__ entry already present — skipping")
else:
    OLD_ALL = '    "WriteFileTool",'
    NEW_ALL = '    "ReadSessionTool",\n    "WriteFileTool",'
    src = src.replace(OLD_ALL, NEW_ALL, 1)
    print("  ✓ ReadSessionTool added to __all__")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 3. Patch agent_session.py (summary budget 2000→4000) ─────────────────────
echo "→ patching agent_session.py (summary budget 2000→4000)"
cp "$SESSION" "$SESSION.bak.$(ts)"
python3 - "$SESSION" <<'PYEOF'
import sys, pathlib

f = pathlib.Path(sys.argv[1])
src = f.read_text(encoding="utf-8")

MARKER = "max_chars: int = 4000"
if MARKER in src:
    print("  ↷ summary budget already at 4000 — skipping")
else:
    OLD = "max_chars: int = 2000"
    if OLD not in src:
        print("✗ max_chars=2000 not found in completed_summary_for_prompt", file=sys.stderr)
        sys.exit(1)
    src = src.replace(OLD, "max_chars: int = 4000", 1)
    f.write_text(src, encoding="utf-8")
    print("  ✓ cross-subtask summary budget raised 2000→4000 chars")
PYEOF

# ── 4. Patch loop.py (add read_session guidance to MEMORY section) ────────────
echo "→ patching loop.py (MEMORY section + read_session hint)"
cp "$LOOP" "$LOOP.bak.$(ts)"
python3 - "$LOOP" <<'PYEOF'
import sys, pathlib

f = pathlib.Path(sys.argv[1])
src = f.read_text(encoding="utf-8")

MARKER = "read_session"
if MARKER in src:
    print("  ↷ read_session guidance already in loop.py — skipping")
else:
    OLD = (
        "FTS) lookup, ``memory_write`` to persist atoms. BEFORE making a meaningful\n"
        "decision, search memory for prior runs. AFTER discovering something\n"
        "durable, write an atom — confidence honest, parents = the event ULIDs that\n"
        "produced the finding."
    )
    NEW = (
        "FTS) lookup, ``memory_write`` to persist atoms. BEFORE making a meaningful\n"
        "decision, search memory for prior runs. AFTER discovering something\n"
        "durable, write an atom — confidence honest, parents = the event ULIDs that\n"
        "produced the finding.\n\n"
        "When resuming or continuing a session, call ``read_session`` first to review\n"
        "what subtasks are complete, what's pending, and what was already learned.\n"
        "Don't redo work that's already done."
    )
    if OLD not in src:
        print("✗ MEMORY section anchor not found in loop.py", file=sys.stderr)
        sys.exit(1)
    src = src.replace(OLD, NEW, 1)
    f.write_text(src, encoding="utf-8")
    print("  ✓ read_session guidance added to MEMORY section in loop.py")
PYEOF

# ── 5. Compile check ─────────────────────────────────────────────────────────
echo "→ compile check"
python3 -m py_compile "$TOOLS/session_review.py" "$INIT" "$SESSION" "$LOOP"
echo "  ✓ all compile"

cp "$HERE/tests/test_session_memory.py" "$ROOT/tests/test_session_memory.py"
echo "  ✓ tests/test_session_memory.py installed"
python3 -m py_compile "$ROOT/tests/test_session_memory.py"
echo "  ✓ test file compiles"

echo
echo "✓ done. next:"
echo "    pytest tests/test_session_memory.py -v"
echo "    # Aria can now call read_session() to review her own progress"
