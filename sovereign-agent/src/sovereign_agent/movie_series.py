"""movie_series — Series and Season records, sitting above movie_projects.py.

movie-studio-d Phase 3 (Kevin, 2026-07-28): "I also need a way to track...
seasons of a series like each series could be stored as a project. Each
series can have seasons. Each season can have as many episodes as we want."

A Series IS the "project" Kevin means here — same slugify/validate/atomic-
write idiom as movie_projects.MovieProject, one JSON file per series. A
Season is a lightweight child record (season_ids on Series, episode_ids on
Season) — episodes themselves are EpisodeRenderSession records living in
movie_episode_render.py's own store, not duplicated here. No cap on episodes
per season in the data model itself, per Kevin's explicit "as many episodes
as we want" — any real limit belongs on an individual episode's own render
caps, not here.

Storage:
  <data_dir>/movie_series/<slug>.json                    — the Series
  <data_dir>/movie_series/<slug>/season-<NN>.json         — each Season
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sovereign_agent.movie_projects import MOVIE_GENRES, MOVIE_STYLES

__all__ = [
    "Series",
    "Season",
    "EpisodeFocusState",
    "slugify",
    "validate_series",
    "validate_season",
    "series_dir",
    "save_series",
    "load_series",
    "load_series_by_slug",
    "list_all_series",
    "delete_series",
    "season_id_for",
    "parse_season_id",
    "create_season",
    "load_season",
    "list_seasons",
    "add_episode_to_season",
    "get_episode_focus",
    "set_episode_focus",
    "set_safety_level",
]

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,80}$")
_VALID_SERIES_STATUS = {"defining", "active", "paused", "complete"}
_VALID_SEASON_STATUS = {"planning", "active", "paused", "complete"}
_GENRE_KEYS = {k for k, _ in MOVIE_GENRES}
_STYLE_KEYS = {k for k, _ in MOVIE_STYLES}
_SEASON_ID_RE = re.compile(r"^(?P<slug>.+)-s(?P<num>\d+)$")


@dataclass
class Series:
    """The umbrella project Kevin means by "a series" — one series, many
    seasons, unbounded episodes per season."""
    title: str
    slug: str = ""
    logline: str = ""
    genre: str = "short-film"
    style: str = "animated"
    season_ids: list[str] = field(default_factory=list)
    status: str = "defining"   # defining | active | paused | complete
    # movie-focus-d (Kevin, 2026-07-29): "add movie production guardrails
    # also so movies are social media platform friendly... add safety
    # levels. Which can be applied per series." strict = social-media-safe
    # (the honest default), moderate = mild fictional action/peril
    # allowed, open = Kevin's own private/unpublished use — never a way
    # to bypass the hard, non-negotiable floor (see
    # movie_content_safety.py's ALWAYS_BLOCKED set, which applies at
    # every level with no exception).
    safety_level: str = "strict"
    created_at: str = ""
    modified_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "Series":
        data = json.loads(text)
        known = {f for f in Series("x").as_dict()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class Season:
    """One season of a Series. episode_ids point at EpisodeRenderSession
    records in movie_episode_render.py's own store — not duplicated here."""
    season_id: str
    series_slug: str
    season_number: int
    title: str = ""
    episode_ids: list[str] = field(default_factory=list)
    status: str = "planning"   # planning | active | paused | complete
    created_at: str = ""
    modified_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "Season":
        data = json.loads(text)
        known = {f for f in Season("x", "y", 1).as_dict()}
        return cls(**{k: v for k, v in data.items() if k in known})


def slugify(title: str) -> str:
    s = "".join(c if (c.isalnum() or c in "-_") else "-" for c in (title or "").lower())
    s = re.sub(r"-{2,}", "-", s).strip("-.")
    return s[:48] or "series"


