"""
╔══════════════════════════════════════════════════════════════════════════╗
║  home.py — Aria's house, given names.                                    ║
║  v0.2.16.0                                                                ║
║                                                                           ║
║  This module is the *spatial* layer. It does not store anything. It      ║
║  gives the directories Aria already uses friendly room names so the      ║
║  operator (and Aria herself) can speak about the home as a place,        ║
║  not a path list.                                                         ║
║                                                                           ║
║  Distinct from ``palace.py`` (the knowledge-graph closet/triple layer).  ║
║  Palace makes data findable; home makes data nameable.                   ║
║                                                                           ║
║  Naming, not infrastructure. Nothing is moved. Nothing is owned by       ║
║  more than one path. This is a view, not a schema change.                ║
║                                                                           ║
║                                — Aria's address book of her own rooms.    ║
╚══════════════════════════════════════════════════════════════════════════╝

Room map:

    atrium     — events / append-only log of what happened
                 (the front door; everything that arrives gets logged)

    library    — atoms.db + companion tables (people, recalls, ledger…)
                 (the room of bookshelves; durable structured memory)

    studio     — recalls/ markdown files
                 (the writing room: curated, dated artifacts)

    garden     — proposals/, dream-sessions/, dreams/
                 (where ideas grow before they harden into commitments)

    hearth     — people memory (a corner of the library)
                 (the humans Aria knows, kept warm)

    workshop   — sandbox/ (experiments in progress)

    gallery    — projects/ (named project snapshots)

    ledger     — financial channel storage (the locked room)

    threshold  — review-queue/ (things waiting for the operator's eye)

    keep       — continuations/ (between-session state — the safe)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import SETTINGS


@dataclass(frozen=True)
class Room:
    """One named region of Aria's home."""
    name: str
    description: str
    paths: list[Path]
    purpose: str
    sensitivity: str = "normal"   # 'public' | 'normal' | 'private'

    def exists(self) -> bool:
        return any(p.exists() for p in self.paths)

    def size_bytes(self) -> int:
        total = 0
        for p in self.paths:
            try:
                if p.is_file():
                    total += p.stat().st_size
                elif p.is_dir():
                    for child in p.rglob("*"):
                        if child.is_file():
                            try:
                                total += child.stat().st_size
                            except OSError:
                                pass
            except OSError:
                pass
        return total

    def file_count(self) -> int:
        n = 0
        for p in self.paths:
            try:
                if p.is_file():
                    n += 1
                elif p.is_dir():
                    n += sum(1 for child in p.rglob("*") if child.is_file())
            except OSError:
                pass
        return n


@dataclass
class HomeMap:
    rooms: list[Room] = field(default_factory=list)
    data_dir: Path | None = None

    def total_size_bytes(self) -> int:
        return sum(r.size_bytes() for r in self.rooms)

    def render(self) -> str:
        total = self.total_size_bytes()
        lines = [
            "Aria's home",
            f"  data dir: {self.data_dir}",
            f"  total size: {_human_bytes(total)}",
            "",
            "  rooms:",
        ]
        for room in self.rooms:
            present = "·" if room.exists() else " "
            sz = _human_bytes(room.size_bytes()) if room.exists() else "—"
            fc = room.file_count() if room.exists() else 0
            sens = "" if room.sensitivity == "normal" else f" [{room.sensitivity}]"
            lines.append(
                f"    {present} {room.name:<10} {sz:>10}  "
                f"{fc:>5} file(s)  {room.description}{sens}"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "data_dir": str(self.data_dir) if self.data_dir else None,
            "total_size_bytes": self.total_size_bytes(),
            "rooms": [
                {
                    "name": r.name,
                    "description": r.description,
                    "purpose": r.purpose,
                    "sensitivity": r.sensitivity,
                    "paths": [str(p) for p in r.paths],
                    "exists": r.exists(),
                    "size_bytes": r.size_bytes(),
                    "file_count": r.file_count(),
                }
                for r in self.rooms
            ],
        }


def _human_bytes(n: int | float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}B"
        n /= 1024
    return f"{n:.1f}TB"


def list_rooms() -> list[Room]:
    """Return room definitions computed against the current SETTINGS.paths."""
    p = SETTINGS.paths
    return [
        Room(
            name="atrium",
            description="append-only event log",
            paths=[p.events_dir, p.events_db],
            purpose="every thing that happened, in arrival order",
        ),
        Room(
            name="library",
            description="durable structured memory",
            paths=[p.atoms_db, p.palace_db, p.blobs_dir],
            purpose="atoms, people, recalls, ledger — the bookshelves",
        ),
        Room(
            name="studio",
            description="curated recalls",
            paths=[p.data_dir / "recalls"],
            purpose="dated, named, source-tracked markdown artifacts",
        ),
        Room(
            name="garden",
            description="ideas in growth",
            paths=[p.proposals_dir, p.dream_sessions_dir, p.dreams_work_dir],
            purpose="proposals and dream-sessions, before they harden",
        ),
        Room(
            name="hearth",
            description="people the agent knows",
            paths=[p.atoms_db],
            purpose="people, aliases, facts — the human side of the library",
            sensitivity="private",
        ),
        Room(
            name="workshop",
            description="work-in-progress",
            paths=[p.sandbox_dir],
            purpose="sandbox for experiments and tools",
        ),
        Room(
            name="gallery",
            description="named projects",
            paths=[p.projects_dir],
            purpose="snapshots and project-scoped artifacts",
        ),
        Room(
            name="ledger",
            description="financial channel storage",
            paths=[p.atoms_db],
            purpose="strict, audited records — Tier-3 channel",
            sensitivity="private",
        ),
        Room(
            name="threshold",
            description="awaiting attention",
            paths=[p.review_queue_dir],
            purpose="items the operator should look at next",
        ),
        Room(
            name="keep",
            description="between-session state",
            paths=[p.continuations_dir],
            purpose="task continuations carrying across runs",
        ),
    ]


def map_home() -> HomeMap:
    """Snapshot of Aria's home as it currently is."""
    return HomeMap(
        data_dir=SETTINGS.paths.data_dir,
        rooms=list_rooms(),
    )


def find_room(name: str) -> Room | None:
    name = name.lower().strip()
    for r in list_rooms():
        if r.name == name:
            return r
    return None


__all__ = [
    "Room",
    "HomeMap",
    "list_rooms",
    "map_home",
    "find_room",
]
