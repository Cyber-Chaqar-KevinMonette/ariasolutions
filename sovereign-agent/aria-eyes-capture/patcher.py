"""patcher.py — Workstream F: wire Aria's eyes' actual frame-grab call.

`senses/eyes.py::look_world()` deliberately reports camera *readiness*
but never grabs a frame — a documented, intentional design choice
("capturing the world is perception of a real space, kept honest +
opt-in"). The plan's own F item asks to "wire the actual capture call
now so it lights up the moment a camera/iPhone-webcam appears — don't
leave that one call as the last mile forever," while respecting that
same opt-in design.

This patcher does NOT touch `look_world()`/`see()` at all — they stay
pure read-only status reports, unchanged. Instead it ADDS a new,
separate, explicit function `capture_frame()` that a caller (Aria, a
new Tier-1 tool) must invoke deliberately to actually grab a still
frame — preserving "capturing the world stays opt-in" exactly as
`senses_tools.py`'s own module docstring already states.

No camera exists on this dev machine (confirmed:
`devices.discover_cameras()` returns `[]` here), so the "actually grabs
a frame" path is tested via a mocked subprocess call — genuinely
untested against real hardware, honestly documented as such — but the
mechanism is real: the moment a `/dev/video*` device and ffmpeg/fswebcam
exist, this call works with zero further wiring.

Anchored span patches against the CURRENT live files (same discipline
as every other patcher this session — not a full-file replace).
"""
from __future__ import annotations

MARK = "eyes-capture-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ═══════════════════════════════════════════════════════════════════════
# senses/eyes.py — the new capture_frame() function
# ═══════════════════════════════════════════════════════════════════════

EYES_IMPORT_ANCHOR = (
    "import shutil\n"
    "from dataclasses import dataclass\n"
    "\n"
    "from . import devices\n"
)
EYES_IMPORT_NEW = (
    "import shutil\n"
    "import subprocess\n"
    "import tempfile\n"
    "import uuid\n"
    "from dataclasses import dataclass\n"
    "from pathlib import Path\n"
    "\n"
    "from . import devices\n"
)

LOOK_WORLD_END_ANCHOR = (
    '    # A backend + a device exist: capture is possible. We report readiness (actual frame grab is the operator\'s\n'
    '    # call — capturing the world is perception of a real space, kept honest + opt-in).\n'
    '    return Sight("camera", True, f"Camera {cams[0].id} ready via {backend}. World-sight available.",\n'
    '                 data={"device": cams[0].id, "backend": backend})\n'
)
CAPTURE_FRAME_FUNCTION = f'''

# {MARK} — the actual frame-grab call look_world() deliberately defers.
# NEVER called automatically by look_world()/see() — a caller must invoke
# this explicitly, preserving "capturing the world stays opt-in" exactly
# as senses_tools.py's own module docstring already states.
def capture_frame(device=None, *, output_path=None, timeout: int = 5) -> Sight:
    """Grab ONE still frame from a camera. Resilient: returns a Sight with
    available=False (never raises) on any missing camera/backend/subprocess
    failure — same discipline as look_world(). `device` defaults to the
    first discovered camera; `output_path` defaults to a fresh temp file."""
    if device is None:
        cams = devices.discover_cameras()
        if not cams:
            return Sight("camera", False, "No camera present — cannot capture a frame.")
        device = cams[0]
    backend = next((b for b in ("ffmpeg", "fswebcam") if shutil.which(b)), None)
    if backend is None:
        return Sight("camera", False,
                     f"Camera {{device.id}} present but no capture backend (install ffmpeg/fswebcam).")

    if output_path is None:
        output_path = Path(tempfile.gettempdir()) / f"aria-sight-{{uuid.uuid4().hex[:8]}}.jpg"
    dev_path = device.name or f"/dev/{{device.id}}"

    try:
        if backend == "ffmpeg":
            cmd = ["ffmpeg", "-y", "-f", "v4l2", "-i", dev_path, "-frames:v", "1", str(output_path)]
        else:  # fswebcam
            cmd = ["fswebcam", "-d", dev_path, "--no-banner", str(output_path)]
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if result.returncode != 0 or not output_path.exists():
            stderr = result.stderr.decode("utf-8", errors="replace")[:200]
            return Sight("camera", False, f"Capture failed via {{backend}}: {{stderr}}")
        return Sight("camera", True, f"Frame captured via {{backend}}.",
                     data={{"path": str(output_path), "device": device.id, "backend": backend}})
    except Exception as exc:  # noqa: BLE001 — same resilience discipline as look_world()
        return Sight("camera", False, f"Capture error: {{exc!r}}")
'''


