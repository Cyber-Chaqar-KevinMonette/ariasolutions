"""tracks — the languages the school teaches, as data.

code-school-d (Kevin, 2026-08-04): "a bot that teaches me how to code.
Categories for different languages... I want to learn more about building AI
systems, to where I can be a reliable programmer."

Same KEEP-list shape as `verticals.py`, and for the same hard-won reason: a
catalog that ships everything by default reached 88 verticals of which six
had delivered anything in 72 hours. Defining a track here is a DRAFT.
Listing its slug in `ENABLED` is the decision to ship it.

Only PYTHON and AI SYSTEMS are enabled. GDSCRIPT/WEB/SQL are written down so
the shape is obvious when Kevin wants them, but a server we just cleaned
from fourteen categories to eight does not need twelve empty channels for a
single learner.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Track", "CATALOG", "ENABLED", "enabled_tracks", "track_by_slug",
           "CATEGORY_FOR", "channels_for"]


@dataclass(frozen=True)
class Track:
    slug: str
    name: str                 # Discord category name
    emoji: str
    blurb: str

    @property
    def ping_role(self) -> str:
        """panel-d (Kevin, 2026-08-04): "add the python and ai systems to my
        panel." /my-panel toggles a subscriber role per entry, so a track
        needs one in the same shape verticals use — Track-Python,
        Track-Aisys. It also makes the school sellable later without a
        rewrite: the gate already exists."""
        return f"Track-{self.slug.title().replace('-', '')}"

    @property
    def lessons_channel(self) -> str:
        return f"{self.slug}-lessons"

    @property
    def drills_channel(self) -> str:
        return f"{self.slug}-drills"

    @property
    def review_channel(self) -> str:
        return f"{self.slug}-review"

    @property
    def channels(self) -> tuple[str, str, str]:
        return (self.lessons_channel, self.drills_channel, self.review_channel)


CATALOG: list[Track] = [
    Track("python", "PYTHON", "🐍",
          "The language sovereign-agent is written in. Every lesson cites "
          "real code you own."),
    Track("aisys", "AI SYSTEMS", "🤖",
          "How an agent actually works: tools, gating, reconcilers, "
          "sentinels — walked through the system you already run."),
    # ── defined, not enabled ────────────────────────────────────────────
    Track("gdscript", "GDSCRIPT", "🎮",
          "Godot scripting — for the game work."),
    Track("web", "WEB", "🌐",
          "HTML/CSS/JS — the funnel site."),
    Track("sql", "SQL", "🗃",
          "Queries and schema design."),
]

# the decision to ship. Adding a slug here is all it takes.
ENABLED: frozenset[str] = frozenset({"python", "aisys"})

CATALOG_BY_SLUG = {t.slug: t for t in CATALOG}
CATEGORY_FOR = {t.slug: t.name for t in CATALOG}


def enabled_tracks() -> list[Track]:
    return [t for t in CATALOG if t.slug in ENABLED]


def track_by_slug(slug: str) -> Track | None:
    return CATALOG_BY_SLUG.get((slug or "").strip().lower())


def channels_for(slug: str) -> tuple[str, ...]:
    t = track_by_slug(slug)
    return t.channels if t else ()
