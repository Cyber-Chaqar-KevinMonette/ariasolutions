"""Tests for the cockpit screen recorder (engine level — no Textual needed)."""
from __future__ import annotations

import json

import pytest

from sovereign_agent.cockpit.recorder import FrameRecorder, slugify


def test_slugify_is_filesystem_safe():
    assert slugify("Rainbow Demo!! v2") == "rainbow-demo-v2"
    assert slugify("   ") == "take"          # fallback
    assert "/" not in slugify("a/b\\c")
    assert len(slugify("x" * 200)) <= 48


def test_capture_before_start_is_a_noop(tmp_path):
    rec = FrameRecorder(tmp_path / "recordings")
    assert rec.capture_svg("<svg/>") is False
    assert rec.frame_count == 0
    assert rec.status_text() == ""


def test_full_take_writes_frames_manifest_player_catalog(tmp_path):
    root = tmp_path / "recordings"
    rec = FrameRecorder(root, fps=4.0)
    sess = rec.start("Rainbow Demo", width=120, height=36,
                     app_version="0.2.49.0", theme="aria-rainbow")
    assert sess.exists() and rec.active
    assert rec.status_text().startswith("● REC")
    for k in range(5):
        assert rec.capture_svg(f"<svg><text>{k}</text></svg>") is True
    assert rec.frame_count == 5
    out = rec.stop()
    assert out is not None and not rec.active

    frames = sorted((out / "frames").glob("frame_*.svg"))
    assert len(frames) == 5
    assert frames[0].name == "frame_00001.svg"

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["frame_count"] == 5
    assert manifest["theme"] == "aria-rainbow"
    assert manifest["app_version"] == "0.2.49.0"
    assert manifest["width"] == 120 and manifest["height"] == 36
    assert manifest["duration_seconds"] == pytest.approx(5 / 4.0, abs=0.01)

    player = (out / "index.html").read_text()
    assert "frames/frame_" in player and "Aria" in player

    catalog = json.loads((root / "catalog.json").read_text())
    assert catalog["count"] == 1
    assert catalog["recordings"][0]["label"] == "Rainbow Demo"
    assert catalog["recordings"][0]["frames"] == 5
    assert (root / "README.md").exists()


def test_session_folders_are_isolated_and_catalog_is_newest_first(tmp_path):
    root = tmp_path / "recordings"
    rec = FrameRecorder(root, fps=2.0)
    rec.start("first"); rec.capture_svg("<svg/>"); first = rec.stop()
    rec.start("second"); rec.capture_svg("<svg/>"); rec.capture_svg("<svg/>"); second = rec.stop()
    assert first != second
    catalog = json.loads((root / "catalog.json").read_text())
    assert catalog["count"] == 2
    # newest take is first in the catalog
    assert catalog["recordings"][0]["label"] == "second"
    assert catalog["recordings"][0]["frames"] == 2


def test_fps_is_clamped_to_sane_range(tmp_path):
    assert FrameRecorder(tmp_path, fps=0.01).fps >= 0.5
    assert FrameRecorder(tmp_path, fps=999).fps <= 10.0


def test_corrupt_catalog_does_not_lose_the_take(tmp_path):
    root = tmp_path / "recordings"
    root.mkdir(parents=True)
    (root / "catalog.json").write_text("{ not valid json ", encoding="utf-8")
    rec = FrameRecorder(root)
    rec.start("resilient"); rec.capture_svg("<svg/>"); rec.stop()
    catalog = json.loads((root / "catalog.json").read_text())
    assert catalog["count"] == 1
    assert catalog["recordings"][0]["label"] == "resilient"
