#!/usr/bin/env bash
# apply_browser_crown.sh — M50: Stateful Web Browser (httpx + optional playwright)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M50 browser-crown: $REPO"

cp "$REPO/aria-browser-crown/payload/src/sovereign_agent/browser.py" \
   "$REPO/src/sovereign_agent/browser.py"
echo "  OK   copied browser.py"

cp "$REPO/aria-browser-crown/payload/src/sovereign_agent/tools/browser_tools.py" \
   "$REPO/src/sovereign_agent/tools/browser_tools.py"
echo "  OK   copied browser_tools.py"

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

# ── 1. Doctrine in loop.py (before NOTIFY CROWN) ─────────────────────────────
patch(loop,
    old='═══ NOTIFY CROWN ═══  # notify-crown-d',
    new='''\
═══ BROWSER CROWN ═══  # browser-crown-d
Stateful web browsing — httpx session (cookies persist) + optional playwright for JS.
  browser_status()                          T0 — session state + backend info
  browser_navigate(url)                     T2 — fetch URL (stateful cookies)
  browser_read(format='text')               T0 — read current page
  browser_links(limit, same_domain_only)    T0 — extract links
  browser_search(query, engine='ddg')       T2 — DuckDuckGo search

Workflow: browser_navigate(url) → browser_read() → follow browser_links().
DDG search: browser_search("topic") returns result URLs without JS.
Cookies persist across calls — useful for multi-step documentation reading.
playwright not installed: httpx handles static HTML; JS-heavy sites may be incomplete.
To enable JS: pip install playwright && playwright install chromium.

═══ NOTIFY CROWN ═══  # notify-crown-d''',
    marker="browser-crown-d",
)

# ── 2. Import in tools/__init__.py (before notify-crown-import-d) ─────────────
patch(init,
    old='from .notify_tools import (  # notify-crown-import-d',
    new='''\
from .browser_tools import (  # browser-crown-import-d
    BrowserStatusTool,
    BrowserNavigateTool,
    BrowserReadTool,
    BrowserLinksTool,
    BrowserSearchTool,
)
from .notify_tools import (  # notify-crown-import-d''',
    marker="browser-crown-import-d",
)

# ── 3. __all__ (before notify-crown-all-d) ────────────────────────────────────
patch(init,
    old='    "NotifyTool",                    # notify-crown-all-d',
    new='''\
    "BrowserStatusTool",             # browser-crown-all-d
    "BrowserNavigateTool",
    "BrowserReadTool",
    "BrowserLinksTool",
    "BrowserSearchTool",
    "NotifyTool",                    # notify-crown-all-d''',
    marker="browser-crown-all-d",
)

print("M50 browser-crown: all patches applied.")
PYEOF

cp "$REPO/aria-browser-crown/tests/test_browser_crown.py" \
   "$REPO/tests/test_browser_crown.py"
echo "  OK   copied test_browser_crown.py"

echo "==> M50 done. Run: .venv/bin/python -m pytest tests/test_browser_crown.py -q"