def patch_eyes(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, EYES_IMPORT_ANCHOR, EYES_IMPORT_NEW, label="eyes import anchor")
    text = _replace_once(
        text, LOOK_WORLD_END_ANCHOR, LOOK_WORLD_END_ANCHOR + CAPTURE_FRAME_FUNCTION,
        label="look_world end anchor",
    )
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# tools/senses_tools.py — the new Tier-1 CaptureFrameTool
# ═══════════════════════════════════════════════════════════════════════

SENSES_TOOLS_END_ANCHOR = (
    '        except Exception as exc:  # noqa: BLE001\n'
    '            return ToolResult(ok=False, error=f"read_error: {exc!r}")\n'
    '        return ToolResult(ok=True, output=out, metadata={"source": "perception_status"})\n'
)
CAPTURE_FRAME_TOOL = f'''

class CaptureFrameTool(Tool):  # {MARK}
    """Actually grab ONE still frame from a camera — the explicit, opt-in
    action perception_status deliberately never takes on its own. Tier 1
    (a real-world action + a new file on disk), not Tier 0, to keep that
    boundary honest.

    FAILURE MODES: no_camera, no_backend, capture_failed
    """

    name = "capture_frame"
    tier = 1
    description = (
        "Grab ONE still frame from a camera, if present, and save it to disk. "
        "This is the explicit, opt-in capture action — perception_status only "
        "reports readiness, it never captures. Call this when Aria genuinely "
        "needs to see the world right now. Resilient: returns available=False "
        "(never raises) if no camera or capture backend (ffmpeg/fswebcam) is "
        "present. FAILURE MODES: no_camera, no_backend, capture_failed"
    )
    failure_modes = ("no_camera", "no_backend", "capture_failed")

    class Args(BaseModel):
        timeout: int = 5
        """Capture timeout in seconds."""

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            from sovereign_agent.senses import eyes
            sight = eyes.capture_frame(timeout=args.timeout)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"capture_failed: {{exc!r}}")
        if not sight.available:
            return ToolResult(ok=False, error=sight.detail)
        return ToolResult(ok=True, output=sight.to_dict(), metadata={{"source": "capture_frame"}})
'''


def patch_senses_tools(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(
        text, SENSES_TOOLS_END_ANCHOR, SENSES_TOOLS_END_ANCHOR + CAPTURE_FRAME_TOOL,
        label="senses_tools end anchor",
    )
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# tools/__init__.py — register the new tool (import + __all__ together,
# per L's own lesson: a missing __all__ entry is a real, recurring bug class)
# ═══════════════════════════════════════════════════════════════════════

TOOLS_IMPORT_ANCHOR = "from .senses_tools import PerceptionStatusTool  # senses-import-d\n"
TOOLS_IMPORT_NEW = (
    TOOLS_IMPORT_ANCHOR
    + f"from .senses_tools import CaptureFrameTool  # {MARK}\n"
)

TOOLS_ALL_ANCHOR = '    "PerceptionStatusTool",  # senses-all-d\n'
TOOLS_ALL_NEW = (
    TOOLS_ALL_ANCHOR
    + f'    "CaptureFrameTool",  # {MARK}\n'
)


def patch_tools_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, TOOLS_IMPORT_ANCHOR, TOOLS_IMPORT_NEW, label="tools import anchor")
    text = _replace_once(text, TOOLS_ALL_ANCHOR, TOOLS_ALL_NEW, label="tools __all__ anchor")
    return text, True
