#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_vision_deep.sh — Aria gains deep image understanding (v0.2.42.0)
#
#  Delivers 3 new Tier 0 vision tools that go far beyond the basic
#  image_caption tool:
#
#    analyze_image          — deep structured analysis (7 focus modes)
#    extract_text_from_image — OCR-focused text extraction
#    compare_images         — before/after / A-B comparison
#
#  All three tools:
#    • Use Ollama vision model (llava:7b by default, configurable via
#      AGENT_VISION_MODEL env var)
#    • Fall back to Claude claude-haiku-4-5 API if Ollama vision fails
#      (requires ANTHROPIC_API_KEY)
#    • Are Tier 0 — read-only, no VRAM lock needed (llava:7b fits in
#      ~4GB; on the 8GB GTX 1070 this runs alongside qwen3:8b in sequence)
#
#  Recommendation: pull a better vision model for superior results:
#    ollama pull llava:13b         # better quality, needs ~8GB VRAM alone
#    ollama pull llava-next:34b    # best local quality, needs A100/RTX4090
#    ollama pull moondream:1.8b    # fastest, lowest VRAM (~1GB)
#
#  Idempotent. Backs up __init__.py before patching.
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
ts(){ date +%Y%m%d%H%M%S; }

echo "→ installing tools/image_analyze.py"
cp "$HERE/payload/src/sovereign_agent/tools/image_analyze.py" "$TOOLS/image_analyze.py"
echo "  ✓ tools/image_analyze.py"

echo "→ patching tools/__init__.py"
backup "$INIT" 2>/dev/null || cp "$INIT" "$INIT.bak.$(ts)"
python3 - "$INIT" <<'PYEOF'
import sys, pathlib

init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

if "from .image_analyze import" in src:
    print("  ↷ image_analyze imports already present — skipping")
else:
    OLD = "from .image_caption import ImageCaptionTool"
    NEW = (
        "from .image_analyze import AnalyzeImageTool, CompareImagesTool, ExtractTextFromImageTool\n"
        "from .image_caption import ImageCaptionTool"
    )
    if OLD not in src:
        print("✗ image_caption import anchor not found in __init__.py", file=sys.stderr)
        sys.exit(1)
    src = src.replace(OLD, NEW, 1)
    print("  ✓ image_analyze imports added")

for name in ('"AnalyzeImageTool"', '"CompareImagesTool"', '"ExtractTextFromImageTool"'):
    if name in src:
        print(f"  ↷ {name} already in __all__ — skipping")
        continue
    OLD_ALL = '    "ImageCaptionTool",'
    NEW_ALL = (
        '    "AnalyzeImageTool",\n'
        '    "CompareImagesTool",\n'
        '    "ExtractTextFromImageTool",\n'
        '    "ImageCaptionTool",'
    )
    if OLD_ALL in src:
        src = src.replace(OLD_ALL, NEW_ALL, 1)
        print("  ✓ image_analyze tools added to __all__")
    break

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

echo "→ compile check"
python3 -m py_compile "$TOOLS/image_analyze.py" "$INIT"
echo "  ✓ compiles"

cp "$HERE/tests/test_vision_deep.py" "$ROOT/tests/test_vision_deep.py"
echo "  ✓ tests/test_vision_deep.py installed"
python3 -m py_compile "$ROOT/tests/test_vision_deep.py"
echo "  ✓ test compiles"

echo
echo "✓ done. next:"
echo "    pytest tests/test_vision_deep.py -v"
echo "    # ensure llava is pulled: ollama pull llava:7b"
echo "    # try: analyze_image(path='/path/to/screenshot.png', focus='text')"
echo "    # try: compare_images(path_a='/old.png', path_b='/new.png')"
