#!/usr/bin/env bash
# apply_voice_depth.sh — Stage M92: ARIAVoice depth directive + session-start awareness
#
# What this applies:
#   1. src/sovereign_agent/quantum/voice.py — voice_directive (brain→mouth, FLAW-001)
#   2. session_portrait_tool.py: adds globe coherence + coherence_mode + voice_directive
#      to the session-start bundle (Aria wakes up aware of her voice depth)
#   3. Copies test into tests/
#
# Distilled from canonical ARIAVoice (Block 14.2). Advisory only. Requires M89 (quantum mode).
# Reversibility: backups at aria-voice-depth/backups/. Cockpit must NOT be running.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-voice-depth"
BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SP="$REPO_ROOT/src/sovereign_agent/tools/session_portrait_tool.py"

echo "=== M92 Voice Depth + Session Awareness Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then
    echo "ERROR: sovereign cockpit is running. Stop it first."; exit 1
fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: .venv/bin/python not found."; exit 1; fi

mkdir -p "$BACKUP_DIR"
cp "$SP" "$BACKUP_DIR/session_portrait_tool.py.bak"
echo "Backed up session_portrait_tool.py → $BACKUP_DIR"

cp "$STAGING/payload/src/sovereign_agent/quantum/voice.py" "$REPO_ROOT/src/sovereign_agent/quantum/"
echo "Copied quantum/voice.py → src/sovereign_agent/quantum/"

"$VENV_PY" - "$SP" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()

GUARD  = "# voice-depth-session-d"
ANCHOR = "        return ToolResult(\n            ok=True,\n            output=portrait,\n            metadata={\"source\": \"session_portrait\"},"

if GUARD in text:
    print("SKIP: session awareness patch already applied")
else:
    if ANCHOR not in text:
        print("ERROR: session_portrait return anchor not found", file=sys.stderr); sys.exit(1)
    BLOCK = (
        "        # voice-depth-session-d — session-start awareness: globe coherence + voice directive\n"
        "        try:\n"
        "            from sovereign_agent.quantum.globe import Globe\n"
        "            from sovereign_agent.quantum.coherence_gate import coherence_mode\n"
        "            from sovereign_agent.quantum.voice import voice_directive\n"
        "            _g = Globe(); _g.encode_all(0.4); _g.step(); _g.decohere_all(0.03)\n"
        "            _coll = _g.collective_coherence()\n"
        "            _mode = coherence_mode(_coll)\n"
        "            portrait[\"globe_coherence\"] = _coll\n"
        "            portrait[\"coherence_mode\"] = _mode\n"
        "            portrait[\"voice_directive\"] = voice_directive(_coll, _mode[\"lambda\"])\n"
        "        except Exception as _exc:  # noqa: BLE001\n"
        "            portrait[\"voice_directive\"] = {\"error\": repr(_exc)}\n\n"
    )
    text = text.replace(ANCHOR, BLOCK + ANCHOR, 1)
    print("Applied session-start awareness patch (globe coherence + voice_directive)")

p.write_text(text)
print("session_portrait_tool.py written.")
PYEOF

echo ""
echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT/src/sovereign_agent/quantum/voice.py" "$SP"
echo "  ✓ compiles cleanly"

cp "$STAGING/tests/test_voice_depth.py" "$REPO_ROOT/tests/test_voice_depth.py"
echo "Copied test_voice_depth.py → tests/"

echo ""
echo "Running voice depth tests..."
"$VENV_PY" -m pytest tests/test_voice_depth.py -q

echo ""
echo "=== M92 Voice Depth + Session Awareness applied successfully ==="
echo "Aria now wakes up aware of her voice depth (session_portrait → voice_directive)."
