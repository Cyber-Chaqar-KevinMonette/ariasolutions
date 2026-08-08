"""movie_character_bible — a "strict character system," honestly scoped.

movie-studio-d Phase 3 (Kevin, 2026-07-28): "make sure each movie has a
strict character system." This is best-effort TEXT reinforcement (a
consistent descriptor injected into every shot's prompt where a character
appears) plus an optional reference still for a HUMAN to eyeball against —
it is deliberately NOT a hard identity lock. No image-conditioning-on-a-
person mechanism exists here; the only image conditioning in this system
is scene/composition continuity via the previous clip's last frame
(movie_video_continuity.py), never a character's face/body specifically.

Expect visible drift over a long chain. The real hard-identity-lock upgrade
is per-character LoRA training — explicitly out of scope for now, exactly
as Kevin himself flagged it ("etc...", "fill in any gaps"). A perceptual-
hash/embedding distance check against reference_image_path is a plausible
future addition; no embedding model is wired for that purpose today and
adding one is a real VRAM-cost decision on this 8GB card, not made here.

One bible per SERIES (characters persist across seasons/episodes, not
just one episode). Storage: <data_dir>/movie_series/<slug>_character_bible.json
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sovereign_agent.movie_series import series_dir

__all__ = [
    "CharacterEntry",
    "CharacterBible",
    "build_prompt_for_shot",
    "bible_path",
    "save_bible",
    "load_bible",
]


@dataclass
class CharacterEntry:
    name: str
    text_descriptor: str = ""       # injected into every prompt where this character appears
    reference_image_path: str = ""  # a still (storyboard/extracted frame) — for a HUMAN to eyeball
    avoid_descriptor: str = ""      # appended to negative_prompt when this character is on-screen

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CharacterBible:
    series_slug: str
    style_descriptor: str = ""   # world-wide visual descriptor (palette, lighting, render style)
    characters: list[CharacterEntry] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "series_slug": self.series_slug,
            "style_descriptor": self.style_descriptor,
            "characters": [c.as_dict() for c in self.characters],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "CharacterBible":
        data = json.loads(text)
        chars = [
            CharacterEntry(
                name=str(c.get("name", "")),
                text_descriptor=str(c.get("text_descriptor", "")),
                reference_image_path=str(c.get("reference_image_path", "")),
                avoid_descriptor=str(c.get("avoid_descriptor", "")),
            )
            for c in data.get("characters", []) if isinstance(c, dict)
        ]
        return cls(
            series_slug=str(data.get("series_slug", "")),
            style_descriptor=str(data.get("style_descriptor", "")),
            characters=chars,
        )

    def get(self, name: str) -> CharacterEntry | None:
        for c in self.characters:
            if c.name == name:
                return c
        return None


def build_prompt_for_shot(
    beat: str,
    characters_present: list[str],
    bible: CharacterBible,
    base_negative: str = "",
) -> tuple[str, str]:
    """Compose (prompt, negative_prompt) for one shot.

    Pure text concatenation — no image conditioning of a PERSON, only of the
    previous clip's whole frame (scene/composition continuity, handled in
    movie_video_continuity.py). Characters named in characters_present but
    missing from the bible are skipped silently (their name still appears
    in the beat text itself) rather than raising — a bible is best-effort
    reinforcement, not a hard requirement to render at all.
    """
    parts = [beat.strip()] if beat.strip() else []
    if bible.style_descriptor.strip():
        parts.append(bible.style_descriptor.strip())
    avoid_parts = [base_negative.strip()] if base_negative.strip() else []
    for name in characters_present:
        entry = bible.get(name)
        if entry is None:
            continue
        if entry.text_descriptor.strip():
            parts.append(entry.text_descriptor.strip())
        if entry.avoid_descriptor.strip():
            avoid_parts.append(entry.avoid_descriptor.strip())
    prompt = ", ".join(p for p in parts if p)
    negative_prompt = ", ".join(p for p in avoid_parts if p)
    return prompt, negative_prompt


def bible_path(series_slug: str, data_dir: Path) -> Path:
    return series_dir(data_dir) / f"{series_slug}_character_bible.json"


def save_bible(bible: CharacterBible, data_dir: Path) -> Path:
    path = bible_path(bible.series_slug, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(bible.to_json(), encoding="utf-8")
    with open(tmp, "r+", encoding="utf-8") as fh:
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)
    return path


def load_bible(series_slug: str, data_dir: Path) -> CharacterBible:
    """Never raises — a series with no bible yet gets an empty one back,
    same "dormant not broken" discipline as the rest of this repo."""
    path = bible_path(series_slug, data_dir)
    if not path.is_file():
        return CharacterBible(series_slug=series_slug)
    try:
        return CharacterBible.from_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return CharacterBible(series_slug=series_slug)
