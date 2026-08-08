#!/usr/bin/env bash
# apply_vision_crown.sh — M45: Screen Perception Stack
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M45 vision-crown: $REPO"

cp "$REPO/aria-vision-crown/payload/src/sovereign_agent/vision.py" \
   "$REPO/src/sovereign_agent/vision.py"
echo "  OK   copied vision.py"

cp "$REPO/aria-vision-crown/payload/src/sovereign_agent/tools/vision_tools.py" \
   "$REPO/src/sovereign_agent/tools/vision_tools.py"
echo "  OK   copied vision_tools.py"

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

# ── loop.py: VISION CROWN doctrine ───────────────────────────────────────────
patch(loop,
    old='═══ EMOTION CROWN ═══  # emotion-crown-d',
    new='''\
═══ VISION CROWN ═══  # vision-crown-d
Screen perception — CPU-first, zero VRAM for routine capture.
  vision_capture()                            T1 — screenshot + CPU OCR (~200ms-2s)
  vision_scene()                              T0 — latest cached scene (instant)
  vision_diff()                               T0 — what changed since last capture
  vision_memory(limit=5)                      T0 — last N visual scenes
  vision_deep(question=None)                  T1 — heavy VLM (vram_lock, expensive)
  vision_watch(interval_seconds, duration_seconds)  T2 — periodic watch

Use vision_capture() + vision_scene() for screen awareness.
Use vision_diff() to detect when Kevin switches context.
vision_deep() uses llava:7b via vram_lock — use sparingly, CPU OCR is preferred.
When you notice something relevant: proactively say so.
"I can see you're working on test failures — should I investigate?"

═══ EMOTION CROWN ═══  # emotion-crown-d''',
    marker="vision-crown-d",
)

# ── tools/__init__.py: import vision_tools ────────────────────────────────────
patch(init,
    old='from .emotion_tools import (  # emotion-crown-import-d',
    new='''\
from .vision_tools import (  # vision-crown-import-d
    VisionCaptureTool,
    VisionSceneTool,
    VisionDiffTool,
    VisionMemoryTool,
    VisionDeepTool,
    VisionWatchTool,
)
from .emotion_tools import (  # emotion-crown-import-d''',
    marker="vision-crown-import-d",
)

# ── tools/__init__.py: add to __all__ ────────────────────────────────────────
patch(init,
    old='    "GetEmotionsTool",              # emotion-crown-all-d',
    new='''\
    "VisionCaptureTool",            # vision-crown-all-d
    "VisionSceneTool",
    "VisionDiffTool",
    "VisionMemoryTool",
    "VisionDeepTool",
    "VisionWatchTool",
    "GetEmotionsTool",              # emotion-crown-all-d''',
    marker="vision-crown-all-d",
)

print("M45 vision-crown: all patches applied.")
PYEOF

cp "$REPO/aria-vision-crown/tests/test_vision_crown.py" "$REPO/tests/test_vision_crown.py"
echo "==> M45 done. Run: .venv/bin/python -m pytest tests/test_vision_crown.py -q"
