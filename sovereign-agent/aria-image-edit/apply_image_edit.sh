#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_image_edit.sh — Aria gains image editing (img2img + inpainting)
#
#  Delivers two new Tier 1 tools:
#
#    edit_image    — transform an existing image with a text prompt (img2img).
#                   Change style, lighting, season, mood, genre.
#                   Uses SDXL-Turbo (fast) or SD2.1 (quality).
#
#    inpaint_image — fill a masked region with AI-generated content.
#                   Requires source + mask image (white=repaint).
#                   Uses SD2-inpainting model.
#
#  VRAM: both tools use vram_lock. SDXL-Turbo img2img: ~5.5GB.
#        SD2 inpainting: ~4GB.
#
#  Prerequisites (same as image_gen):
#    .venv/bin/pip install diffusers transformers accelerate torch Pillow
#
#  After apply, in the cockpit:
#    edit_image(path='/path/to/photo.jpg', prompt='oil painting style', strength=0.5)
#    inpaint_image(path='/source.png', mask_path='/mask.png', prompt='blue sky')
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

echo "→ installing tools/image_edit.py"
cp "$HERE/payload/src/sovereign_agent/tools/image_edit.py" "$TOOLS/image_edit.py"
echo "  ✓ tools/image_edit.py"

echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib

init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

if "from .image_edit import" in src:
    print("  ↷ image_edit import already present — skipping")
else:
    # Use image_generate or image_caption as anchor
    for anchor in (
        "from .image_generate import GenerateImageTool",
        "from .image_caption import ImageCaptionTool",
        "from .image_analyze import",
    ):
        if anchor in src:
            src = src.replace(
                anchor,
                "from .image_edit import EditImageTool, InpaintImageTool\n" + anchor,
                1,
            )
            print("  ✓ image_edit imports added")
            break
    else:
        print("✗ no image import anchor found in __init__.py", file=sys.stderr)
        sys.exit(1)

for name in ('"EditImageTool"', '"InpaintImageTool"'):
    if name in src:
        print(f"  ↷ {name} already in __all__ — skipping")
        continue
    for old_all, new_all in (
        ('    "GenerateImageTool",', '    "EditImageTool",\n    "InpaintImageTool",\n    "GenerateImageTool",'),
        ('    "ImageCaptionTool",',  '    "EditImageTool",\n    "InpaintImageTool",\n    "ImageCaptionTool",'),
        ('    "AnalyzeImageTool",',  '    "EditImageTool",\n    "InpaintImageTool",\n    "AnalyzeImageTool",'),
    ):
        if old_all in src:
            src = src.replace(old_all, new_all, 1)
            print("  ✓ EditImageTool, InpaintImageTool added to __all__")
            break
    break  # only need to insert once (both names added together)

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

echo "→ compile check"
python3 -m py_compile "$TOOLS/image_edit.py" "$INIT"
echo "  ✓ compiles"

cp "$HERE/tests/test_image_edit.py" "$ROOT/tests/test_image_edit.py"
echo "  ✓ tests/test_image_edit.py installed"
python3 -m py_compile "$ROOT/tests/test_image_edit.py"
echo "  ✓ test compiles"

echo
echo "✓ done. prerequisites:"
echo "    .venv/bin/pip install diffusers transformers accelerate torch Pillow"
echo "    pytest tests/test_image_edit.py -v"
echo
echo "    # In cockpit:"
echo "    edit_image(path='/absolute/path/to/photo.jpg', prompt='oil painting style', strength=0.5)"
echo "    inpaint_image(path='/source.png', mask_path='/mask.png', prompt='replace with blue sky')"
