#!/usr/bin/env bash
# apply_compression.sh — M36: high-leverage context compression
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M36 compression: $REPO"

cp "$REPO/aria-compression/payload/src/sovereign_agent/compression.py" \
   "$REPO/src/sovereign_agent/compression.py"
echo "  OK   copied compression.py"

cp "$REPO/aria-compression/payload/src/sovereign_agent/tools/compression_tools.py" \
   "$REPO/src/sovereign_agent/tools/compression_tools.py"
echo "  OK   copied compression_tools.py"

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

# ── loop.py: COMPRESSION ORACLE doctrine ─────────────────────────────────────
patch(loop,
    old='═══ MODE AWARENESS ═══  # mode-awareness-d',
    new='''\
═══ COMPRESSION ORACLE ═══  # compression-oracle-d
When a session grows long (>50 events or budget < 30%), check first:
  context_stats()         → event count, opportunity score, tokens estimate (T0)
If compression_opportunity > 0.6: call compress_context(). It preserves
all decisions, commits, and lessons while compressing noise. The summary
is written as an atom and surfaces on the next read_session() call.
  read_compressed_context() → retrieve latest summary (T0)
Compression is love: it keeps what matters and makes room for more work.
No events are deleted — compression is additive, never destructive.

═══ MODE AWARENESS ═══  # mode-awareness-d''',
    marker="compression-oracle-d",
)

# ── tools/__init__.py: import compression_tools ───────────────────────────────
patch(init,
    old='from .mode_tools import (  # mode-master-import-d',
    new='''\
from .compression_tools import (  # compression-import-d
    ContextStatsTool,
    CompressContextTool,
    ReadCompressedContextTool,
)
from .mode_tools import (  # mode-master-import-d''',
    marker="compression-import-d",
)

# ── tools/__init__.py: add to __all__ ────────────────────────────────────────
patch(init,
    old='    "ModeStatusTool",             # mode-master-all-d',
    new='''\
    "ContextStatsTool",           # compression-all-d
    "CompressContextTool",
    "ReadCompressedContextTool",
    "ModeStatusTool",             # mode-master-all-d''',
    marker="compression-all-d",
)

print("M36 compression: all patches applied.")
PYEOF

cp "$REPO/aria-compression/tests/test_compression.py" "$REPO/tests/test_compression.py"
echo "==> M36 done. Run: .venv/bin/python -m pytest tests/test_compression.py -q"
