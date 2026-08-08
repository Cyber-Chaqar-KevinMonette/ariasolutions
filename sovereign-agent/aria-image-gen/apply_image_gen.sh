#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_image_gen.sh — Aria gains local image generation capability
#
#  Delivers one new Tier 1 tool:
#
#    generate_image   — text-to-image via FLUX.1-schnell (or SDXL-Turbo /
#                       SD2.1 as fallbacks). VRAM-serialized. Thread-safe.
#
#  Tier 1 because it writes PNG files to data_dir/images/generated/.
#  VRAM-gated: checks free VRAM before starting, uses vram_lock() so
#  generation never races against qwen3:8b.
#
#  Prerequisites (install before first use):
#    .venv/bin/pip install diffusers transformers accelerate torch
#    # FLUX.1-schnell is gated — accept HuggingFace license:
#    # huggingface-cli login && huggingface-cli download black-forest-labs/FLUX.1-schnell
#
#  After apply, in the cockpit ask:
#    generate_image(prompt="a sunset over mountains, oil painting, 8k")
#    # Then immediately:
#    analyze_image(path="<returned path>")
#
#  Idempotent. Backs up __init__.py before patching.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$PWD}"

# Walk up to find repo root
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

echo "→ installing tools/image_generate.py"
cp "$HERE/payload/src/sovereign_agent/tools/image_generate.py" "$TOOLS/image_generate.py"
echo "  ✓ tools/image_generate.py"

echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib

init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

if "from .image_generate import" in src:
    print("  ↷ image_generate import already present — skipping")
else:
    # Insert before image_caption (which may or may not already have image_analyze before it)
    anchor = "from .image_caption import ImageCaptionTool"
    if anchor not in src:
        # Try the image_analyze anchor if vision_deep was already applied
        anchor = "from .image_analyze import"
        if anchor not in src:
            print("✗ no image import anchor found in __init__.py", file=sys.stderr)
            sys.exit(1)
        # Insert before image_analyze
        src = src.replace(
            anchor,
            "from .image_generate import GenerateImageTool\n" + anchor,
            1,
        )
    else:
        src = src.replace(
            anchor,
            "from .image_generate import GenerateImageTool\n" + anchor,
            1,
        )
    print("  ✓ GenerateImageTool import added")

if '"GenerateImageTool"' in src:
    print("  ↷ GenerateImageTool already in __all__ — skipping")
else:
    old_all = '    "ImageCaptionTool",'
    new_all = '    "GenerateImageTool",\n    "ImageCaptionTool",'
    if old_all in src:
        src = src.replace(old_all, new_all, 1)
        print("  ✓ GenerateImageTool added to __all__")
    else:
        # ImageCaptionTool may already have been displaced by AnalyzeImageTool
        old_all2 = '    "AnalyzeImageTool",'
        new_all2 = '    "GenerateImageTool",\n    "AnalyzeImageTool",'
        if old_all2 in src:
            src = src.replace(old_all2, new_all2, 1)
            print("  ✓ GenerateImageTool added to __all__ (after AnalyzeImageTool)")
        else:
            print("  ⚠ could not locate __all__ anchor — add GenerateImageTool manually")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

echo "→ compile check"
python3 -m py_compile "$TOOLS/image_generate.py" "$INIT"
echo "  ✓ compiles"

cp "$HERE/tests/test_image_gen.py" "$ROOT/tests/test_image_gen.py"
echo "  ✓ tests/test_image_gen.py installed"
python3 -m py_compile "$ROOT/tests/test_image_gen.py"
echo "  ✓ test compiles"

echo
echo "✓ done. prerequisites before first use:"
echo "    .venv/bin/pip install diffusers transformers accelerate torch"
echo "    # For FLUX.1-schnell (best quality, needs HF login):"
echo "    # huggingface-cli login"
echo "    # huggingface-cli download black-forest-labs/FLUX.1-schnell"
echo "    # For SDXL-Turbo (no login needed):"
echo "    # python -c \"from diffusers import AutoPipelineForText2Image; AutoPipelineForText2Image.from_pretrained('stabilityai/sdxl-turbo')\""
echo
echo "    pytest tests/test_image_gen.py -v"
echo
echo "    # In cockpit:"
echo "    generate_image(prompt='a photorealistic red apple, studio lighting')"
