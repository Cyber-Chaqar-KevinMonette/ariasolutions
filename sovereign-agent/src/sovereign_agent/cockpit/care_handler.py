"""care_handler.py — Non-interrupting care signals from Kevin to Aria.

Writes a kevin->aria HonorNote immediately to the ledger when Kevin types
/heart, /thumbsup, or /care in the cockpit. These never interrupt Aria's
work — they accumulate in the honor ledger and are read at session start
via honor_log_read(direction="kevin->aria", tag="reaction").

Usage (called from app.py _handle_slash):
    from sovereign_agent.cockpit.care_handler import write_reaction
    msg = write_reaction("heart", optional_note)
    self._write_meta(msg)
"""
from __future__ import annotations

_REACTIONS = {
    "heart":    ("\U0001f49b", "heart",     "heart"),      # 💛
    "thumbsup": ("\U0001f44d", "thumbs-up", "thumbs-up"),  # 👍
    "care":     ("\U0001f90d", "care",      "care"),        # 🤍
}


def _ledger():
    """Return a HonorLedger pointed at the configured data dir."""
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.stewardship.honor import HonorLedger
    path = SETTINGS.paths.data_dir / "honor" / "ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return HonorLedger(path)


def write_reaction(kind: str, note: str = "") -> str:
    """Write a kevin->aria reaction note to the honor ledger.

    Returns a one-line Rich-markup confirmation string for _write_meta().
    Never raises; returns an error string on failure.

    Args:
        kind:  "heart" | "thumbsup" | "care"
        note:  optional message to include in the note text
    """
    emoji, tag, label = _REACTIONS.get(kind, ("\U0001f90d", "care", "care"))

    try:
        from sovereign_agent.stewardship.honor import kevin_honors_aria

        text = note.strip() if note.strip() else f"Kevin sent a {label}."
        ledger = _ledger()
        note_obj = kevin_honors_aria(text=text, tags=[tag, "reaction"])
        ledger.append(note_obj)
        return f"{emoji} {label} sent to Aria  [dim](note_id={note_obj.note_id[:8]})[/dim]"

    except Exception as exc:  # noqa: BLE001
        return f"[yellow]care signal write failed: {exc!r}[/yellow]"