def validate_series(s: Series) -> list[str]:
    errs: list[str] = []
    if not (s.title or "").strip():
        errs.append("title is required")
    elif not _NAME_RE.match(s.title.strip()):
        errs.append("title has invalid characters (letters/numbers/space/-/_ only)")
    if s.genre not in _GENRE_KEYS:
        errs.append(f"genre {s.genre!r} not one of {sorted(_GENRE_KEYS)}")
    if s.style not in _STYLE_KEYS:
        errs.append(f"style {s.style!r} not one of {sorted(_STYLE_KEYS)}")
    if s.status not in _VALID_SERIES_STATUS:
        errs.append(f"status {s.status!r} not one of {sorted(_VALID_SERIES_STATUS)}")
    from .movie_content_safety import SAFETY_LEVELS
    if s.safety_level not in SAFETY_LEVELS:
        errs.append(f"safety_level {s.safety_level!r} not one of {sorted(SAFETY_LEVELS)}")
    return errs


def validate_season(se: Season) -> list[str]:
    errs: list[str] = []
    if not (se.series_slug or "").strip():
        errs.append("series_slug is required")
    if se.season_number < 1:
        errs.append("season_number must be >= 1")
    if se.status not in _VALID_SEASON_STATUS:
        errs.append(f"status {se.status!r} not one of {sorted(_VALID_SEASON_STATUS)}")
    return errs


def _atomic_write_json(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    with open(tmp, "r+", encoding="utf-8") as fh:
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)


# ── Series ──────────────────────────────────────────────────────────────


def series_dir(data_dir: Path) -> Path:
    p = Path(data_dir) / "movie_series"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _series_path(data_dir: Path, title: str) -> Path:
    return series_dir(data_dir) / f"{slugify(title)}.json"


def save_series(s: Series, data_dir: Path) -> Path:
    if not s.slug:
        s.slug = slugify(s.title)
    errs = validate_series(s)
    if errs:
        raise ValueError("series invalid:\n  - " + "\n  - ".join(errs))
    now = datetime.now(timezone.utc).isoformat()
    if not s.created_at:
        s.created_at = now
    s.modified_at = now
    path = _series_path(data_dir, s.title)
    _atomic_write_json(path, s.to_json())
    return path


def set_safety_level(series_slug: str, level: str, data_dir: Path) -> Series:
    """Kevin, 2026-07-29: 'add safety levels. Which can be applied per
    series.' Loads, validates (via save_series -> validate_series), and
    persists — an unknown series or an invalid level both raise honestly
    rather than silently doing nothing."""
    series = load_series_by_slug(series_slug, data_dir)
    if series is None:
        raise ValueError(f"no series with slug {series_slug!r}")
    series.safety_level = level
    save_series(series, data_dir)
    return series


