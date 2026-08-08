"""movie_projects — define movie projects (title, genre, logline) before build.

movie-studio-d (Kevin, 2026-07-28): "Let's add a movie producer mode... get
her producing full scale movies." Same shape as game_projects.py's "define
the direction before building" doctrine — a real short-film production
project, scoped honestly to what a solo/local pipeline can actually finish
(see MOVIE_GENRES), not a AAA-studio fantasy.

`style` is the film analog to game_projects.py's `engine` field: a real
field (not hardcoded logic) recording whether this project is animated,
live-action, or mixed — informs which generation tools/prompt style fit it,
without baking a single style into the schema.

Storage: one JSON file per project under `<data>/movie_projects/<slug>.json`,
plus a single focus pointer at `<data>/movie_projects/_focus.json` — same
focus-is-an-audit-trail-not-a-lock doctrine as game_projects.py: `reason` is
required on every switch, nothing here enforces discipline behaviorally.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "MovieProject",
    "MOVIE_GENRES",
    "MOVIE_STYLES",
    "FocusState",
    "slugify",
    "validate",
    "save",
    "load",
    "load_by_slug",
    "list_all",
    "delete",
    "projects_dir",
    "movie_workspace_dir",
    "get_focus",
    "set_focus",
    "STARTER_IDEAS",
]

# Deliberately shippable scope — a solo/local pipeline can actually finish
# these, unlike "feature film." (key, human label). "other" lets the
# operator name a genre we haven't catalogued.
MOVIE_GENRES: list[tuple[str, str]] = [
    ("short-film", "Short film"),
    ("animated-short", "Animated short"),
    ("documentary-style", "Documentary-style"),
    ("music-video", "Music video"),
    ("trailer-proof-of-concept", "Trailer / proof-of-concept"),
    ("other", "Other (name it below)"),
]
_GENRE_KEYS = {k for k, _ in MOVIE_GENRES}

MOVIE_STYLES: list[tuple[str, str]] = [
    ("animated", "Animated"),
    ("live-action", "Live-action"),
    ("mixed", "Mixed"),
    ("other", "Other"),
]
_STYLE_KEYS = {k for k, _ in MOVIE_STYLES}

# Shown in Movie Studio's empty state — inspiration, not an auto-created
# project. Kevin or Aria still defines the real concept deliberately, same
# "define before build" discipline as game_projects.py.
STARTER_IDEAS = (
    "a 2-3 minute animated short built around one clean visual idea",
    "a documentary-style piece about a real, small, true story",
    "a music video for an existing track — visuals built to the beat",
)

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,80}$")
_VALID_STATUS = {"defining", "active", "paused", "shipped"}


@dataclass
class MovieProject:
    """One movie project's definition (the concept, not the footage)."""
    title: str
    genre: str = "short-film"
    genre_other: str = ""        # freeform genre when genre == "other"
    logline: str = ""            # the one-line pitch
    style: str = "animated"      # animated | live-action | mixed | other
    monetization_note: str = ""  # how THIS one might make even a little money
    status: str = "defining"     # defining | active | paused | shipped
    created_at: str = ""
    modified_at: str = ""

    @property
    def genre_label(self) -> str:
        if self.genre == "other" and self.genre_other:
            return self.genre_other
        return dict(MOVIE_GENRES).get(self.genre, self.genre)

    @property
    def style_label(self) -> str:
        return dict(MOVIE_STYLES).get(self.style, self.style)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "MovieProject":
        data = json.loads(text)
        known = {f for f in MovieProject("x").as_dict()}
        return cls(**{k: v for k, v in data.items() if k in known})


def slugify(title: str) -> str:
    s = "".join(c if (c.isalnum() or c in "-_") else "-" for c in (title or "").lower())
    s = re.sub(r"-{2,}", "-", s).strip("-.")
    return s[:48] or "movie"


def validate(p: MovieProject) -> list[str]:
    errs: list[str] = []
    if not (p.title or "").strip():
        errs.append("title is required")
    elif not _NAME_RE.match(p.title.strip()):
        errs.append("title has invalid characters (letters/numbers/space/-/_ only)")
    if p.genre not in _GENRE_KEYS:
        errs.append(f"genre {p.genre!r} not one of {sorted(_GENRE_KEYS)}")
    if p.genre == "other" and not (p.genre_other or "").strip():
        errs.append("genre is 'other' — please name the genre in genre_other")
    if p.style not in _STYLE_KEYS:
        errs.append(f"style {p.style!r} not one of {sorted(_STYLE_KEYS)}")
    if p.status not in _VALID_STATUS:
        errs.append(f"status {p.status!r} not one of {sorted(_VALID_STATUS)}")
    return errs


