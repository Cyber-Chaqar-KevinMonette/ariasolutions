"""screen_studio_pane.py — the ✦ screen split-pane: Kevin's own manual
video/screenshot recording studio, living beside chat.

Kevin, 2026-08-01: "integrate a screen recording software into the
cockpit so I can use it as a video recording or screen recording studio
as well" -- alongside fixing his OS-level screenshot key. Existing tools
(tools/record_screen.py, tools/screenshot.py) are built for ARIA to call
herself (bounded single calls); this pane is the human-operated half —
click Start, keep working, click Stop, exactly like a normal recorder.

Same shape as movie_pane.py's MoviePane: a plain VerticalScroll (not a
Screen), lives persistently inside #main, shown via the `screen-split`
CSS class on #main (see cockpit/app.py), never pushed/popped.
"""
from __future__ import annotations

import time
from pathlib import Path

from textual import work
from textual.containers import VerticalScroll
from textual.widgets import Button, Static

from . import screen_recording_session as recsession

__all__ = ["ScreenStudioPane", "capture_screenshot_to_dir"]


def capture_screenshot_to_dir(data_dir: Path) -> tuple[bool, str]:
    """The actual capture logic, pulled out of the @work-decorated worker
    so it's a plain function a test can call directly and synchronously —
    fighting Textual's thread-worker machinery in a test buys nothing a
    real dependency-injected unit test doesn't already cover. grim first
    (matches tools/screenshot.py's TakeScreenshotTool), portal fallback
    for the same COSMIC gap (confirmed live: this machine has no grim)."""
    import asyncio
    import subprocess

    from sovereign_agent.tools.screenshot import _GRIM_CMD, _grim_available

    out_dir = Path(data_dir) / "images" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"screenshot_{int(time.time())}.png"

    if not _grim_available():
        from sovereign_agent.portal_screenshot import capture_screenshot_via_portal

        try:
            portal_path = asyncio.run(capture_screenshot_via_portal())
        except Exception as exc:  # noqa: BLE001
            return False, f"screenshot failed: {exc}"
        if portal_path is None or not portal_path.exists():
            return False, (
                "grim not installed and the desktop portal capture "
                "also failed — sudo apt install grim"
            )
        out_path.write_bytes(portal_path.read_bytes())
        try:
            portal_path.unlink()
        except OSError:
            pass
        return True, f"saved (portal): {out_path}"

    try:
        result = subprocess.run(
            [_GRIM_CMD, str(out_path)], capture_output=True, timeout=10
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"screenshot failed: {exc}"
    ok = (result.returncode == 0 and out_path.exists()
          and out_path.stat().st_size > 0)
    if ok:
        return True, f"saved: {out_path}"
    return False, f"screenshot failed: {result.stderr.decode(errors='replace').strip()}"


class ScreenStudioPane(VerticalScroll):
    """Manual recording studio: start/stop screen video, take a
    screenshot. Base state is hidden — #main.screen-split (cockpit/app.py)
    reveals + widths it, same container-class-toggle pattern movie_pane.py
    and #chat-pane already use."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._recording_handle = None
        self._recording_path: Path | None = None
        self._recording_started_at: float | None = None
        self._timer = None
        # Same busy-guard idiom as MoviePane._busy — refuses a second
        # click outright instead of racing a still-running stop/screenshot.
        self._busy: set[str] = set()

    def _try_start(self, group: str) -> bool:
        if group in self._busy:
            self._toast("still working — wait for it to finish first")
            return False
        self._busy.add(group)
        return True

    def _finish(self, group: str) -> None:
        self._busy.discard(group)

    def compose(self):
        yield Static("", id="screen-pane-header")
        yield Static("", id="screen-pane-status")
        yield Button("● Start Recording", id="screen-pane-record-toggle")
        yield Button("Take Screenshot", id="screen-pane-screenshot")

    def on_mount(self) -> None:
        self._refresh_header()

    def _refresh_header(self) -> None:
        try:
            self.query_one("#screen-pane-header", Static).update(
                "◊ Screen Studio — manual video/screenshot capture"
            )
        except Exception:  # noqa: BLE001
            pass

    def _toast(self, msg: str) -> None:
        try:
            self.query_one("#screen-pane-status", Static).update(msg)
        except Exception:  # noqa: BLE001
            pass

    def _data_dir(self):
        from sovereign_agent.config import SETTINGS

        return SETTINGS.paths.data_dir

    # ── button dispatch ──────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.button.add_class("flash")
        self.set_timer(0.3, lambda: event.button.remove_class("flash"))

        bid = event.button.id
        if bid == "screen-pane-record-toggle":
            self._toggle_recording(); return
        if bid == "screen-pane-screenshot":
            self._take_screenshot(); return

    # ── recording ────────────────────────────────────────────────────────

    def _toggle_recording(self) -> None:
        if self._recording_handle is not None:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        if not self._try_start("screen-studio-record"):
            return
        if not recsession.recording_available():
            self._toast("gst-launch-1.0 or the screen-capture portal isn't available — "
                       "sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-good "
                       "gstreamer1.0-plugins-bad")
            self._finish("screen-studio-record")
            return
        data_dir = self._data_dir()
        if data_dir is None:
            self._toast("data_dir not configured")
            self._finish("screen-studio-record")
            return
        out_dir = recsession.recordings_dir(data_dir)
        ts = int(time.time())
        out_path = out_dir / f"recording_{ts}.mp4"
        self._toast("starting recording…")
        self._start_recording_worker(out_path)

    @work(thread=True, exclusive=True, group="screen-studio-record")
    def _start_recording_worker(self, out_path: Path) -> None:
        try:
            handle = recsession.start(out_path)
        except Exception as exc:  # noqa: BLE001 — includes a portal Start()
            # cancellation ("recording cancelled — no screen/window was
            # picked") when the user closes the OS picker without choosing.
            self.app.call_from_thread(
                self._toast, f"failed to start recording: {exc}"
            )
            self.app.call_from_thread(self._finish, "screen-studio-record")
            return
        self._recording_handle = handle
        self._recording_path = out_path
        self._recording_started_at = time.monotonic()
        self.app.call_from_thread(self._on_recording_started, out_path)

    def _on_recording_started(self, out_path: Path) -> None:
        try:
            self.query_one("#screen-pane-record-toggle", Button).label = "■ Stop Recording"
        except Exception:  # noqa: BLE001
            pass
        self._toast(f"recording… → {out_path}")
        self._timer = self.set_interval(1.0, self._tick_recording_timer)
        self._finish("screen-studio-record")

    def _tick_recording_timer(self) -> None:
        if self._recording_started_at is None:
            return
        elapsed = time.monotonic() - self._recording_started_at
        self._toast(f"recording… {elapsed:.0f}s → {self._recording_path}")

    def _stop_recording(self) -> None:
        if not self._try_start("screen-studio-record"):
            return
        handle = self._recording_handle
        if handle is None:
            self._finish("screen-studio-record")
            return
        self._toast("stopping recording…")
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._stop_recording_worker(handle, self._recording_path)

    @work(thread=True, exclusive=True, group="screen-studio-record-stop")
    def _stop_recording_worker(self, handle, out_path: Path) -> None:
        try:
            result = recsession.stop(handle)
        except Exception as exc:  # noqa: BLE001
            self.app.call_from_thread(self._toast, f"stop failed: {exc}")
            self.app.call_from_thread(self._finish, "screen-studio-record")
            return
        self._recording_handle = None
        self._recording_started_at = None
        wrote_file = out_path is not None and out_path.exists() and out_path.stat().st_size > 0
        if wrote_file:
            msg = f"saved: {out_path}"
        elif result.stderr:
            # resilience-stderr-surfaced-d — the original bug: stderr was
            # captured but never read, so a real, fixable reason (e.g.
            # "compositor doesn't support wlr-screencopy-unstable-v1")
            # showed as the same dead-end message every time.
            msg = f"recording failed: {result.stderr}"
        else:
            msg = "recording stopped but no playable file was written"
        self.app.call_from_thread(self._on_recording_stopped, msg)

    def _on_recording_stopped(self, msg: str) -> None:
        try:
            self.query_one("#screen-pane-record-toggle", Button).label = "● Start Recording"
        except Exception:  # noqa: BLE001
            pass
        self._toast(msg)
        self._finish("screen-studio-record")

    # ── screenshot ───────────────────────────────────────────────────────

    def _take_screenshot(self) -> None:
        if not self._try_start("screen-studio-screenshot"):
            return
        data_dir = self._data_dir()
        if data_dir is None:
            self._toast("data_dir not configured")
            self._finish("screen-studio-screenshot")
            return
        self._toast("capturing screenshot…")
        self._screenshot_worker(data_dir)

    @work(thread=True, exclusive=True, group="screen-studio-screenshot")
    def _screenshot_worker(self, data_dir: Path) -> None:
        _ok, msg = capture_screenshot_to_dir(data_dir)
        self.app.call_from_thread(self._toast, msg)
        self.app.call_from_thread(self._finish, "screen-studio-screenshot")

    # DEFAULT_CSS uses a TYPE selector (ScreenStudioPane { ... }), not an
    # id selector, matching the gotcha movie_pane.py's own comment
    # documents: a widget's own DEFAULT_CSS auto-scopes an id selector
    # matching the widget's OWN id to DESCENDANTS only, so `#screen-studio
    # -pane { ... }` inside this class would silently never apply.
    DEFAULT_CSS = """
    ScreenStudioPane {
        display: none;
        border-left: solid $primary;
        padding: 0 1;
        background: $surface;
    }
    #screen-pane-header { height: auto; text-style: bold; margin-bottom: 1; }
    #screen-pane-status {
        height: auto; min-height: 3; color: $text; text-style: bold;
        margin-bottom: 1; padding: 0 1; border: round $primary;
    }
    ScreenStudioPane Button { width: 100%; margin-bottom: 1; }
    ScreenStudioPane Button.flash { border: round $success; background: $success 20%; color: $success; }
    """
