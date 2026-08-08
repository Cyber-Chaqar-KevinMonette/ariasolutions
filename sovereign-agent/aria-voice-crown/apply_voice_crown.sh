#!/usr/bin/env bash
# apply_voice_crown.sh — M47: Voice Crown (STT + TTS)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M47 voice-crown: $REPO"

# ── Copy payload files ────────────────────────────────────────────────────────
cp "$REPO/aria-voice-crown/payload/src/sovereign_agent/voice.py" \
   "$REPO/src/sovereign_agent/voice.py"
echo "  OK   copied voice.py"

cp "$REPO/aria-voice-crown/payload/src/sovereign_agent/tools/voice_tools.py" \
   "$REPO/src/sovereign_agent/tools/voice_tools.py"
echo "  OK   copied voice_tools.py"

# ── Patch loop.py and tools/__init__.py ──────────────────────────────────────
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

# ── 1. Doctrine section in loop.py (before VISION CROWN) ─────────────────────
patch(loop,
    old='═══ VISION CROWN ═══  # vision-crown-d',
    new='''\
═══ VOICE CROWN ═══  # voice-crown-d
Voice I/O — CPU-only, zero VRAM (faster-whisper CPU + piper-tts).
  voice_status()                               T0 — STT/TTS/arecord availability
  transcribe_audio(wav_path, model_size)       T1 — CPU Whisper transcription
  synthesize_speech(text, voice, play=False)   T1 — Piper TTS → WAV

Check voice_status() before attempting transcription or synthesis.
faster-whisper base.en model: ~150MB, excellent English, 2-3× real-time on CPU.
piper-tts voices: en_US-lessac-medium (natural) or en_US-ryan-high (expressive).
Both backends are CPU-only and can run alongside qwen3:8b without VRAM conflict.
If STT unavailable: fall back to text; never fail silently.

═══ VISION CROWN ═══  # vision-crown-d''',
    marker="voice-crown-d",
)

# ── 2. Import in tools/__init__.py (before vision-crown-import-d) ─────────────
patch(init,
    old='from .vision_tools import (  # vision-crown-import-d',
    new='''\
from .voice_tools import (  # voice-crown-import-d
    VoiceStatusTool,
    TranscribeAudioTool,
    SynthesizeSpeechTool,
)
from .vision_tools import (  # vision-crown-import-d''',
    marker="voice-crown-import-d",
)

# ── 3. __all__ in tools/__init__.py (before vision-crown-all-d) ───────────────
patch(init,
    old='    "VisionCaptureTool",            # vision-crown-all-d',
    new='''\
    "VoiceStatusTool",               # voice-crown-all-d
    "TranscribeAudioTool",
    "SynthesizeSpeechTool",
    "VisionCaptureTool",            # vision-crown-all-d''',
    marker="voice-crown-all-d",
)

print("M47 voice-crown: all patches applied.")
PYEOF

# ── Copy tests ────────────────────────────────────────────────────────────────
cp "$REPO/aria-voice-crown/tests/test_voice_crown.py" \
   "$REPO/tests/test_voice_crown.py"
echo "  OK   copied test_voice_crown.py"

echo "==> M47 done. Run: .venv/bin/python -m pytest tests/test_voice_crown.py -q"
