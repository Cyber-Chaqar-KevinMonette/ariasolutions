"""recorder.py — a screen recorder for the cockpit that needs no other software.

True video capture of a Wayland/COSMIC window is fragile and can't be verified
without a live display, so this takes the honest, robust path for a terminal
app: it snapshots the cockpit's *rendered* state to SVG frames on a timer, then
writes a manifest and a self-contained HTML player you can open in any browser
to watch the recording back — crisp, not a blurry screen-grab. No OBS, no
ffmpeg, no display server.

Layout under the recordings root (one tidy folder per take):

    recordings/
      catalog.json                         ← index of every take
      README.md                            ← what this folder is
      20260603-091500_rainbow-demo/
        frames/frame_00001.svg …
        manifest.json                      ← times, fps, size, version, theme
        index.html                         ← open this to play it back

The engine is deliberately decoupled from Textual: the app hands it SVG strings
(``capture_svg(app.export_screenshot())``), so it can be tested headlessly.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(label: str, *, fallback: str = "take") -> str:
    """A safe, tidy folder-name fragment from a free-text label."""
    s = _SLUG_RE.sub("-", (label or "").strip().lower()).strip("-")
    return (s or fallback)[:48]


@dataclass
class RecordingManifest:
    session_id: str
    label: str
    started_at: str
    ended_at: str | None
    fps: float
    frame_count: int
    width: int
    height: int
    app_version: str
    theme: str
    duration_seconds: float


class FrameRecorder:
    """Captures SVG frames into a cataloged session folder.

    Typical use from the app::

        rec = FrameRecorder(recordings_root, fps=2.0)
        rec.start("rainbow demo", width=w, height=h, app_version=v, theme=t)
        # on a timer, while rec.active:
        rec.capture_svg(app.export_screenshot())
        path = rec.stop()   # writes manifest.json + index.html + updates catalog
    """

    def __init__(self, root: Path | str, *, fps: float = 2.0) -> None:
        self.root = Path(root)
        self.fps = max(0.5, min(10.0, float(fps)))
        self.active = False
        self._session_id = ""
        self._label = ""
        self._session_dir: Path | None = None
        self._frames_dir: Path | None = None
        self._count = 0
        self._t0 = 0.0
        self._meta: dict = {}

    # ── state ──
    @property
    def elapsed(self) -> float:
        return (time.monotonic() - self._t0) if self.active else 0.0

    @property
    def frame_count(self) -> int:
        return self._count

    @property
    def session_dir(self) -> Path | None:
        return self._session_dir

    def status_text(self) -> str:
        """Compact indicator string, e.g. '● REC  00:07 · 14f'."""
        if not self.active:
            return ""
        secs = int(self.elapsed)
        return f"● REC  {secs // 60:02d}:{secs % 60:02d} · {self._count}f"

    # ── lifecycle ──
    def start(self, label: str = "take", *, width: int = 0, height: int = 0,
              app_version: str = "", theme: str = "") -> Path:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._session_id = f"{ts}_{slugify(label)}"
        self._session_dir = self.root / self._session_id
        self._frames_dir = self._session_dir / "frames"
        self._frames_dir.mkdir(parents=True, exist_ok=True)
        self._count = 0
        self._t0 = time.monotonic()
        self._label = label
        self._meta = {
            "width": int(width), "height": int(height),
            "app_version": app_version, "theme": theme,
            "started_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.active = True
        _ensure_root_readme(self.root)
        return self._session_dir

    def capture_svg(self, svg: str | None) -> bool:
        """Persist one frame. Returns True if a frame was written."""
        if not self.active or self._frames_dir is None or not svg:
            return False
        self._count += 1
        (self._frames_dir / f"frame_{self._count:05d}.svg").write_text(
            svg, encoding="utf-8")
        return True

    def stop(self) -> Path | None:
        """Finalize: write manifest.json + index.html, update catalog.json."""
        if not self.active or self._session_dir is None:
            return None
        self.active = False
        manifest = RecordingManifest(
            session_id=self._session_id,
            label=self._label,
            started_at=self._meta.get("started_at", ""),
            ended_at=datetime.now().isoformat(timespec="seconds"),
            fps=self.fps,
            frame_count=self._count,
            width=int(self._meta.get("width", 0)),
            height=int(self._meta.get("height", 0)),
            app_version=self._meta.get("app_version", ""),
            theme=self._meta.get("theme", ""),
            duration_seconds=round(self._count / self.fps, 2) if self.fps else 0.0,
        )
        (self._session_dir / "manifest.json").write_text(
            json.dumps(asdict(manifest), indent=2), encoding="utf-8")
        (self._session_dir / "index.html").write_text(
            _player_html(manifest), encoding="utf-8")
        _update_catalog(self.root, manifest)
        return self._session_dir


# ─── folder hygiene: catalog + readme ───────────────────────────────────────


def _update_catalog(root: Path, manifest: RecordingManifest) -> None:
    """Append/replace this take in recordings/catalog.json (newest first)."""
    catalog_path = root / "catalog.json"
    entries: list[dict] = []
    if catalog_path.exists():
        try:
            data = json.loads(catalog_path.read_text(encoding="utf-8"))
            entries = data.get("recordings", []) if isinstance(data, dict) else []
        except Exception:  # noqa: BLE001 — a corrupt catalog shouldn't lose the take
            entries = []
    entries = [e for e in entries if e.get("session_id") != manifest.session_id]
    entries.insert(0, {
        "session_id": manifest.session_id,
        "label": manifest.label,
        "started_at": manifest.started_at,
        "ended_at": manifest.ended_at,
        "frames": manifest.frame_count,
        "duration_seconds": manifest.duration_seconds,
        "fps": manifest.fps,
        "size": f"{manifest.width}x{manifest.height}",
        "app_version": manifest.app_version,
        "theme": manifest.theme,
        "path": manifest.session_id,
        "player": f"{manifest.session_id}/index.html",
    })
    catalog_path.write_text(json.dumps(
        {"updated_at": datetime.now().isoformat(timespec="seconds"),
         "count": len(entries), "recordings": entries}, indent=2),
        encoding="utf-8")


def _ensure_root_readme(root: Path) -> None:
    readme = root / "README.md"
    if readme.exists():
        return
    root.mkdir(parents=True, exist_ok=True)
    readme.write_text(
        "# Aria — cockpit recordings\n\n"
        "Each take is its own folder, `YYYYMMDD-HHMMSS_label/`, containing:\n\n"
        "- `frames/` — the captured SVG frames\n"
        "- `manifest.json` — times, fps, terminal size, version, theme\n"
        "- `index.html` — open in any browser to play the take back\n\n"
        "`catalog.json` indexes every take (newest first). These are crisp SVG "
        "captures of the cockpit's rendered state — no external software needed "
        "to make or watch them.\n",
        encoding="utf-8")


# ─── the self-contained player ──────────────────────────────────────────────


def _player_html(m: RecordingManifest) -> str:
    """A standalone HTML player: cycles frames/frame_NNNNN.svg at the recorded
    fps, with play/pause, a scrubber, and a frame counter. Opens from disk; no
    server required."""
    title = f"{m.label or 'take'} · {m.session_id}"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; background:#0b0b12; color:#e6e3f5;
         font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
  header {{ padding:14px 18px; border-bottom:1px solid #221c33; }}
  header b {{ color:#c9a7f5; }}
  .meta {{ color:#8a86a8; font-size:12px; margin-top:4px; }}
  #stage {{ display:flex; justify-content:center; padding:18px; }}
  #frame {{ max-width:100%; height:auto; border-radius:8px;
           box-shadow:0 8px 40px #0008; background:#000; }}
  .bar {{ display:flex; align-items:center; gap:12px; padding:12px 18px;
         border-top:1px solid #221c33; flex-wrap:wrap; }}
  button {{ background:#1e1138; color:#e6e3f5; border:1px solid #3a2a5a;
           border-radius:6px; padding:6px 14px; cursor:pointer; font:inherit; }}
  button:hover {{ border-color:#c9a7f5; }}
  input[type=range] {{ flex:1; min-width:160px; accent-color:#c9a7f5; }}
  #count {{ color:#8a86a8; min-width:120px; text-align:right; }}
</style></head>
<body>
<header><b>♥ Aria</b> — {m.label or 'take'}
  <div class="meta">{m.frame_count} frames · {m.fps} fps · ~{m.duration_seconds}s
    · {m.width}x{m.height} · theme {m.theme or '—'} · v{m.app_version or '—'}
    · {m.started_at}</div>
</header>
<div id="stage"><img id="frame" alt="frame"></div>
<div class="bar">
  <button id="play">⏸ pause</button>
  <input id="seek" type="range" min="1" max="{max(1, m.frame_count)}" value="1">
  <span id="count">frame 1 / {m.frame_count}</span>
</div>
<script>
  const N = {m.frame_count}, FPS = {m.fps};
  const img = document.getElementById('frame'),
        seek = document.getElementById('seek'),
        count = document.getElementById('count'),
        playBtn = document.getElementById('play');
  let i = 1, playing = N > 1, timer = null;
  const pad = n => String(n).padStart(5,'0');
  function show(n) {{
    i = ((n - 1 + N) % N) + 1;
    img.src = 'frames/frame_' + pad(i) + '.svg';
    seek.value = i; count.textContent = 'frame ' + i + ' / ' + N;
  }}
  function tick() {{ if (playing) show(i % N + 1); }}
  function run() {{ clearInterval(timer); if (playing && N > 1)
      timer = setInterval(tick, Math.max(80, 1000 / FPS)); }}
  playBtn.onclick = () => {{ playing = !playing;
      playBtn.textContent = playing ? '⏸ pause' : '▶ play'; run(); }};
  seek.oninput = () => {{ playing = false; playBtn.textContent='▶ play';
      run(); show(parseInt(seek.value)); }};
  show(1); run();
</script>
</body></html>
"""
