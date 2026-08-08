"""game_projects — define game projects (name, genre, concept) before build.

Kevin's ask (2026-07-20): let Aria build video games toward real revenue,
across up to 3 concurrent projects she can switch between, but stay
disciplined on whichever one she's on unless told to switch or it's
genuinely vital. Same shape as bot_projects.py's "define the direction
before building" doctrine — the mature first floor toward income, applied
to game dev instead of bots.

Engine is fixed to "godot" for now (Roblox Studio has no native Linux
build, so a real unattended session isn't feasible on this machine) but
kept as a field, not hardcoded logic, so a second engine can slot in later
without a schema change.

Storage: one JSON file per project under `<data>/game_projects/<slug>.json`,
plus a single focus pointer at `<data>/game_projects/_focus.json`.

Focus is observability + an audit trail, NOT a hard code lock — matches
this repo's doctrine (sentinels observe/advise; the diagnosis catalog
requires a reason, not a permission gate). `reason` is required on every
switch. The rule Aria should actually follow: don't switch focus without
either an explicit operator instruction or a genuinely vital reason, and
say which one it was in the reason text. Nothing in this module enforces
that behaviorally — it's a durable record she and Kevin can both see.
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
    "GameProject",
    "GENRES",
    "DIMENSIONS",
    "FocusState",
    "slugify",
    "validate",
    "save",
    "load",
    "list_all",
    "delete",
    "projects_dir",
    "game_workspace_dir",
    "get_focus",
    "set_focus",
    "STARTER_IDEAS",
]

# Curated, deliberately small-scope / shippable-by-one-(AI)-person genres —
# real itch.io precedent for "even a little" money, not aiming at a AAA
# scope no one here can finish. (key, human label). "other" lets the
# operator name a genre we haven't catalogued.
GENRES: list[tuple[str, str]] = [
    ("idle-incremental", "Idle / incremental"),
    ("puzzle", "Puzzle (one-screen or short levels)"),
    ("roguelike-arena", "Roguelike arena / short run"),
    ("arcade-score-attack", "Arcade / score-attack"),
    ("narrative-short", "Narrative short"),
    ("platformer", "Platformer"),
    ("other", "Other (name it below)"),
]
_GENRE_KEYS = {k for k, _ in GENRES}

# dimension-d (Kevin, 2026-08-02): "we can start with 2D or 2.5D and then
# work our way to 3D." Godot natively covers all three in one engine
# (Node2D vs Node3D scene roots) -- this field is what ScaffoldGodotProjectTool
# reads to pick the right starter scene. Default 2d: the easiest, fastest
# starting point matching Kevin's own stated order.
DIMENSIONS: list[tuple[str, str]] = [
    ("2d", "2D"),
    ("2.5d", "2.5D (2D gameplay, depth/perspective tricks)"),
    ("3d", "3D"),
]
_DIMENSION_KEYS = {k for k, _ in DIMENSIONS}

# Shown in the Game Studio's empty state — inspiration, not an auto-created
# project. Kevin or Aria still defines the real concept deliberately,
# matching bot_projects.py's own "define before build" discipline.
STARTER_IDEAS = (
    "idle prestige clicker — one core loop, a handful of upgrades, "
    "built to be replayed",
    "one-screen puzzle pack — 20-40 small hand-tuned levels, easy to "
    "finish and polish",
    "score-attack arcade loop — 60-90 second runs, one mechanic done well",
)

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,60}$")
_VALID_STATUS = {"defining", "active", "paused", "shipped"}


@dataclass
class GameProject:
    """One game project's definition (the concept, not the code)."""
    project_name: str
    genre: str = "idle-incremental"
    genre_other: str = ""        # freeform genre when genre == "other"
    concept: str = ""            # the pitch / direction
    monetization_note: str = ""  # how THIS one might make even a little money
    engine: str = "godot"        # a field, not hardcoded logic — Roblox etc. can slot in later
    dimension: str = "2d"        # 2d | 2.5d | 3d — which starter scene to scaffold
    status: str = "defining"     # defining | active | paused | shipped
    created_at: str = ""
    modified_at: str = ""

    @property
    def genre_label(self) -> str:
        if self.genre == "other" and self.genre_other:
            return self.genre_other
        return dict(GENRES).get(self.genre, self.genre)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "GameProject":
        data = json.loads(text)
        known = {f for f in GameProject("x").as_dict()}
        return cls(**{k: v for k, v in data.items() if k in known})


