# aria-movie-series — Series → Season → Episode → Shot → Clip chaining foundation (Phase A)

> Movie Studio Phase 3: the data model + mechanisms for a series with unbounded seasons/episodes,
> a resumable/pauseable episode render session (dream.py-style), a character bible (best-effort
> text consistency, not a hard identity lock), a structural clip quality gate, real last-frame
> extraction via ffmpeg, and (Phase B) the real chained-generation runner wiring LTXConditionPipeline
> frame continuity + retry/quarantine/auto-pause into one clip-at-a-time driver. Propose-only /
> reversible / staged.
>
> Phase B's `_sync_generate_ltx_continuation` has been exercised only via monkeypatched tests so
> far — a real, monitored, human-supervised test run is required before trusting it unattended
> (same crash-safety discipline as the rest of tonight's GPU work on this card).

## Payload (flat modules under `src/sovereign_agent/`, not a subpackage)
- `movie_series.py` — `Series` + `Season` dataclasses, mirrors `movie_projects.py`'s save/load idiom.
- `movie_character_bible.py` — `CharacterBible`/`CharacterEntry` + `build_prompt_for_shot()`.
- `movie_episode_render.py` — `EpisodeRenderSession`/`EpisodeCaps`/`ShotEntry`/`ClipEntry`/`EpisodeStore`,
  a direct structural mirror of `dream.py`'s pauseable/resumable/fcntl-locked session store.
- `movie_clip_quality_gate.py` — `assess_frame()`, a real PIL stddev/color heuristic catching a
  blank/washed-out/degenerate frame before it becomes the next shot's continuity cursor.
- `movie_video_continuity.py` — `extract_last_frame()`, real ffmpeg subprocess call in
  `senses/eyes.py`'s exact house style.
- `movie_clip_generation.py` — dispatches between the live, proven `_sync_generate_ltx` (first clip)
  and the new `_sync_generate_ltx_continuation` (every clip after, frame-conditioned via
  `LTXConditionPipeline`/`LTXVideoCondition`).
- `movie_episode_render_runner.py` — `advance_episode()`, mirrors `dream_runner.advance_dream`: one
  clip attempt per call, persists after every clip, retry/quarantine/auto-pause on repeated failure,
  first real caller of `WorkflowSentinel` anywhere in this repo.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-movie-series     # before apply
./aria-movie-series/apply_movie_series.sh                 # cockpit stopped
```
