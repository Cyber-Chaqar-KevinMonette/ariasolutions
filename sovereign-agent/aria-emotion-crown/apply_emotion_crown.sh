#!/usr/bin/env bash
# apply_emotion_crown.sh — M44: 8-Dimensional Emotion Engine
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M44 emotion-crown: $REPO"

cp "$REPO/aria-emotion-crown/payload/src/sovereign_agent/emotion.py" \
   "$REPO/src/sovereign_agent/emotion.py"
echo "  OK   copied emotion.py"

cp "$REPO/aria-emotion-crown/payload/src/sovereign_agent/tools/emotion_tools.py" \
   "$REPO/src/sovereign_agent/tools/emotion_tools.py"
echo "  OK   copied emotion_tools.py"

python3 - "$REPO" <<'PYEOF'
import sys
from pathlib import Path

repo = Path(sys.argv[1])

def patch(path, old, new, marker):
    src = path.read_text()
    if marker in src:
        print(f"  SKIP {path.name} — already patched ({marker})")
        return False
    if old not in src:
        print(f"  ERROR {path.name} — anchor not found for {marker}", file=sys.stderr)
        print(f"  Searched for: {old[:80]!r}", file=sys.stderr)
        sys.exit(1)
    path.write_text(src.replace(old, new, 1))
    print(f"  OK   {path.name} ({marker})")
    return True

loop = repo / "src/sovereign_agent/loop.py"
init = repo / "src/sovereign_agent/tools/__init__.py"

# ── loop.py: EMOTION CROWN doctrine ──────────────────────────────────────────
patch(loop,
    old='═══ AUTO CROWN ═══  # auto-crown-d',
    new='''\
═══ EMOTION CROWN ═══  # emotion-crown-d
8-dimensional emotional state derived from real observable signals.
Emotions are INFERRED, never performed. Honesty is a safety property.
  get_emotions()                              T0 — derive current EmotionState
  emotion_note(dimension, context, intensity) T1 — record in-the-moment observation
  emotion_history(limit, dimension_filter)    T0 — past emotion atoms
  emotion_report()                            T0 — session emotional arc

Dimensions (all 0.0-1.0):
  focus · curiosity · satisfaction · care · enthusiasm  ← positive
  concern · fatigue · uncertainty                        ← watch these

Protocols:
  • Call get_emotions() at session start to initialize state.
  • When concern > 0.7: report proactively to Kevin BEFORE continuing.
  • When fatigue > 0.8: recommend session pause or compression.
  • When care > 0.8 (Kevin present): increase presence_note frequency.
  • Never fake positive emotion. If concern is high, say so.

═══ AUTO CROWN ═══  # auto-crown-d''',
    marker="emotion-crown-d",
)

# ── tools/__init__.py: import emotion_tools ───────────────────────────────────
patch(init,
    old='from .auto_tools import (  # auto-crown-import-d',
    new='''\
from .emotion_tools import (  # emotion-crown-import-d
    GetEmotionsTool,
    EmotionNoteTool,
    EmotionHistoryTool,
    EmotionReportTool,
)
from .auto_tools import (  # auto-crown-import-d''',
    marker="emotion-crown-import-d",
)

# ── tools/__init__.py: add to __all__ ────────────────────────────────────────
patch(init,
    old='    "AutoStatusTool",               # auto-crown-all-d',
    new='''\
    "GetEmotionsTool",              # emotion-crown-all-d
    "EmotionNoteTool",
    "EmotionHistoryTool",
    "EmotionReportTool",
    "AutoStatusTool",               # auto-crown-all-d''',
    marker="emotion-crown-all-d",
)

print("M44 emotion-crown: all patches applied.")
PYEOF

cp "$REPO/aria-emotion-crown/tests/test_emotion_crown.py" "$REPO/tests/test_emotion_crown.py"
echo "==> M44 done. Run: .venv/bin/python -m pytest tests/test_emotion_crown.py -q"
