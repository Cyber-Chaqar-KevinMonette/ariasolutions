"""suggestions — users propose add-ons/updates; donations move them up.

Kevin's ask: users can ask Aria about potential add-ons or updates, submit
their own, and **donate to have their suggestion prioritized**. A demand-
driven roadmap that also earns — the community tells us what to build, and a
donation is a genuine signal of how much they want it.

The priority score is **donation-forward**: dollars dominate, votes add a
smaller nudge, so a paid boost visibly outranks a pile of free votes — but
free votes still matter (nobody's shut out). Aria surfaces the ranked list so
Kevin always knows the highest-leverage thing to build next.

Storage: one JSON per suggestion under `<data>/suggestions/`, atomic + fsync,
corrupt-file-resilient. Same durable pattern as the rest of the shop. The
donation itself is a Stripe link (`boost_url`); a confirmed payment calls
`boost()` to add cents (manual in Round 1, reconciler in Round 2).
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "Suggestion",
    "KINDS",
    "STATUSES",
    "VOTE_WEIGHT_CENTS",
    "add_suggestion",
    "load",
    "list_all",
    "vote",
    "boost",
    "set_status",
    "delete",
    "suggestions_dir",
    "compose_suggestions_report",
    "is_suggestions_query",
]

KINDS = ["addon", "update", "bug", "idea", "other"]
STATUSES = ["open", "planned", "in-progress", "done", "declined"]

# each free vote is worth this many "cents" of priority — small, so a real
# donation clearly outranks vote-brigading, but votes still count.
VOTE_WEIGHT_CENTS = 20


@dataclass
class Suggestion:
    text: str
    author: str = "anon"
    target: str = ""              # which bot/product it's about ("" = general)
    kind: str = "idea"
    votes: int = 0
    donation_cents: int = 0       # total confirmed boost donations
    status: str = "open"
    boost_url: str = ""           # Stripe donation link to prioritize this
    id: str = ""
    created_at: str = ""
    modified_at: str = ""

    @property
    def priority(self) -> int:
        return int(self.donation_cents) + int(self.votes) * VOTE_WEIGHT_CENTS

    @property
    def boost_label(self) -> str:
        d = self.donation_cents / 100
        money = f"${d:.0f}" if d == int(d) else f"${d:.2f}"
        return f"{money} boosted · {self.votes} vote(s)"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "Suggestion":
        data = json.loads(text)
        known = {f for f in Suggestion(text="x").as_dict()}
        return cls(**{k: v for k, v in data.items() if k in known})


def suggestions_dir(data_dir: Path) -> Path:
    p = Path(data_dir) / "suggestions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(data_dir: Path, sid: str) -> Path:
    safe = "".join(c for c in sid if c.isalnum())[:32] or "x"
    return suggestions_dir(data_dir) / f"{safe}.json"


def _save(s: Suggestion, data_dir: Path) -> Path:
    s.modified_at = datetime.now(timezone.utc).isoformat()
    path = _path(data_dir, s.id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(s.to_json(), encoding="utf-8")
    with open(tmp, "r+", encoding="utf-8") as fh:
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)
    return path


def add_suggestion(data_dir: Path, text: str, *, author: str = "anon",
                   target: str = "", kind: str = "idea",
                   boost_url: str = "") -> Suggestion:
    if not (text or "").strip():
        raise ValueError("suggestion text is required")
    if kind not in KINDS:
        kind = "idea"
    now = datetime.now(timezone.utc).isoformat()
    s = Suggestion(text=text.strip(), author=(author or "anon").strip()[:60],
                   target=target.strip()[:60], kind=kind, boost_url=boost_url,
                   id=uuid.uuid4().hex[:8], created_at=now)
    _save(s, data_dir)
    return s


def load(sid: str, data_dir: Path) -> Suggestion | None:
    path = _path(data_dir, sid)
    if not path.is_file():
        return None
    try:
        return Suggestion.from_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def list_all(data_dir: Path, *, status: str | None = None) -> list[Suggestion]:
    out: list[Suggestion] = []
    for f in sorted(suggestions_dir(data_dir).glob("*.json")):
        try:
            s = Suggestion.from_json(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — skip corrupt, never crash
            continue
        if status is not None and s.status != status:
            continue
        out.append(s)
    # highest priority first; ties broken by newest
    out.sort(key=lambda s: (s.priority, s.created_at), reverse=True)
    return out


def vote(sid: str, data_dir: Path, *, delta: int = 1) -> Suggestion | None:
    s = load(sid, data_dir)
    if s is None:
        return None
    s.votes = max(0, s.votes + delta)
    _save(s, data_dir)
    return s


def boost(sid: str, data_dir: Path, *, cents: int) -> Suggestion | None:
    """Record a confirmed donation boost (adds to donation_cents)."""
    s = load(sid, data_dir)
    if s is None or cents <= 0:
        return s
    s.donation_cents += int(cents)
    _save(s, data_dir)
    return s


def set_status(sid: str, data_dir: Path, status: str) -> Suggestion | None:
    if status not in STATUSES:
        raise ValueError(f"status {status!r} not one of {STATUSES}")
    s = load(sid, data_dir)
    if s is None:
        return None
    s.status = status
    _save(s, data_dir)
    return s


def delete(sid: str, data_dir: Path) -> bool:
    path = _path(data_dir, sid)
    if not path.is_file():
        return False
    path.unlink()
    return True


def compose_suggestions_report(data_dir: Path | None = None, *, limit: int = 8) -> str:
    if data_dir is None:
        try:
            from sovereign_agent.config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
        except Exception:  # noqa: BLE001
            return "I can't read the suggestions right now."
    # only the still-actionable ones
    active = [s for s in list_all(data_dir) if s.status in ("open", "planned", "in-progress")]
    if not active:
        return ("No suggestions yet. Anyone can propose an add-on or update — "
                "and boost it with a donation to move it up the list. 💛")
    lines = [f"💡 Top {min(limit, len(active))} suggestion(s) "
             f"(donations move them up):"]
    for i, s in enumerate(active[:limit], 1):
        tgt = f" [{s.target}]" if s.target else ""
        lines.append(f"  {i}. [b]{s.text}[/b]{tgt} — {s.boost_label} "
                     f"[dim]({s.kind}, {s.status})[/dim]")
    return "\n".join(lines)


# Precise, feature-specific triggers only — the bare word "suggestions" is
# deliberately NOT here (it collides with next_report's "any suggestions?" =
# "what do you suggest I do?"). Keep these unambiguous about the FEATURE.
_SUGGEST_TRIGGERS = (
    "community suggestion", "user suggestion", "the suggestions", "suggestion box",
    "suggestion list", "feature request", "add-on request", "addon request",
    "what should we build", "what to build next", "the roadmap", "roadmap request",
    "what do people want", "vote for", "boost my suggestion", "our suggestions",
)


def is_suggestions_query(text: str) -> bool:
    if not text:
        return False
    from sovereign_agent.bridge_patterns import match_any
    return match_any(text, _SUGGEST_TRIGGERS)