def load_series(title: str, data_dir: Path) -> Series | None:
    path = _series_path(data_dir, title)
    if not path.is_file():
        return None
    try:
        return Series.from_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def load_series_by_slug(slug: str, data_dir: Path) -> Series | None:
    path = series_dir(data_dir) / f"{slug}.json"
    if not path.is_file():
        return None
    try:
        return Series.from_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def list_all_series(data_dir: Path) -> list[Series]:
    out: list[Series] = []
    d = series_dir(data_dir)
    for f in sorted(d.glob("*.json")):
        try:
            out.append(Series.from_json(f.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 — skip a corrupt file, never crash the list
            continue
    return out


def delete_series(title: str, data_dir: Path) -> bool:
    path = _series_path(data_dir, title)
    if not path.is_file():
        return False
    path.unlink()
    return True


# ── Seasons ──────────────────────────────────────────────────────────────


def season_id_for(series_slug: str, season_number: int) -> str:
    return f"{series_slug}-s{season_number:02d}"


def parse_season_id(season_id: str) -> tuple[str, int] | None:
    m = _SEASON_ID_RE.match(season_id)
    if not m:
        return None
    return m.group("slug"), int(m.group("num"))


def _seasons_dir(data_dir: Path, series_slug: str) -> Path:
    p = series_dir(data_dir) / series_slug
    p.mkdir(parents=True, exist_ok=True)
    return p


def _season_path(data_dir: Path, season_id: str) -> Path:
    parsed = parse_season_id(season_id)
    if parsed is None:
        raise ValueError(f"malformed season_id: {season_id!r}")
    series_slug, num = parsed
    return _seasons_dir(data_dir, series_slug) / f"season-{num:02d}.json"


def create_season(series_slug: str, title: str, data_dir: Path) -> Season:
    """Add the next season to an existing series. Requires the series to
    already exist — same "define before build" discipline as everywhere
    else in this file."""
    series = load_series_by_slug(series_slug, data_dir)
    if series is None:
        raise ValueError(f"no series with slug {series_slug!r} — define it first")
    season_number = len(series.season_ids) + 1
    season_id = season_id_for(series_slug, season_number)
    now = datetime.now(timezone.utc).isoformat()
    season = Season(
        season_id=season_id,
        series_slug=series_slug,
        season_number=season_number,
        title=title,
        created_at=now,
        modified_at=now,
    )
    errs = validate_season(season)
    if errs:
        raise ValueError("season invalid:\n  - " + "\n  - ".join(errs))
    _atomic_write_json(_season_path(data_dir, season_id), season.to_json())

    series.season_ids = [*series.season_ids, season_id]
    save_series(series, data_dir)
    return season


def load_season(season_id: str, data_dir: Path) -> Season | None:
    try:
        path = _season_path(data_dir, season_id)
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        return Season.from_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def list_seasons(series_slug: str, data_dir: Path) -> list[Season]:
    out: list[Season] = []
    d = _seasons_dir(data_dir, series_slug)
    for f in sorted(d.glob("season-*.json")):
        try:
            out.append(Season.from_json(f.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    return out


def add_episode_to_season(season_id: str, episode_id: str, data_dir: Path) -> Season:
    season = load_season(season_id, data_dir)
    if season is None:
        raise ValueError(f"no season with id {season_id!r} — create it first")
    if episode_id not in season.episode_ids:
        season.episode_ids = [*season.episode_ids, episode_id]
        season.modified_at = datetime.now(timezone.utc).isoformat()
        _atomic_write_json(_season_path(data_dir, season_id), season.to_json())
    return season


# ── Episode focus: which episode the movie pane is currently showing ──────
#
# movie-focus-d (Kevin, 2026-07-28): "one panel contains everything we
# need" — the pane needs to always know which episode it's controlling
# without a picker widget. Line-for-line the same shape as
# movie_projects.FocusState/get_focus/set_focus: reason required, bounded
# history, an audit trail rather than a lock. Deliberately does NOT
# validate that episode_id exists in EpisodeStore — that store lives in
# movie_episode_render.py, a sibling module built on top of this one;
# importing it here would invert the layering. Same "nothing here
# enforces discipline behaviorally" doctrine movie_projects.py already
# states explicitly.


@dataclass
class EpisodeFocusState:
    episode_id: str | None = None
    since: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, text: str) -> "EpisodeFocusState":
        data = json.loads(text)
        return cls(
            episode_id=data.get("episode_id"),
            since=data.get("since", ""),
            history=data.get("history", []),
        )


def _episode_focus_path(data_dir: Path) -> Path:
    return series_dir(data_dir) / "_episode_focus.json"


def get_episode_focus(data_dir: Path) -> EpisodeFocusState:
    path = _episode_focus_path(data_dir)
    if not path.is_file():
        return EpisodeFocusState()
    try:
        return EpisodeFocusState.from_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return EpisodeFocusState()


def set_episode_focus(episode_id: str, reason: str, data_dir: Path) -> EpisodeFocusState:
    """Switch (or set) which episode the movie pane is currently showing.
    `reason` is required and always recorded — an audit trail, not a
    lock, same doctrine as movie_projects.set_focus."""
    if not (reason or "").strip():
        raise ValueError("set_episode_focus requires a non-empty reason")

    prev = get_episode_focus(data_dir)
    now = datetime.now(timezone.utc).isoformat()
    entry = {"ts": now, "from": prev.episode_id, "to": episode_id, "reason": reason.strip()}
    new_state = EpisodeFocusState(
        episode_id=episode_id,
        since=now,
        history=[*prev.history, entry][-50:],   # bounded, never unbounded growth
    )
    _atomic_write_json(_episode_focus_path(data_dir), json.dumps(new_state.as_dict(), indent=2, ensure_ascii=False))
    return new_state
