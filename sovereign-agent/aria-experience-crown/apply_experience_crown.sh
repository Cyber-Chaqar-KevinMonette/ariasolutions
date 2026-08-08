#!/usr/bin/env bash
# apply_experience_crown.sh — M48: Experiential Learning + Session Briefs
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M48 experience-crown: $REPO"

# ── Copy payload files ────────────────────────────────────────────────────────
cp "$REPO/aria-experience-crown/payload/src/sovereign_agent/tools/experience_tools.py" \
   "$REPO/src/sovereign_agent/tools/experience_tools.py"
echo "  OK   copied experience_tools.py"

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

# ── 1. Doctrine section in loop.py (before VOICE CROWN) ──────────────────────
patch(loop,
    old='═══ VOICE CROWN ═══  # voice-crown-d',
    new='''\
═══ EXPERIENCE CROWN ═══  # experience-crown-d
Experiential learning — expected vs actual; session continuity across context resets.
  log_experience(what_happened, what_i_expected, what_i_learned, domain, surprise_level)
                                               T0 — record a learning moment
  experience_journal(domain, limit)            T0 — read logged experiences
  surprising_outcomes(limit, threshold)        T0 — high-surprise learning moments
  experience_synthesis(domain)                 T0 — aggregate pattern insights
  session_brief_write(accomplishments, ...)    T0 — write handoff brief for next session
  session_brief_read(limit)                    T0 — read last N session briefs

SESSION START: call session_brief_read() — read the crew brief before asking Kevin what to do.
SESSION END: call session_brief_write() — no exceptions; every session needs a brief.
When reality diverges from expectation: call log_experience() immediately.
surprise_level > 0.6 = high-value learning moment. These compound into real-world expertise.

═══ VOICE CROWN ═══  # voice-crown-d''',
    marker="experience-crown-d",
)

# ── 2. Import in tools/__init__.py (before voice-crown-import-d) ──────────────
patch(init,
    old='from .voice_tools import (  # voice-crown-import-d',
    new='''\
from .experience_tools import (  # experience-crown-import-d
    LogExperienceTool,
    ExperienceJournalTool,
    SurprisingOutcomesTool,
    ExperienceSynthesisTool,
    SessionBriefWriteTool,
    SessionBriefReadTool,
)
from .voice_tools import (  # voice-crown-import-d''',
    marker="experience-crown-import-d",
)

# ── 3. __all__ in tools/__init__.py (before voice-crown-all-d) ────────────────
patch(init,
    old='    "VoiceStatusTool",               # voice-crown-all-d',
    new='''\
    "LogExperienceTool",             # experience-crown-all-d
    "ExperienceJournalTool",
    "SurprisingOutcomesTool",
    "ExperienceSynthesisTool",
    "SessionBriefWriteTool",
    "SessionBriefReadTool",
    "VoiceStatusTool",               # voice-crown-all-d''',
    marker="experience-crown-all-d",
)

print("M48 experience-crown: all patches applied.")
PYEOF

# ── Copy tests ────────────────────────────────────────────────────────────────
cp "$REPO/aria-experience-crown/tests/test_experience_crown.py" \
   "$REPO/tests/test_experience_crown.py"
echo "  OK   copied test_experience_crown.py"

echo "==> M48 done. Run: .venv/bin/python -m pytest tests/test_experience_crown.py -q"