def slugify(name: str) -> str:
    s = "".join(c if (c.isalnum() or c in "-_") else "-" for c in (name or "").lower())
    s = re.sub(r"-{2,}", "-", s).strip("-.")
    return s[:48] or "project"


def validate(p: GameProject) -> list[str]:
    errs: list[str] = []
    if not (p.project_name or "").strip():
        errs.append("project name is required")
    elif not _NAME_RE.match(p.project_name.strip()):
        errs.append("project name has invalid characters (letters/numbers/space/-/_ only)")
    if p.genre not in _GENRE_KEYS:
        errs.append(f"genre {p.genre!r} not one of {sorted(_GENRE_KEYS)}")
    if p.genre == "other" and not (p.genre_other or "").strip():
        errs.append("genre is 'other' — please name the genre in genre_other")
    if p.dimension not in _DIMENSION_KEYS:
        errs.append(f"dimension {p.dimension!r} not one of {sorted(_DIMENSION_KEYS)}")
    if p.status not in _VALID_STATUS:
        errs.append(f"status {p.status!r} not one of {sorted(_VALID_STATUS)}")
    return errs


def projects_dir(data_dir: Path) -> Path:
    p = Path(data_dir) / "game_projects"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(data_dir: Path, project_name: str) -> Path:
    return projects_dir(data_dir) / f"{slugify(project_name)}.json"


def game_workspace_dir(slug: str, sandbox_dir: Path | None = None) -> Path:
    """Where a game project's actual Godot files live. Rooting every game
    under sandbox_dir/games/<slug> is what lets the EXISTING write_file /
    edit_file / copy_file tools (already sandboxed via pathguard) scaffold
    Godot files with zero new write-tool code."""
    if sandbox_dir is None:
        from sovereign_agent.config import SETTINGS
        sandbox_dir = SETTINGS.paths.sandbox_dir
    d = Path(sandbox_dir) / "games" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(p: GameProject, data_dir: Path) -> Path:
    errs = validate(p)
    if errs:
        raise ValueError("game project invalid:\n  - " + "\n  - ".join(errs))
    now = datetime.now(timezone.utc).isoformat()
    if not p.created_at:
        p.created_at = now
    p.modified_at = now
    path = _path(data_dir, p.project_name)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(p.to_json(), encoding="utf-8")
    with open(tmp, "r+", encoding="utf-8") as fh:
        fh.flush(); os.fsync(fh.fileno())
    tmp.replace(path)
    return path


def load(project_name: str, data_dir: Path) -> GameProject | None:
    path = _path(data_dir, project_name)
    if not path.is_file():
        return None
    try:
        return GameProject.from_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def load_by_slug(slug: str, data_dir: Path) -> GameProject | None:
    path = projects_dir(data_dir) / f"{slug}.json"
    if not path.is_file():
        return None
    try:
        return GameProject.from_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def list_all(data_dir: Path) -> list[GameProject]:
    out: list[GameProject] = []
    d = projects_dir(data_dir)
    for f in sorted(d.glob("*.json")):
        if f.name == "_focus.json":
            continue
        try:
            out.append(GameProject.from_json(f.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 — skip a corrupt file, never crash the list
            continue
    return out


def delete(project_name: str, data_dir: Path) -> bool:
    path = _path(data_dir, project_name)
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
    required and always recorded — this is an audit trail, not a lock.
    The behavioral rule Aria follows: don't call this without either an
    explicit operator instruction or a genuinely vital reason, and say
    which in `reason`. That rule lives in the tool description she reads,
    not in code here."""
    if not (reason or "").strip():
        raise ValueError("set_focus requires a non-empty reason")
    if not load_by_slug(slug, data_dir):
        raise ValueError(f"no game project with slug {slug!r} — define it first")

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
