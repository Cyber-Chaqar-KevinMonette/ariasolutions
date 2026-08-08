"""sprite_qa.py — quality assurance for generated game sprites.

Kevin (2026-08-02): "the more generative the better, as long as there is
production grade quality assurance across the board at every step." Real
gap found live: place_game_sprite.py's first-ever generation (Ember Keep,
"a small glowing campfire ember... transparent background") came back as
a multi-panel grid of a dozen different campfires on an opaque white
background — text-to-image diffusion has no concept of alpha from a plain
prompt, and turbo-distilled models at 4 steps readily produce contact-
sheet-style outputs unless steered away from it. Wiring that straight into
a Sprite2D texture would have shipped a broken, ugly, non-transparent
"sprite" with zero warning.

Two real fixes, not cosmetic ones:
  1. remove_background() — rembg (FOSS, MIT, local ONNX U2Net, no external
     API) actually mattes the subject out, producing real RGBA alpha. This
     is the only reliable fix for the transparency problem; a prompt alone
     cannot produce it.
  2. check_sprite_quality() — a cheap, deterministic sanity pass AFTER
     matting: corrupt/unreadable file, degenerate (near-blank or
     near-solid) output, and "nothing survived background removal" (the
     matting model found no distinct foreground, usually because the
     source was itself degenerate) all fail loudly instead of silently
     shipping. This does NOT (and cannot reliably) detect "is this a
     multi-panel grid" — that's addressed upstream instead, by steering
     the prompt away from it (see place_game_sprite.py's
     ANTI_COLLAGE_TERMS), the same lesson every sprite-gen guide gives:
     fix generation conditioning, don't try to detect its failure after
     the fact.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

__all__ = [
    "ANTI_COLLAGE_TERMS",
    "SpriteQAResult",
    "remove_background",
    "check_sprite_quality",
]

# Prepended to every place_game_sprite negative_prompt — the actual fix
# for the contact-sheet failure mode observed live, steering generation
# away from it rather than trying to detect it after the fact.
ANTI_COLLAGE_TERMS = (
    "collage, grid, contact sheet, multiple panels, multiple views, "
    "multiple objects, tiled, sprite sheet, comparison, variations"
)

# A near-uniform image (flat color, failed generation, or a background
# that survived matting untouched) has very low per-channel stddev.
_DEGENERATE_STDDEV_THRESHOLD = 3.0
# After background removal, the alpha channel should have real
# variance — some transparent, some opaque. Below this, either nothing
# was detected as foreground (alpha ~all 0) or nothing was removed at
# all (alpha ~all 255, matting no-op).
_ALPHA_STDDEV_THRESHOLD = 5.0


@dataclass
class SpriteQAResult:
    ok: bool
    warnings: list[str] = field(default_factory=list)
    png_bytes: bytes | None = None


def remove_background(png_bytes: bytes) -> bytes:
    """Real background removal via rembg (local U2Net, CPU). Returns RGBA
    PNG bytes with an actual alpha channel — the only reliable way to get
    transparency out of a plain text-to-image prompt."""
    from rembg import remove

    return remove(png_bytes)


def _image_stats(png_bytes: bytes):
    from PIL import Image
    import numpy as np

    img = Image.open(io.BytesIO(png_bytes))
    img.load()  # force-decode now — a truncated/corrupt file raises here
    return img, np.asarray(img)


def check_sprite_quality(
    png_bytes: bytes, *, expected_width: int, expected_height: int,
) -> SpriteQAResult:
    """Sanity pass on a matted (RGBA) sprite. Hard-fails (ok=False) only
    on genuinely unusable output — corrupt file, wrong dimensions,
    degenerate/blank image, or a matting pass that found no real
    foreground. Soft issues are reported as warnings on an ok=True
    result rather than blocking — false positives here would just make
    the tool annoying to use for legitimate unusual art."""
    warnings: list[str] = []

    try:
        img, arr = _image_stats(png_bytes)
    except Exception as exc:  # noqa: BLE001 — any decode failure is disqualifying
        return SpriteQAResult(ok=False, warnings=[f"unreadable image: {exc!r}"])

    if img.width != expected_width or img.height != expected_height:
        return SpriteQAResult(
            ok=False,
            warnings=[f"dimension mismatch: got {img.width}x{img.height}, "
                      f"expected {expected_width}x{expected_height}"],
        )

    rgb = arr[..., :3] if arr.ndim == 3 and arr.shape[-1] >= 3 else arr
    if float(rgb.std()) < _DEGENERATE_STDDEV_THRESHOLD:
        return SpriteQAResult(
            ok=False,
            warnings=[f"degenerate image — near-uniform color "
                      f"(stddev={float(rgb.std()):.2f}), generation likely failed"],
        )

    if img.mode == "RGBA" or (arr.ndim == 3 and arr.shape[-1] == 4):
        alpha = arr[..., 3]
        alpha_std = float(alpha.std())
        if alpha_std < _ALPHA_STDDEV_THRESHOLD:
            mean = float(alpha.mean())
            if mean < 10:
                return SpriteQAResult(
                    ok=False,
                    warnings=["background removal found no foreground — "
                              "alpha is effectively all-transparent"],
                )
            return SpriteQAResult(
                ok=False,
                warnings=["background removal made no change — alpha is "
                          "effectively all-opaque, matting likely failed"],
            )
    else:
        warnings.append(f"no alpha channel present (mode={img.mode!r}) — "
                        "background removal may not have run")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return SpriteQAResult(ok=True, warnings=warnings, png_bytes=buf.getvalue())
