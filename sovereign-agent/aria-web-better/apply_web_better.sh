#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_web_better.sh — Clean web extraction and multi-hop research
#
#  web_fetch returns raw HTML. web_search returns titles and URLs.
#  Neither gives Aria clean, readable content. This closes the gap.
#
#  Prerequisites (optional but recommended):
#    .venv/bin/pip install markdownify
#  (Falls back to tag-stripping without it.)
#
#  Changes:
#  1. Install tools/web_better.py
#  2. Patch tools/__init__.py — imports + __all__
#  3. Patch loop.py — add WEB RESEARCH guidance
#
#  Idempotent. Backs up patched files.
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
TOOLS="$PKG/tools"
INIT="$TOOLS/__init__.py"
LOOP="$PKG/loop.py"
ts(){ date +%Y%m%d%H%M%S; }

# ── 1. Install web_better.py ───────────────────────────────────────────────
echo "→ installing tools/web_better.py"
cp "$HERE/payload/src/sovereign_agent/tools/web_better.py" "$TOOLS/web_better.py"
echo "  ✓ web_better.py"

# ── 2. Patch tools/__init__.py ─────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

IMPORT_MARKER = "# web-better-import-d"
if IMPORT_MARKER in src:
    print("  ↷ web_better import already present — skipping")
else:
    new_import = (
        "from .web_better import WebExtractTool, WebResearchTool  "
        + IMPORT_MARKER + "\n"
    )
    for anchor in ("from .web_fetch import", "from .read_file import ReadFileTool"):
        if anchor in src:
            src = src.replace(anchor, new_import + anchor, 1)
            print("  ✓ web_better imports added")
            break
    else:
        last_from = src.rfind("\nfrom .")
        if last_from >= 0:
            insert_at = src.find("\n", last_from + 1) + 1
            src = src[:insert_at] + new_import + src[insert_at:]
            print("  ✓ web_better imports appended")
        else:
            print("✗ no import anchor found", file=sys.stderr)
            sys.exit(1)

ALL_MARKER = "# web-better-all-d"
if ALL_MARKER in src:
    print("  ↷ web_better __all__ already present — skipping")
else:
    new_all = (
        '    "WebExtractTool",\n'
        '    "WebResearchTool",  ' + ALL_MARKER + '\n'
    )
    for anchor in ('    "WebFetchTool",', '    "ReadFileTool",'):
        if anchor in src:
            src = src.replace(anchor, new_all + anchor, 1)
            print("  ✓ web_better added to __all__")
            break
    else:
        print("  ⚠ __all__ anchor not found — skipping")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 3. Patch loop.py — WEB RESEARCH section ───────────────────────────────
echo "→ patching loop.py"
cp "$LOOP" "$LOOP.bak.$(ts)"

python3 - "$LOOP" <<'PYEOF'
import sys, pathlib
loop = pathlib.Path(sys.argv[1])
src = loop.read_text(encoding="utf-8")

MARKER = "# web-better-d"
if MARKER in src:
    print("  ↷ WEB RESEARCH section already present — skipping")
else:
    section = (
        "\n═══ WEB RESEARCH ═══\n"
        "Prefer these over raw web_fetch / web_search for research tasks:\n"
        "\n"
        "  web_extract(url)                 — fetch URL → clean readable text\n"
        "  web_research(query, depth=3)     — search + extract top N → synthesized\n"
        "\n"
        "web_extract supports: github.com, docs.python.org, stackoverflow.com,\n"
        "wikipedia.org, arxiv.org, readthedocs.io, developer.mozilla.org, pypa.io,\n"
        "docs.pydantic.dev, textual.textualize.io, and more.\n"
        "\n"
        "Use web_research for open-ended questions. Use web_extract when you have\n"
        "a specific URL and want clean content (not raw HTML).\n"
        "  " + MARKER + "\n\n"
    )
    for anchor in ("# behavior-self-d\n", "# palace-write-d\n", "# lessons-loop-d\n",
                   "# know-thyself-d\n", "═══ COMPLETION ═══"):
        if anchor in src:
            if anchor == "═══ COMPLETION ═══":
                src = src.replace(anchor, section + anchor, 1)
            else:
                src = src.replace(anchor, anchor + section, 1)
            print("  ✓ WEB RESEARCH section added")
            break
    else:
        print("  ⚠ no anchor found — skipping loop.py patch")

loop.write_text(src, encoding="utf-8")
print("  ✓ loop.py written")
PYEOF

# ── 4. Compile checks ──────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$TOOLS/web_better.py" "$INIT" "$LOOP"
echo "  ✓ all files compile"

cp "$HERE/tests/test_web_better.py" "$ROOT/tests/test_web_better.py"
python3 -m py_compile "$ROOT/tests/test_web_better.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. Clean web extraction is available."
echo
echo "  2 new Tier 0 tools:"
echo "    web_extract   — URL → clean readable text (HTML stripped)"
echo "    web_research  — search + extract → synthesized block with sources"
echo
echo "  Optional (better output): .venv/bin/pip install markdownify"
echo
echo "  run: pytest tests/test_web_better.py -v"
