"""assemble_movie_episode — Tier 1. Merge a rendered episode's clips into
one playable file.

movie-focus-d (Kevin, 2026-07-28): "Then after it makes the last clip it
can merge them together to make the complete movie." Real ffmpeg concat-
demuxer call, in `senses/eyes.py`'s exact subprocess house style
(explicit timeout, `capture_output=True`, returncode check, stderr
truncated, never-raising-past-the-tool-boundary discipline). This is
genuinely new territory — no `-f concat` usage existed anywhere in this
repo before it.

Gathers ordered `pass`-quality clips from every shot in shot-then-clip
order (quarantined/failed clips are skipped automatically since they're
never marked "pass"). Tries a fast stream copy first (`-c copy` — safe
because every clip in a chain shares the same codec/resolution/fps by
construction); falls back to a `libx264` re-encode if that fails for any
reason, and reports honestly which path succeeded.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from sovereign_agent.movie_assets import record_asset
from sovereign_agent.movie_episode_render import EpisodeRenderSession, EpisodeStore
from sovereign_agent.tools.base import Tool, ToolResult

__all__ = ["AssembleMovieEpisodeTool"]


def _ordered_pass_clip_paths(episode: EpisodeRenderSession) -> list[Path]:
    paths: list[Path] = []
    for shot in episode.shots:
        for clip in shot.clips:
            if clip.quality_status == "pass" and clip.path:
                paths.append(Path(clip.path))
    return paths


def _write_concat_listfile(paths: list[Path], listfile_path: Path) -> None:
    lines = []
    for p in paths:
        escaped = str(p.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    listfile_path.write_text("\n".join(lines), encoding="utf-8")


def _concat_clips(paths: list[Path], out_path: Path, *, timeout: int = 120) -> tuple[bool, str]:
    """Real ffmpeg concat. Returns (ok, detail) — never raises."""
    if not paths:
        return False, "no pass-quality clips to assemble"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    listfile = out_path.with_suffix(".concat.txt")
    _write_concat_listfile(paths, listfile)

    def _run(cmd: list[str]) -> tuple[bool, str]:
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout)
            if result.returncode != 0 or not out_path.exists():
                stderr = result.stderr.decode("utf-8", errors="replace")[:200]
                return False, stderr
            return True, ""
        except subprocess.TimeoutExpired:
            return False, f"timed out after {timeout}s"
        except Exception as exc:  # noqa: BLE001
            return False, repr(exc)

    ok, detail = _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
                        "-c", "copy", str(out_path)])
    if ok:
        return True, "assembled via stream copy"

    ok, detail2 = _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
                         "-c:v", "libx264", str(out_path)])
    if ok:
        return True, "assembled via re-encode (stream copy failed)"
    return False, f"stream copy failed ({detail}); re-encode also failed ({detail2})"


class _Args(BaseModel):
    episode_id: str = Field(description="The episode render session id to assemble")
    allow_partial: bool = Field(
        default=False,
        description="Assemble even if the episode isn't marked completed — a legitimate "
                    "power-user action for a partial cut.",
    )


class AssembleMovieEpisodeTool(Tool[_Args]):
    name = "assemble_movie_episode"
    tier = 1
    description = (
        "Merge a movie episode's chained, quality-gate-passed clips into one playable "
        "video file via real ffmpeg concat (local, FOSS, no cost). Refuses a non-completed "
        "episode unless allow_partial=True. "
        "FAILURE MODES: unknown_episode; episode_not_completed; no_clips_to_assemble; assembly_failed."
    )
    failure_modes = ("unknown_episode", "episode_not_completed", "no_clips_to_assemble", "assembly_failed")
    Args = _Args

    def __init__(self, data_dir: Optional[Path] = None, work_root: Optional[Path] = None) -> None:
        self._data_dir = data_dir
        self._work_root = work_root

    def _store(self) -> EpisodeStore:
        data_dir = self._data_dir
        work_root = self._work_root
        if data_dir is None or work_root is None:
            from sovereign_agent.config import SETTINGS
            if data_dir is None:
                data_dir = SETTINGS.paths.data_dir
            if work_root is None:
                work_root = SETTINGS.paths.sandbox_dir / "movies"
        return EpisodeStore(Path(data_dir) / "movie_episodes", Path(work_root))

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        store = self._store()
        try:
            episode = store.get(args.episode_id)
        except Exception:  # noqa: BLE001
            return ToolResult(ok=False, error=f"unknown_episode: {args.episode_id!r}")

        if episode.status != "completed" and not args.allow_partial:
            return ToolResult(
                ok=False,
                error=(f"episode_not_completed: status is {episode.status!r} "
                       "(pass allow_partial=True to assemble anyway)"),
            )

        paths = _ordered_pass_clip_paths(episode)
        if not paths:
            return ToolResult(ok=False, error="no_clips_to_assemble: no pass-quality clips recorded")

        out_path = Path(episode.work_dir) / f"{episode.episode_id}_assembled.mp4"
        ok, detail = _concat_clips(paths, out_path)
        if not ok:
            return ToolResult(ok=False, error=f"assembly_failed: {detail}")

        try:
            record_asset(Path(episode.work_dir), relative_path=out_path.name,
                        kind="episode_cut", source_tool="assemble_movie_episode")
        except Exception:  # noqa: BLE001 — manifest entry is best-effort; assembly already succeeded
            pass

        return ToolResult(ok=True, output={
            "path": str(out_path),
            "clip_count": len(paths),
            "message": f"Assembled {len(paths)} clips ({detail}) -> {out_path}",
        })
