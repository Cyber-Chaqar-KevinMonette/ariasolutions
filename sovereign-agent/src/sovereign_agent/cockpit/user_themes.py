"""
╔══════════════════════════════════════════════════════════════════════════╗
║  cockpit/user_themes.py — themes the operator and Aria build together   ║
║                                                                           ║
║  16 curated themes ship in cockpit/themes.py. This module is the         ║
║  *workshop* where new ones get built, cloned, tweaked, and saved.        ║
║                                                                           ║
║  Storage:                                                                 ║
║                                                                           ║
║    Each user theme lives as a JSON file at                              ║
║      <data_dir>/themes/<name>.json                                       ║
║                                                                           ║
║    One file per theme — clean diffs, easy backup, no shared mutable     ║
║    state. Themes can be hand-edited; the cockpit picks up changes on    ║
║    next launch.                                                          ║
║                                                                           ║
║  Capacity:                                                               ║
║                                                                           ║
║    Soft cap at 1000 user themes (theme-studio-d — raised from 50 at      ║
║    Kevin's ask: "no cap basically, as long as it breaks nothing and     ║
║    slows nothing"). It is only a WARNING threshold — save never refuses. ║
║    Themes are individual JSON files, so list/save scale freely; the only ║
║    real cost is boot-time registration, which stays fast into the        ║
║    hundreds. (Curated themes don't count toward the cap.)                ║
║                                                                           ║
║  Workflow philosophy:                                                    ║
║                                                                           ║
║    Default is ONE theme at a time. The operator picks a target          ║
║    (`sov theme apply aria-ember` makes ember the cockpit's startup      ║
║    theme), creates or clones, iterates, applies. Highest focus, deepest ║
║    quality.                                                              ║
║                                                                           ║
║    If the operator has a batch of ideas ready, nothing gates them from  ║
║    creating multiple — `sov theme create` is non-interactive when all   ║
║    flags are passed. But the friction of one-at-a-time is the default. ║
║                                                                           ║
║  Effects slot:                                                           ║
║                                                                           ║
║    Every user theme JSON carries an `effects` dict, reserved for        ║
║    future special-effect features (subtle animations, ANSI flourishes, ║
║    breathing-color states). For v1 the slot is preserved-but-unused —  ║
║    enabling forward compatibility without inventing a scheme we haven't ║
║    yet earned.                                                          ║
║                                                                           ║
║  What this module never does:                                           ║
║                                                                           ║
║    × Override or modify curated themes (those are version-locked code) ║
║    × Auto-apply a theme without explicit `sov theme apply`             ║
║    × Persist invalid color values (validation runs before save)        ║
║    × Silently overwrite existing themes (clone/save requires --force)  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .themes import CockpitTheme

if TYPE_CHECKING:
    from textual.app import App


SOFT_CAP = 1000  # theme-studio-d — a soft WARNING threshold only; save never refuses
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")

# The cockpit picks up the "active" theme from this single-line file. Lets
# `sov theme apply <name>` persist the choice without rewriting config.
ACTIVE_THEME_FILENAME = "active_theme.txt"


@dataclass
class UserTheme:
    """An operator-authored theme. Serializes to JSON 1:1.

    Same shape as CockpitTheme plus authorship metadata and an `effects`
    slot reserved for future co-design between operator and Aria.
    """
    name: str
    family: str
    mood: str
    dark: bool
    background: str
    surface: str
    panel: str
    primary: str
    accent: str
    secondary: str
    success: str
    warning: str
    error: str
    foreground: str | None = None
    boost: str | None = None
    luminosity_spread: float = 0.20
    text_alpha: float = 0.95

    # ── Authorship ──────────────────────────────────────────────────────
    created_by: str = "operator"         # operator | aria | co-design
    created_at: str = ""                  # ISO timestamp
    modified_at: str = ""
    cloned_from: str | None = None        # name of parent theme, if any
    notes: str = ""                       # operator's free-form notes

    # ── Future-compat effects slot ──────────────────────────────────────
    # Reserved for v0.2.35+. Operators may freely add keys here; the
    # cockpit ignores unknown ones until support lands. Forward-compat
    # by construction.
    effects: dict[str, Any] = field(default_factory=dict)

    def to_cockpit_theme(self) -> CockpitTheme:
        """Project to a CockpitTheme so it registers identically to curated ones."""
        return CockpitTheme(
            name=self.name, family=self.family, mood=self.mood, dark=self.dark,
            background=self.background, surface=self.surface, panel=self.panel,
            primary=self.primary, accent=self.accent, secondary=self.secondary,
            success=self.success, warning=self.warning, error=self.error,
            foreground=self.foreground, boost=self.boost,
            luminosity_spread=self.luminosity_spread, text_alpha=self.text_alpha,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "UserTheme":
        data = json.loads(text)
        # Drop unknown keys so future-format JSON loads on old code (Article I
        # — fail loud only on REAL incompatibility, not on forward-compat
        # additions)
        known = set(cls.__dataclass_fields__.keys())
        return cls(**{k: v for k, v in data.items() if k in known})


# ─── Validation ───────────────────────────────────────────────────────────


def validate(theme: UserTheme) -> list[str]:
    """Return a list of human-readable validation errors (empty if valid)."""
    errs: list[str] = []
    if not NAME_RE.match(theme.name):
        errs.append(
            f"name {theme.name!r} invalid; must match {NAME_RE.pattern} "
            "(lowercase, starts with letter, hyphens ok, 2-31 chars)"
        )
    if theme.family not in ("warm", "cool", "nature", "mono", "custom"):
        errs.append(f"family {theme.family!r} invalid; must be warm|cool|nature|mono|custom")
    for slot in ("background", "surface", "panel", "primary", "accent",
                 "secondary", "success", "warning", "error"):
        v = getattr(theme, slot)
        if not v or not HEX_RE.match(v):
            errs.append(f"slot {slot} = {v!r} is not a valid #RRGGBB hex color")
    for opt in ("foreground", "boost"):
        v = getattr(theme, opt)
        if v is not None and not HEX_RE.match(v):
            errs.append(f"slot {opt} = {v!r} not a valid hex (or use None to default)")
    if not (0.0 <= theme.luminosity_spread <= 1.0):
        errs.append(f"luminosity_spread {theme.luminosity_spread} out of [0,1]")
    if not (0.0 <= theme.text_alpha <= 1.0):
        errs.append(f"text_alpha {theme.text_alpha} out of [0,1]")
    return errs


# ─── Storage ──────────────────────────────────────────────────────────────


def themes_dir(data_dir: Path) -> Path:
    p = data_dir / "themes"
    p.mkdir(parents=True, exist_ok=True)
    return p


def theme_path(data_dir: Path, name: str) -> Path:
    return themes_dir(data_dir) / f"{name}.json"


def save(theme: UserTheme, data_dir: Path, *, force: bool = False) -> Path:
    """Persist a user theme. Refuses to overwrite without force=True."""
    errs = validate(theme)
    if errs:
        raise ValueError("theme invalid:\n  - " + "\n  - ".join(errs))
    p = theme_path(data_dir, theme.name)
    if p.is_file() and not force:
        raise FileExistsError(
            f"theme {theme.name!r} already exists at {p}. "
            "Pass force=True or use --force to overwrite."
        )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not theme.created_at:
        theme.created_at = now
    theme.modified_at = now
    p.write_text(theme.to_json(), encoding="utf-8")
    return p


def load(name: str, data_dir: Path) -> UserTheme | None:
    p = theme_path(data_dir, name)
    if not p.is_file():
        return None
    try:
        return UserTheme.from_json(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def delete(name: str, data_dir: Path) -> bool:
    p = theme_path(data_dir, name)
    if not p.is_file():
        return False
    p.unlink()
    return True


def list_all(data_dir: Path) -> list[UserTheme]:
    out: list[UserTheme] = []
    for p in sorted(themes_dir(data_dir).glob("*.json")):
        try:
            out.append(UserTheme.from_json(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue  # corrupted file; show it via doctor, don't crash list
    return out


def clone(src_theme: CockpitTheme | UserTheme, *, new_name: str,
          new_mood: str | None = None) -> UserTheme:
    """Build a new UserTheme from any source (curated or user)."""
    src_dict = asdict(src_theme) if hasattr(src_theme, "__dataclass_fields__") else {}
    # Only carry over the color/structural fields; reset authorship metadata
    base_fields = {
        k: v for k, v in src_dict.items()
        if k in UserTheme.__dataclass_fields__ and k not in (
            "created_by", "created_at", "modified_at", "cloned_from",
            "notes", "effects",
        )
    }
    base_fields["name"] = new_name
    if new_mood is not None:
        base_fields["mood"] = new_mood
    return UserTheme(
        **base_fields,
        cloned_from=getattr(src_theme, "name", None),
        created_by="operator",
        notes="",
        effects={},
    )


# ─── Active-theme persistence ────────────────────────────────────────────


def get_active_theme_name(data_dir: Path) -> str | None:
    p = data_dir / ACTIVE_THEME_FILENAME
    if not p.is_file():
        return None
    name = p.read_text(encoding="utf-8").strip()
    return name or None


def set_active_theme_name(name: str, data_dir: Path) -> Path:
    p = data_dir / ACTIVE_THEME_FILENAME
    p.write_text(name + "\n", encoding="utf-8")
    return p


# ─── Cockpit registration ────────────────────────────────────────────────


def register_user_themes(app: "App", data_dir: Path) -> list[str]:
    """Register every persisted user theme on the given Textual app.

    Failures (corrupt JSON, etc.) are silent: the cockpit ships without
    the broken theme rather than refusing to start. `sov theme list`
    surfaces the failures separately.
    """
    registered: list[str] = []
    for ut in list_all(data_dir):
        try:
            app.register_theme(ut.to_cockpit_theme().to_textual_theme())
            registered.append(ut.name)
        except Exception:
            continue
    return registered


__all__ = [
    "UserTheme",
    "SOFT_CAP",
    "ACTIVE_THEME_FILENAME",
    "themes_dir",
    "theme_path",
    "save", "load", "delete", "list_all", "clone", "validate",
    "get_active_theme_name", "set_active_theme_name",
    "register_user_themes",
]