def projects_dir(data_dir: Path) -> Path:
    p = Path(data_dir) / "movie_projects"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(data_dir: Path, title: str) -> Path:
    return projects_dir(data_dir) / f"{slugify(title)}.json"


def movie_workspace_dir(slug: str, sandbox_dir: Path | None = None) -> Path:
    """Where a movie project's real files (treatment, storyboards, clips)
    live. Rooting every movie under sandbox_dir/movies/<slug> lets the
    EXISTING write_file/edit_file tools (already sandboxed via pathguard)
    write script/treatment docs with zero new write-tool code."""
    if sandbox_dir is None:
        from sovereign_agent.config import SETTINGS
        sandbox_dir = SETTINGS.paths.sandbox_dir
    d = Path(sandbox_dir) / "movies" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(p: MovieProject, data_dir: Path) -> Path:
    errs = validate(p)
    if errs:
        raise ValueError("movie project invalid:\n  - " + "\n  - ".join(errs))
    now = datetime.now(timezone.utc).isoformat()
    if not p.created_at:
        p.created_at = now
    p.modified_at = now
    path = _path(data_dir, p.title)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(p.to_json(), encoding="utf-8")
    with open(tmp, "r+", encoding="utf-8") as fh:
        fh.flush(); os.fsync(fh.fileno())
    tmp.replace(path)
    return path


def load(title: str, data_dir: Path) -> MovieProject | None:
    path = _path(data_dir, title)
    if not path.is_file():
        return None
    try:
        return MovieProject.from_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def load_by_slug(slug: str, data_dir: Path) -> MovieProject | None:
    path = projects_dir(data_dir) / f"{slug}.json"
    if not path.is_file():
        return None
    try:
        return MovieProject.from_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def list_all(data_dir: Path) -> list[MovieProject]:
    out: list[MovieProject] = []
    d = projects_dir(data_dir)
    for f in sorted(d.glob("*.json")):
        if f.name == "_focus.json":
            continue
        try:
            out.append(MovieProject.from_json(f.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 — skip a corrupt file, never crash the list
            continue
    return out


def delete(title: str, data_dir: Path) -> bool:
    path = _path(data_dir, title)
    if not path.is_file():
        return False
    path.unlink()
    return True


# ── Focus: which project she's currently disciplined to ──────────────────


@dataclass
class FocusState:
    slug: str | None = None
    since: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, text: str) -> "FocusState":
        data = json.loads(text)
        return cls(
            slug=data.get("slug"),
            since=data.get("since", ""),
            history=data.get("history", []),
        )


def _focus_path(data_dir: Path) -> Path:
    return projects_dir(data_dir) / "_focus.json"


def get_focus(data_dir: Path) -> FocusState:
    path = _focus_path(data_dir)
    if not path.is_file():
        return FocusState()
    try:
        return FocusState.from_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return FocusState()


def set_focus(slug: str, reason: str, data_dir: Path, vital: bool = False) -> FocusState:
    """Switch (or set) which project is currently focused. `reason` is
    required and always recorded — an audit trail, not a lock. Same
    doctrine as game_projects.set_focus."""
    if not (reason or "").strip():
        raise ValueError("set_focus requires a non-empty reason")
    if not load_by_slug(slug, data_dir):
        raise ValueError(f"no movie project with slug {slug!r} — define it first")

    prev = get_focus(data_dir)
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "ts": now,
        "from": prev.slug,
        "to": slug,
        "reason": reason.strip(),
        "vital": bool(vital),
    }
    new_state = FocusState(
        slug=slug,
        since=now,
        history=[*prev.history, entry][-50:],  # bounded, never unbounded growth
    )
    path = _focus_path(data_dir)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(new_state.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    with open(tmp, "r+", encoding="utf-8") as fh:
        fh.flush(); os.fsync(fh.fileno())
    tmp.replace(path)
    return new_state
