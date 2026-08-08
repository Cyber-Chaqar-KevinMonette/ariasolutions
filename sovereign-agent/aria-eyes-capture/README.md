# aria-eyes-capture — Workstream F (eyes item)

Wires Aria's actual camera frame-grab call — the one deliberately-deferred
"last mile" the plan named: *"`look_world()` reports readiness but never
grabs a frame... wire the actual capture call now so it lights up the
moment a camera/iPhone-webcam appears."*

## What this ships

Three anchored patches, no new file:

- `src/sovereign_agent/senses/eyes.py` — a new `capture_frame()` function.
  **`look_world()`/`see()` are completely untouched** (proven by a
  dedicated regression test comparing the exact original function body
  against the patched file) — capture stays explicit and opt-in, never
  automatic, exactly as `senses_tools.py`'s own module docstring already
  states ("Capturing the world stays opt-in/operator-gated; this reports
  readiness").
- `src/sovereign_agent/tools/senses_tools.py` — a new **Tier 1**
  `CaptureFrameTool` wrapping `capture_frame()`. Tier 1, not Tier 0
  (`PerceptionStatusTool`'s tier), because this is a real-world action
  that writes a new file to disk — not a pure status read.
- `src/sovereign_agent/tools/__init__.py` — import + `__all__` entry for
  `CaptureFrameTool`, added together in the same patch (L's own lesson
  this session: a missing `__all__` entry is a real, recurring bug class
  — never add one without the other).

## Honesty about what's actually tested

No camera exists on the machine this was built on (confirmed directly:
`devices.discover_cameras()` returns `[]` here). The "actually grabs a
frame" path is tested via a mocked `subprocess.run` call — a real,
meaningful test of the mechanism's logic (backend selection, command
construction, error handling), but **not** a test against real hardware.
The moment a `/dev/video*` device and ffmpeg/fswebcam exist on a machine
running this code, `capture_frame()` works with zero further wiring —
that's the whole point — but this session cannot prove that empirically
without the hardware, and says so plainly rather than overclaiming.

## Tests

`tests/test_patcher.py` (14 tests) — all three patches apply cleanly
against the CURRENT live files, are idempotent, compile, `look_world()`'s
exact original body is proven unchanged, `capture_frame()` is confirmed
never called internally (only defined), the new tool is confirmed Tier 1,
import + `__all__` are confirmed added together, a missing anchor raises
`PatchError`.

`tests/test_eyes_capture.py` (9 tests, staging only, shadow-copy) /
`tests/test_eyes_capture_live.py` (same 9, promoted to live `tests/` after
apply, plain imports, zero `sys.modules` manipulation): `look_world()`/
`see()` still work exactly as before; `capture_frame()` reports
unavailable when no camera or no backend is present; a mocked ffmpeg call
succeeds and returns the expected path/backend; a failing subprocess call
is reported as an honest failure (never raises); a subprocess exception
is caught and reported (never raises); the new tool returns an error
`ToolResult` with no camera and a success `ToolResult` with a mocked one;
the tool is confirmed present in `tools.__all__`.

Reversible: restore all 3 files from the backup.
