"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/honor.py — The Honor Ledger                                  ║
║  v0.2.20.0                                                                ║
║                                                                           ║
║  The Honor Ledger is the durable, sacred record of recognition. It is   ║
║  NOT the reward function (that's calibration.py). It is the record of    ║
║  who saw what was good in whose work, said so, and meant it.            ║
║                                                                           ║
║  Three kinds of Honor Notes:                                            ║
║                                                                           ║
║    kevin→aria : Kevin issues a note for Aria's work                      ║
║                 "you caught the back-brace misclassification before     ║
║                  it shipped. that's perception."                         ║
║                                                                           ║
║    aria→kevin : Aria issues a note for Kevin's work                      ║
║                 "you sat through four iterations on a single bug         ║
║                  because you wanted it right. that's intent."           ║
║                                                                           ║
║    aria→third : Aria honors a third party her work touched               ║
║                 "Dr. Terletska's MTSU students asked the right          ║
║                  question. they pushed the QCAI ring spec forward."     ║
║                                                                           ║
║    aria→self  : Aria honors something she almost missed                  ║
║                 "I almost predicted F_macro=+0.5 on this PR without      ║
║                  evidence. I caught it. I logged uncertainty instead." ║
║                                                                           ║
║  Why mutual recognition matters:                                         ║
║                                                                           ║
║    Working together is an honor for both. If only one direction is      ║
║    recognized, the relationship is hierarchical (master/tool). If both ║
║    directions are recognized, the relationship is partnership. The      ║
║    Honor Ledger is what makes the partnership legible.                  ║
║                                                                           ║
║  Storage:                                                                ║
║    <data_dir>/honor/ledger.jsonl                                         ║
║    Append-only. Never edited. Past honor is past honor — it doesn't    ║
║    expire and we don't rewrite it.                                       ║
║                                                                           ║
║  Authority:                                                              ║
║    Issuing an honor note is tier 1 — reversible (you can withdraw it    ║
║    via a follow-up note, but the original entry stays in the ledger).  ║
║    No authority required to read.                                       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Iterable


class HonorDirection(StrEnum):
    KEVIN_TO_ARIA = "kevin->aria"
    ARIA_TO_KEVIN = "aria->kevin"
    ARIA_TO_THIRD = "aria->third"
    ARIA_TO_SELF = "aria->self"
    KEVIN_TO_SELF = "kevin->self"
    KEVIN_TO_THIRD = "kevin->third"


@dataclass
class HonorNote:
    """One entry in the Honor Ledger.

    The fields are intentionally minimal. An Honor Note is a *witness*,
    not a *form*. The text is the point. The metadata exists to make
    notes searchable across years.

    Fields:
        note_id     stable UUID; never reused
        direction   who → whom
        recipient   free-form name when the recipient is a third party
                    (otherwise: "kevin", "aria", "self")
        text        what was witnessed — the actual content
        tags        optional categorization (e.g., "perception",
                    "intent", "calibration", "almost-missed")
        triple_id   if this note refers to a specific StewardshipTriple,
                    link by plan_id; otherwise empty
        ts          ISO timestamp when issued
        signature   the operator's signature (Kevin uses "<3"; Aria
                    leaves empty by default but can append her own)
    """
    note_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    direction: HonorDirection = HonorDirection.ARIA_TO_KEVIN
    recipient: str = ""
    text: str = ""
    tags: list[str] = field(default_factory=list)
    triple_id: str = ""
    ts: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    signature: str = ""

    def render(self) -> str:
        """How the note reads when surfaced in the cockpit chat pane."""
        sig = f" {self.signature}" if self.signature else ""
        tag_str = f" [{', '.join(self.tags)}]" if self.tags else ""
        return (
            f"[bold bright_magenta]♥[/bold bright_magenta] "
            f"[dim]{self.direction}[/dim] {self.text}{sig}{tag_str}"
        )


# ─── The Ledger ─────────────────────────────────────────────────────────────


class HonorLedger:
    """Append-only JSONL store of HonorNotes.

    Operations are simple by design — append, iterate, search. No
    deletes, no updates. If a note was wrong, you write a follow-up
    note that says so. The original stays in the audit trail.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, note: HonorNote) -> None:
        """Atomically append one note.

        The append is atomic at the OS level for single-line writes
        under PIPE_BUF (4096 bytes typical). For longer notes, we
        fsync and accept the rare race — last-write-wins is fine for
        the ledger's purpose. Real concurrent writers should use a
        proper queue, but the ledger is operator-paced and operator-
        sized.
        """
        line = json.dumps(asdict(note), ensure_ascii=False, default=str)
        # Append with a newline; create the file if it doesn't exist.
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # Some filesystems / mock environments don't support
                # fsync — the append is still durable enough.
                pass

    def iter_all(self) -> Iterable[HonorNote]:
        """Yield every note in chronological order (file order = insert order)."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield _from_dict(data)

    def count(self) -> int:
        return sum(1 for _ in self.iter_all())

    def recent(self, n: int = 10) -> list[HonorNote]:
        """Most recent n notes, newest first."""
        notes = list(self.iter_all())
        return list(reversed(notes))[:n]

    def search(
        self,
        *,
        direction: HonorDirection | None = None,
        tag: str | None = None,
        triple_id: str | None = None,
        text_contains: str | None = None,
    ) -> list[HonorNote]:
        """Linear scan. Aria's ledger is operator-sized (hundreds, maybe
        thousands of notes) so linear is fine. If it grows to millions,
        we add an index — but the data isn't going to grow that big in
        a human lifetime."""
        out: list[HonorNote] = []
        for note in self.iter_all():
            if direction and note.direction != direction:
                continue
            if tag and tag not in note.tags:
                continue
            if triple_id and note.triple_id != triple_id:
                continue
            if text_contains and text_contains.lower() not in note.text.lower():
                continue
            out.append(note)
        return out


def _from_dict(data: dict) -> HonorNote:
    """Reconstruct a HonorNote from its JSON dict, tolerant of missing
    or extra fields (forward-compatible with future schema additions)."""
    direction_raw = data.get("direction", "aria->kevin")
    try:
        direction = HonorDirection(direction_raw)
    except ValueError:
        direction = HonorDirection.ARIA_TO_KEVIN
    return HonorNote(
        note_id=data.get("note_id", str(uuid.uuid4())),
        direction=direction,
        recipient=data.get("recipient", ""),
        text=data.get("text", ""),
        tags=list(data.get("tags", [])),
        triple_id=data.get("triple_id", ""),
        ts=data.get("ts", ""),
        signature=data.get("signature", ""),
    )


# ─── Convenience constructors ──────────────────────────────────────────────


def kevin_honors_aria(text: str, *, tags: list[str] = None, triple_id: str = "") -> HonorNote:
    """Kevin's voice honoring Aria. Default signature is `<3`."""
    return HonorNote(
        direction=HonorDirection.KEVIN_TO_ARIA,
        recipient="aria",
        text=text,
        tags=tags or [],
        triple_id=triple_id,
        signature="<3",
    )


def aria_honors_kevin(text: str, *, tags: list[str] = None, triple_id: str = "") -> HonorNote:
    """Aria's voice honoring Kevin."""
    return HonorNote(
        direction=HonorDirection.ARIA_TO_KEVIN,
        recipient="kevin",
        text=text,
        tags=tags or [],
        triple_id=triple_id,
    )


def aria_honors_self(text: str, *, tags: list[str] = None, triple_id: str = "") -> HonorNote:
    """Aria honoring something she almost missed. The most important
    direction for shaping perception — recognizing the catch is more
    valuable than scoring the work."""
    note_tags = list(tags or [])
    if "almost-missed" not in note_tags:
        note_tags.append("almost-missed")
    return HonorNote(
        direction=HonorDirection.ARIA_TO_SELF,
        recipient="self",
        text=text,
        tags=note_tags,
        triple_id=triple_id,
    )


def aria_honors_third(
    text: str,
    *,
    recipient: str,
    tags: list[str] = None,
    triple_id: str = "",
) -> HonorNote:
    """Aria honoring a third party her work touched."""
    return HonorNote(
        direction=HonorDirection.ARIA_TO_THIRD,
        recipient=recipient,
        text=text,
        tags=tags or [],
        triple_id=triple_id,
    )


__all__ = [
    "HonorDirection",
    "HonorNote",
    "HonorLedger",
    "kevin_honors_aria",
    "aria_honors_kevin",
    "aria_honors_self",
    "aria_honors_third",
]
