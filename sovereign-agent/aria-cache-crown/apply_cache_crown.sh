#!/usr/bin/env bash
# apply_cache_crown.sh — M33: runtime response cache for T0 tools
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M33 cache-crown: $REPO"

cp "$REPO/aria-cache-crown/payload/src/sovereign_agent/cache.py" \
   "$REPO/src/sovereign_agent/cache.py"
echo "  OK   copied cache.py"

cp "$REPO/aria-cache-crown/payload/src/sovereign_agent/tools/cache_tools.py" \
   "$REPO/src/sovereign_agent/tools/cache_tools.py"
echo "  OK   copied cache_tools.py"

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

# ── loop.py: import ResponseCache ────────────────────────────────────────────
patch(loop,
    old='from .reflector import reflect\nfrom .tools.base import Tool, ToolResult',
    new='from .cache import ResponseCache as _ResponseCache  # cache-crown-import-d\nfrom .reflector import reflect\nfrom .tools.base import Tool, ToolResult',
    marker="cache-crown-import-d",
)

# ── loop.py: module-level singleton ─────────────────────────────────────────
patch(loop,
    old='_PATH_TOOLS: frozenset[str] = frozenset({',
    new='_response_cache = _ResponseCache()  # T0 response cache, session-scoped  # cache-crown-singleton-d\n\n_PATH_TOOLS: frozenset[str] = frozenset({',
    marker="cache-crown-singleton-d",
)

# ── loop.py: cache check before tool-start-d ─────────────────────────────────
patch(loop,
    old='                _record("tool-start-d", {  # observatory-tool-start-d',
    new='''\
                # ── Cache check (T0 read-only tools only) ──────────────  # cache-crown-dispatch-d
                if meta.tier == 0:
                    _cached_content = _response_cache.get(tool_name, args)
                    if _cached_content is not None:
                        _record("cache-hit-d", {"tool": tool_name})
                        messages.append({"role": "tool", "name": tool_name, "content": _cached_content})
                        continue

                _record("tool-start-d", {  # observatory-tool-start-d''',
    marker="cache-crown-dispatch-d",
)

# ── loop.py: cache store after execute ───────────────────────────────────────
patch(loop,
    old='                messages.append({\n                    "role": "tool", "name": tool_name, "content": content,\n                })',
    new='''\
                if meta.tier == 0 and result.ok:  # cache-crown-store-d
                    _response_cache.put(tool_name, args, content)
                messages.append({
                    "role": "tool", "name": tool_name, "content": content,
                })''',
    marker="cache-crown-store-d",
)

# ── loop.py: CACHE CROWN doctrine ────────────────────────────────────────────
patch(loop,
    old='═══ WORKFLOW ═══  # workflow-wire-d',
    new='''\
═══ CACHE CROWN ═══  # cache-crown-doctrine-d
T0 tools (read/search/query) are cached per session. Repeated calls with
identical arguments return instantly from memory — no redundant DB hits.
  cache_stats()          → hit rate, size, tokens saved this session (T0)
  cache_flush(tool_name) → clear one tool\'s entries or all (T1)
Cache is love: every cache hit is a cycle returned for better work.

═══ WORKFLOW ═══  # workflow-wire-d''',
    marker="cache-crown-doctrine-d",
)

# ── tools/__init__.py: import cache_tools ────────────────────────────────────
patch(init,
    old='from .prompt_forge import (  # prompt-forge-import-d',
    new='''\
from .cache_tools import (  # cache-crown-import-d
    CacheStatsTool,
    CacheFlushTool,
)
from .prompt_forge import (  # prompt-forge-import-d''',
    marker="cache-crown-import-d",
)

# ── tools/__init__.py: add to __all__ ────────────────────────────────────────
patch(init,
    old='    "ForgePromptTool",           # prompt-forge-all-d',
    new='''\
    "CacheStatsTool",             # cache-crown-all-d
    "CacheFlushTool",
    "ForgePromptTool",           # prompt-forge-all-d''',
    marker="cache-crown-all-d",
)

print("M33 cache-crown: all patches applied.")
PYEOF

cp "$REPO/aria-cache-crown/tests/test_cache_crown.py" "$REPO/tests/test_cache_crown.py"
echo "==> M33 done. Run: .venv/bin/python -m pytest tests/test_cache_crown.py -q"
