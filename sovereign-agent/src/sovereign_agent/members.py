"""members.py — 👥 the client database: she remembers everyone by ID.

Kevin's ask (2026-07-17): "have Aria remember each client by their ID —
note their ID and keep who they are. A client database. She should
always remember I am the owner, and always remember Camden (Discord name
Theodore) is one of my employees."

The Discord **user ID is stable** — it never changes when someone edits
their username — so it's the durable key. Each record carries the
username HISTORY (so a rename is tracked, not lost), the role, when we
first/last saw them, per-member stats, a free note, and their prefs
(region + fulfillment). One JSON file per member (the same durable
pattern as the rest of the shop), corrupt/missing → safe defaults.

Aria's ground truths (seeded, always true):
  • the owner (DISCORD_OWNER_ID) is Kevin — role "owner", never editable
    away from owner by anything but Kevin.
  • Camden (Discord "Theodore") is an employee — role "employee".
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

ROLE_OWNER = "owner"
ROLE_EMPLOYEE = "employee"
ROLE_SUBSCRIBER = "subscriber"
ROLE_MEMBER = "member"
_ROLE_RANK = {ROLE_OWNER: 3, ROLE_EMPLOYEE: 2, ROLE_SUBSCRIBER: 1,
              ROLE_MEMBER: 0}

# Kevin's standing team facts (seeded on first touch; owner from the vault)
KNOWN_TEAM: dict[str, str] = {
    # discord username (lowercased) : role — matched when an ID is unknown
    "theodore": ROLE_EMPLOYEE,        # Camden, Kevin's employee
}
TEAM_NOTES: dict[str, str] = {
    "theodore": "Camden — Kevin's employee (Support). Spectator + invites "
                "+ helps drive sales.",
}


def _dir(data_dir: Path) -> Path:
    return Path(data_dir) / "community" / "members"


def _safe_id(user_id: str) -> str:
    return re.sub(r"[^0-9]", "", str(user_id)) or "unknown"


def _path(data_dir: Path, user_id: str) -> Path:
    return _dir(data_dir) / f"{_safe_id(user_id)}.json"


def owner_id() -> str:
    return (os.environ.get("DISCORD_OWNER_ID") or "").strip()


def _blank(user_id: str, now: float) -> dict:
    return {"id": str(user_id), "aid": "", "names": [], "role": ROLE_MEMBER,
            "first_seen": now, "last_seen": now, "note": "",
            "stats": {}, "region": None, "fulfillment": "all"}


# ── Aria IDs (Kevin, 2026-07-19): our own stable ID per person ────────
# The Discord snowflake is the unfakeable anchor; the AID is OURS —
# platform-independent (survives a future web store/email lane), short
# enough to speak ("A-7K2M9Q"), and safe to show publicly without
# exposing anyone's Discord ID. Minted once at first contact, never
# reissued, never derived from the Discord ID (privacy by construction).
_AID_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"   # no 0/O/1/I/L lookalikes


def _aid_index_path(data_dir: Path) -> Path:
    return _dir(data_dir) / "_aid_index.json"


def _load_aid_index(data_dir: Path) -> dict:
    try:
        return json.loads(_aid_index_path(data_dir).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _mint_aid(data_dir: Path, user_id: str) -> str:
    import secrets

    index = _load_aid_index(data_dir)
    for _ in range(64):                       # collision-proof by retry
        aid = "A-" + "".join(secrets.choice(_AID_ALPHABET) for _ in range(6))
        if aid not in index:
            index[aid] = str(user_id)
            p = _aid_index_path(data_dir)
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp = p.with_suffix(".tmp")
                tmp.write_text(json.dumps(index, indent=2), encoding="utf-8")
                tmp.replace(p)
            except Exception:  # noqa: BLE001
                pass
            return aid
    return ""                                  # astronomically unlikely


def find_by_aid(data_dir: Path, aid: str) -> dict | None:
    """Resolve one of OUR IDs back to the member record."""
    user_id = _load_aid_index(data_dir).get((aid or "").strip().upper())
    return load_member(data_dir, user_id) if user_id else None


def load_member(data_dir: Path, user_id: str) -> dict | None:
    try:
        return json.loads(_path(data_dir, user_id).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _write(data_dir: Path, rec: dict) -> None:
    p = _path(data_dir, rec["id"])
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        tmp.replace(p)
    except Exception:  # noqa: BLE001
        pass


def _team_bindings_path(data_dir: Path) -> Path:
    return _dir(data_dir) / "_team_bindings.json"


def _resolve_role(data_dir: Path, user_id: str, username: str,
                  current: str) -> str:
    """Ground truths win: the vault owner is always owner (by ID, never
    by name); known team NAMES elevate exactly ONCE — the first Discord
    ID to claim a team name is bound to it forever, and any later
    account wearing the same name stays a plain member.

    Spoof-hole hardening (Kevin, 2026-07-19: "harden her for
    communities"): before this, renaming yourself 'Theodore' inherited
    the employee role. Now identity is ID-anchored; names are just
    clothes."""
    if owner_id() and str(user_id) == owner_id():
        return ROLE_OWNER
    uname = (username or "").strip().lower()
    if uname in KNOWN_TEAM:
        try:
            bindings = json.loads(
                _team_bindings_path(data_dir).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            bindings = {}
        bound = bindings.get(uname)
        if bound is None:
            bindings[uname] = str(user_id)          # first claim binds
            try:
                p = _team_bindings_path(data_dir)
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp = p.with_suffix(".tmp")
                tmp.write_text(json.dumps(bindings, indent=2),
                               encoding="utf-8")
                tmp.replace(p)
            except Exception:  # noqa: BLE001
                pass
            return _highest(current, KNOWN_TEAM[uname])
        if bound == str(user_id):                    # the real teammate
            return _highest(current, KNOWN_TEAM[uname])
        return current or ROLE_MEMBER                # an impersonator
    return current or ROLE_MEMBER


def _highest(a: str, b: str) -> str:
    return a if _ROLE_RANK.get(a, 0) >= _ROLE_RANK.get(b, 0) else b


def remember(data_dir: Path, user_id: str, username: str = "", *,
             now: float | None = None) -> dict:
    """See a member: create/update their record. Tracks username history
    (a rename appends, never overwrites — the ID is who they ARE), stamps
    last_seen, and holds ground-truth roles. Returns the record."""
    now = time.time() if now is None else now
    rec = load_member(data_dir, user_id) or _blank(user_id, now)
    uname = (username or "").strip()
    if uname and uname not in rec["names"]:
        rec["names"] = (rec["names"] + [uname])[-10:]   # keep rename history
    rec["last_seen"] = now
    if not rec.get("aid"):
        rec["aid"] = _mint_aid(data_dir, user_id)   # ours, once, forever
    rec["role"] = _resolve_role(data_dir, user_id, uname,
                                rec.get("role", ROLE_MEMBER))
    if rec["role"] == ROLE_EMPLOYEE and not rec.get("note"):
        rec["note"] = TEAM_NOTES.get(uname.lower(), "employee")
    if rec["role"] == ROLE_OWNER and not rec.get("note"):
        rec["note"] = "Kevin — the owner. Always."
    _write(data_dir, rec)
    return rec


def bump_stat(data_dir: Path, user_id: str, key: str, n: int = 1) -> None:
    """Per-client metric (commands run, finds viewed, pings on, …)."""
    rec = load_member(data_dir, user_id) or _blank(user_id, time.time())
    rec.setdefault("stats", {})[key] = int(rec["stats"].get(key, 0)) + n
    rec["last_seen"] = time.time()
    _write(data_dir, rec)


def set_role(data_dir: Path, user_id: str, role: str) -> dict:
    """Owner-driven role assignment (e.g. mark someone an employee).
    Never demotes the vault owner below owner."""
    rec = load_member(data_dir, user_id) or _blank(user_id, time.time())
    if owner_id() and str(user_id) == owner_id():
        role = ROLE_OWNER
    rec["role"] = role
    _write(data_dir, rec)
    return rec


def set_note(data_dir: Path, user_id: str, note: str) -> None:
    rec = load_member(data_dir, user_id) or _blank(user_id, time.time())
    rec["note"] = str(note or "")[:500]
    _write(data_dir, rec)


def set_prefs(data_dir: Path, user_id: str, *, region=None,
              fulfillment=None) -> dict:
    rec = load_member(data_dir, user_id) or _blank(user_id, time.time())
    if region is not None:
        rec["region"] = region
    if fulfillment is not None:
        rec["fulfillment"] = fulfillment
    _write(data_dir, rec)
    return rec


def display_name(rec: dict | None) -> str:
    if not rec or not rec.get("names"):
        return f"member {rec['id']}" if rec else "unknown"
    return rec["names"][-1]


def is_owner(data_dir: Path, user_id: str) -> bool:
    if owner_id() and str(user_id) == owner_id():
        return True
    rec = load_member(data_dir, user_id)
    return bool(rec and rec.get("role") == ROLE_OWNER)


def is_team(data_dir: Path, user_id: str) -> bool:
    """Owner or employee — the people who help run the shop."""
    rec = load_member(data_dir, user_id)
    return (is_owner(data_dir, user_id)
            or bool(rec and rec.get("role") in (ROLE_OWNER, ROLE_EMPLOYEE)))


def list_members(data_dir: Path) -> list[dict]:
    d = _dir(data_dir)
    out: list[dict] = []
    try:
        for p in d.glob("*.json"):
            if p.name.startswith("_"):     # _aid_index / _team_bindings
                continue
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return []
    out.sort(key=lambda r: (-_ROLE_RANK.get(r.get("role", ""), 0),
                            -float(r.get("last_seen", 0))))
    return out


def compose_roster(data_dir: Path) -> str:
    """A readable who's-who — the client database at a glance."""
    members = list_members(data_dir)
    if not members:
        return ("👥 No members recorded yet. She logs everyone by their "
                "Discord ID the moment they interact.")
    lines = [f"👥 Client database — {len(members)} known by ID", ""]
    for r in members[:60]:
        role = r.get("role", "member")
        mark = {"owner": "👑", "employee": "🛠", "subscriber": "⭐"}.get(role, "·")
        names = " / ".join(r.get("names", [])[-3:]) or r["id"]
        note = f" — {r['note']}" if r.get("note") else ""
        lines.append(f"{mark} {names}  [id {r['id']}] · {role}{note}")
    return "\n".join(lines)


def compose_recognition(data_dir: Path, user_id: str) -> str:
    """'Do you know who I am?' — answered from HER OWN client DB,
    deterministic, awake or asleep (Kevin's unanswered /ma, 2026-07-19).
    Warm, specific, never fabricated: only what the record actually holds."""
    rec = load_member(data_dir, user_id)
    if is_owner(data_dir, user_id):
        name = display_name(rec) if rec else "Kevin"
        return (f"👑 Of course I know you — you're {name}, the owner. "
                "This whole shop is ours; I keep your profile, your "
                "projects, and every note you've left me. 💛")
    if not rec:
        return ("We haven't been properly introduced yet — I log everyone "
                "by Discord ID the moment we interact, so I'll remember you "
                "from now on. Tell me your name if you like! 💛")
    role = rec.get("role", "member")
    mark = {"employee": "🛠 my teammate", "subscriber": "⭐ a subscriber"}.get(
        role, "a member of the shop")
    asks = int(rec.get("stats", {}).get("asks", 0) or 0)
    note = rec.get("note") or ""
    bits = [f"You're {display_name(rec)} — {mark}."]
    if rec.get("aid"):
        bits.append(f"Your Aria ID is {rec['aid']}.")
    if asks:
        bits.append(f"We've talked {asks} time{'s' if asks != 1 else ''} before.")
    if note:
        bits.append(f"My note on you says: {note}")
    bits.append("💛")
    return " ".join(bits)


RECOGNITION_TRIGGERS = (
    "who am i", "do you know who i am", "do you know me",
    "remember me", "do you remember me", "know who i am",
)


__all__ = ["ROLE_OWNER", "ROLE_EMPLOYEE", "ROLE_SUBSCRIBER", "ROLE_MEMBER",
           "KNOWN_TEAM", "owner_id", "load_member", "remember", "bump_stat",
           "set_role", "set_note", "set_prefs", "display_name", "is_owner",
           "is_team", "list_members", "compose_roster",
           "compose_recognition", "RECOGNITION_TRIGGERS", "find_by_aid"]
