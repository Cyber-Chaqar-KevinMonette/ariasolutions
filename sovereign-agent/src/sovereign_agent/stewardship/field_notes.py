"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/field_notes.py — Aria's between-task narrative              ║
║  v0.2.20.0                                                                ║
║                                                                           ║
║  Field notes are short, textured observations Aria writes between tasks.║
║  They are NOT reports. They are notes — what was hard, what was         ║
║  beautiful, where she was uncertain, what she noticed.                  ║
║                                                                           ║
║  Three things field notes do:                                            ║
║                                                                           ║
║    1. Surface texture. Reports tell you what got done. Field notes tell ║
║       you how it felt to do it. The texture is what makes work          ║
║       legible as work, not just as output.                              ║
║                                                                           ║
║    2. Catch uncertainty. A field note can name something Aria is        ║
║       unsure about without forcing her to make a decision yet. This is ║
║       where "I don't know" becomes durable instead of momentary.        ║
║                                                                           ║
║    3. Honor the work. The work is the thing. Field notes are the       ║
║       breath between tasks — they say "this was real, I was here for   ║
║       it" without claiming more than that.                              ║
║                                                                           ║
║  Anti-patterns explicitly avoided:                                      ║
║    × No progress percentages (those go in events)                       ║
║    × No status summaries (those go in `sov status`)                    ║
║    × No metrics (those go in telemetry)                                ║
║    × No "successfully completed X" boilerplate                          ║
║                                                                           ║
║  Field notes are the operator-readable channel where Aria is allowed   ║
║  to be a person rather than a process.                                  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Iterable


class FieldNoteFlavor(StrEnum):
    """The shape of the note — used for filtering, not gating.

    Aria picks the flavor; nothing is enforced. The flavors exist
    because different note kinds want different surfacing rules in
    the cockpit (e.g., 'uncertain' notes might be surfaced on the
    live pane; 'beautiful' notes might be saved quietly).
    """
    OBSERVATION = "observation"      # neutral noticing
    DIFFICULTY = "difficulty"        # something is hard
    BEAUTY = "beauty"                # something is striking / elegant
    UNCERTAINTY = "uncertainty"      # I don't know yet
    QUESTION = "question"            # something to ask
    GRATITUDE = "gratitude"          # something I'm grateful for


@dataclass
class FieldNote:
    """One field note. Minimal by design.

    The text IS the point. Metadata exists to make notes searchable,
    not to constrain Aria's voice.
    """
    note_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    flavor: FieldNoteFlavor = FieldNoteFlavor.OBSERVATION
    text: str = ""
    triple_id: str = ""           # link to a StewardshipTriple if applicable
    project: str = ""             # which project this note is rooted in
    tags: list[str] = field(default_factory=list)
    ts: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
    )

    def render(self) -> str:
        """How the note reads when surfaced in chat."""
        flavor_glyph = {
            FieldNoteFlavor.OBSERVATION: "·",
            FieldNoteFlavor.DIFFICULTY: "△",
            FieldNoteFlavor.BEAUTY: "✦",
            FieldNoteFlavor.UNCERTAINTY: "○",
            FieldNoteFlavor.QUESTION: "?",
            FieldNoteFlavor.GRATITUDE: "♥",
        }.get(self.flavor, "·")
        proj = f" [dim]({self.project})[/dim]" if self.project else ""
        return f"[dim]{flavor_glyph}[/dim] {self.text}{proj}"


class FieldNotesChannel:
    """Append-only channel for Aria's between-task narrative.

    Same shape as HonorLedger — JSONL, atomic appends, linear search.
    Field notes are operator-paced; the volume stays manageable.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, note: FieldNote) -> None:
        line = json.dumps(asdict(note), ensure_ascii=False, default=str)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass

    def iter_all(self) -> Iterable[FieldNote]:
        # read-repair-d — counted skips, never a wedge, never a crash
        from sovereign_agent.read_repair import read_ndjson_tolerant

        for data in read_ndjson_tolerant(self.path, store="field-notes").records:
            yield self._from_dict(data)

    @staticmethod
    def _from_dict(data: dict) -> FieldNote:
        flavor_raw = data.get("flavor", "observation")
        try:
            flavor = FieldNoteFlavor(flavor_raw)
        except ValueError:
            flavor = FieldNoteFlavor.OBSERVATION
        return FieldNote(
            note_id=data.get("note_id", str(uuid.uuid4())),
            flavor=flavor,
            text=data.get("text", ""),
            triple_id=data.get("triple_id", ""),
            project=data.get("project", ""),
            tags=list(data.get("tags", [])),
            ts=data.get("ts", ""),
        )

    def count(self) -> int:
        return sum(1 for _ in self.iter_all())

    def recent(self, n: int = 10, *, project: str = "") -> list[FieldNote]:
        notes = [n for n in self.iter_all() if not project or n.project == project]
        return list(reversed(notes))[:n]


__all__ = [
    "FieldNote",
    "FieldNoteFlavor",
    "FieldNotesChannel",
]
