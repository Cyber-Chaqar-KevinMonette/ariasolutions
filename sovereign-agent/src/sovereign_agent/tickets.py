"""tickets.py — 🎫 advanced private ticketing (open → claimed → resolved).

Kevin's ask: a proper private ticketing system. A member opens a ticket
(order help, support, a custom-bot request, billing, or other); it lives in
a **private thread** only they + Owner/Staff/Support + Aria can see. Staff
**claim** it, work it, then **resolve** and **close** it. Every step is
ledgered (audited, visible in Discord Watch) and the owner has a board of
all open tickets.

Pure + tested: this module owns the ticket store + the state machine only;
the Discord thread creation / buttons live in `discord_admin/bot.py`.
Durable one-JSON-per-ticket (same pattern as members/referrals), an index
with a monotonic counter for readable IDs (T0001…), and an append-only
event log on each ticket. Corrupt/missing → safe defaults, never a crash.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

# ── the state machine ────────────────────────────────────────────────────────
OPEN = "open"
CLAIMED = "claimed"
RESOLVED = "resolved"
CLOSED = "closed"

# who's allowed to move a ticket forward (Discord roles; owner always may)
STAFF_ROLES = ("Staff", "Support")

CATEGORIES: dict[str, str] = {
    "order": "🧾 Order help",
    "support": "🛠 Support",
    "custom": "🤖 Custom bot request",
    "billing": "💳 Billing",
    "other": "💬 Other",
}

# allowed transitions: from -> {to}
_TRANSITIONS: dict[str, set[str]] = {
    OPEN: {CLAIMED, RESOLVED, CLOSED},
    CLAIMED: {RESOLVED, CLOSED, OPEN},      # can be released back to open
    RESOLVED: {CLOSED, OPEN},               # reopen if not actually fixed
    CLOSED: {OPEN},                         # reopen
}


def can_transition(frm: str, to: str) -> bool:
    return to in _TRANSITIONS.get(frm, set())


# ── paths ────────────────────────────────────────────────────────────────────
def _dir(data_dir: Path) -> Path:
    return Path(data_dir) / "community" / "tickets"


def _path(data_dir: Path, tid: str) -> Path:
    safe = "".join(c for c in str(tid) if c.isalnum())
    return _dir(data_dir) / f"{safe}.json"


def _index_path(data_dir: Path) -> Path:
    return _dir(data_dir) / "index.json"


def _load_index(data_dir: Path) -> dict:
    try:
        d = json.loads(_index_path(data_dir).read_text("utf-8"))
        if isinstance(d, dict):
            d.setdefault("counter", 0)
            d.setdefault("open", [])
            return d
    except Exception:  # noqa: BLE001
        pass
    return {"counter": 0, "open": []}


def _save_index(data_dir: Path, idx: dict) -> None:
    p = _index_path(data_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(idx, indent=2), encoding="utf-8")
        tmp.replace(p)
    except Exception:  # noqa: BLE001
        pass


def _write(data_dir: Path, t: dict) -> None:
    p = _path(data_dir, t["id"])
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(t, indent=2), encoding="utf-8")
        tmp.replace(p)
    except Exception:  # noqa: BLE001
        pass


def load(data_dir: Path, tid: str) -> dict | None:
    try:
        return json.loads(_path(data_dir, tid).read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _log(t: dict, actor: str, action: str, detail: str = "") -> None:
    t.setdefault("events", []).append(
        {"ts": time.time(), "actor": str(actor), "action": action,
         "detail": detail})
    t["updated_ts"] = time.time()


# ── public API ───────────────────────────────────────────────────────────────
def open_ticket(data_dir: Path, opener_id: str, opener_name: str,
                category: str, subject: str, *,
                now: float | None = None) -> dict:
    """Create a ticket, return the record. Category falls back to 'other';
    subject is trimmed. Assigns a readable id (T0001…)."""
    now = time.time() if now is None else now
    idx = _load_index(data_dir)
    idx["counter"] = int(idx.get("counter", 0)) + 1
    tid = f"T{idx['counter']:04d}"
    cat = category if category in CATEGORIES else "other"
    t = {"id": tid, "opener_id": str(opener_id),
         "opener_name": str(opener_name or opener_id),
         "category": cat, "subject": (subject or "(no subject)").strip()[:300],
         "status": OPEN, "claimed_by": None, "claimed_name": None,
         "channel_id": None, "created_ts": now, "updated_ts": now,
         "events": []}
    _log(t, opener_id, "opened", f"{cat}: {t['subject']}")
    _write(data_dir, t)
    if tid not in idx["open"]:
        idx["open"].append(tid)
    _save_index(data_dir, idx)
    return t


def set_channel(data_dir: Path, tid: str, channel_id) -> dict | None:
    t = load(data_dir, tid)
    if t is None:
        return None
    t["channel_id"] = str(channel_id)
    _write(data_dir, t)
    return t


def _drop_from_open(data_dir: Path, tid: str) -> None:
    idx = _load_index(data_dir)
    if tid in idx["open"]:
        idx["open"].remove(tid)
        _save_index(data_dir, idx)


def _add_to_open(data_dir: Path, tid: str) -> None:
    idx = _load_index(data_dir)
    if tid not in idx["open"]:
        idx["open"].append(tid)
        _save_index(data_dir, idx)


def _move(data_dir: Path, tid: str, to: str, actor: str, actor_name: str,
          action: str, detail: str = "") -> tuple[bool, str, dict | None]:
    t = load(data_dir, tid)
    if t is None:
        return False, "That ticket doesn't exist.", None
    if t["status"] == to and to != OPEN:
        return False, f"Ticket {tid} is already {to}.", t
    if not can_transition(t["status"], to):
        return False, f"Can't go from {t['status']} to {to}.", t
    t["status"] = to
    _log(t, actor, action, detail)
    _write(data_dir, t)
    return True, "", t


def claim(data_dir: Path, tid: str, staff_id: str,
          staff_name: str) -> tuple[bool, str, dict | None]:
    t = load(data_dir, tid)
    if t is None:
        return False, "That ticket doesn't exist.", None
    if t["status"] == CLAIMED:
        if t.get("claimed_by") == str(staff_id):
            return True, "", t                  # idempotent re-claim by owner
        return False, (f"Already claimed by {t.get('claimed_name')}."), t
    ok, msg, t = _move(data_dir, tid, CLAIMED, staff_id, staff_name,
                       "claimed", f"by {staff_name}")
    if ok and t is not None:
        t["claimed_by"] = str(staff_id)
        t["claimed_name"] = str(staff_name)
        _write(data_dir, t)
    return ok, msg, t


def resolve(data_dir: Path, tid: str, actor: str,
            actor_name: str = "") -> tuple[bool, str, dict | None]:
    return _move(data_dir, tid, RESOLVED, actor, actor_name, "resolved")


def close(data_dir: Path, tid: str, actor: str,
          actor_name: str = "") -> tuple[bool, str, dict | None]:
    ok, msg, t = _move(data_dir, tid, CLOSED, actor, actor_name, "closed")
    if ok:
        _drop_from_open(data_dir, tid)
    return ok, msg, t


def reopen(data_dir: Path, tid: str, actor: str,
           actor_name: str = "") -> tuple[bool, str, dict | None]:
    ok, msg, t = _move(data_dir, tid, OPEN, actor, actor_name, "reopened")
    if ok:
        _add_to_open(data_dir, tid)
    return ok, msg, t


def add_message(data_dir: Path, tid: str, author: str, text: str) -> dict | None:
    t = load(data_dir, tid)
    if t is None:
        return None
    _log(t, author, "message", str(text)[:500])
    _write(data_dir, t)
    return t


def list_open(data_dir: Path) -> list[dict]:
    idx = _load_index(data_dir)
    out = [load(data_dir, tid) for tid in idx.get("open", [])]
    out = [t for t in out if t]
    out.sort(key=lambda t: t.get("created_ts", 0))
    return out


def list_for_user(data_dir: Path, user_id: str) -> list[dict]:
    out: list[dict] = []
    try:
        for p in _dir(data_dir).glob("T*.json"):
            try:
                t = json.loads(p.read_text("utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if t.get("opener_id") == str(user_id):
                out.append(t)
    except Exception:  # noqa: BLE001
        return []
    out.sort(key=lambda t: -t.get("created_ts", 0))
    return out


# ── composers ────────────────────────────────────────────────────────────────
_BADGE = {OPEN: "🟢 open", CLAIMED: "🟡 claimed", RESOLVED: "✅ resolved",
          CLOSED: "⚪ closed"}


def compose_ticket(t: dict) -> str:
    cat = CATEGORIES.get(t.get("category", "other"), "💬 Other")
    lines = [f"🎫 **Ticket {t['id']}** · {_BADGE.get(t['status'], t['status'])}",
             f"**{cat}** — {t.get('subject', '')}",
             f"Opened by **{t.get('opener_name', t['opener_id'])}**"]
    if t.get("claimed_name"):
        lines.append(f"Claimed by **{t['claimed_name']}**")
    return "\n".join(lines)


def compose_board(data_dir: Path) -> str:
    """Owner/staff overview of every open ticket."""
    tickets = list_open(data_dir)
    if not tickets:
        return "🎫 **Ticket board** — no open tickets. All clear! 💛"
    lines = [f"🎫 **Ticket board** — {len(tickets)} open", ""]
    for t in tickets:
        cat = CATEGORIES.get(t.get("category", "other"), "💬")
        who = t.get("claimed_name") or "unclaimed"
        lines.append(f"{_BADGE.get(t['status'], '')} **{t['id']}** · {cat} · "
                     f"{t.get('subject', '')[:50]} · {who}")
    return "\n".join(lines)


__all__ = [
    "OPEN", "CLAIMED", "RESOLVED", "CLOSED", "STAFF_ROLES", "CATEGORIES",
    "can_transition", "open_ticket", "set_channel", "claim", "resolve",
    "close", "reopen", "add_message", "load", "list_open", "list_for_user",
    "compose_ticket", "compose_board",
]
