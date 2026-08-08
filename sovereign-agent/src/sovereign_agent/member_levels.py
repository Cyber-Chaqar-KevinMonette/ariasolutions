"""member_levels — activity levels, so the room rewards showing up.

levels-d (Kevin, 2026-08-03): "add a leveling system per new member too...
for activity."

Pure + injectable: every function takes `now` and (where it matters) the xp
amount, so the whole curve is testable without a clock, a random seed, or a
Discord connection. The bot layer just calls `award()` on each message.

Design decisions worth stating, because they're what separates a level
system people enjoy from one they game:

  • **Per-user cooldown.** XP is granted at most once per COOLDOWN_S. Without
    it the leaderboard measures who spams hardest, which poisons the exact
    thing it's meant to encourage — and it would make Aria's own channels
    noisier, not better.
  • **A band, not a constant.** 15-25 xp keeps totals from being a trivially
    predictable message-count × k, so there's nothing to optimise against.
  • **Quadratic curve.** Each level costs meaningfully more than the last,
    so early levels arrive fast (a new member sees progress on day one) and
    later ones stay meaningful.
  • **Storage is one small JSON file, written atomically.** A corrupt or
    missing file degrades to "everyone is level 0" — never an exception on
    the message path, because a crash there takes the gateway down.
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

__all__ = [
    "XP_MIN", "XP_MAX", "COOLDOWN_S", "CURVE_A", "CURVE_B",
    "xp_to_reach", "level_for_xp", "xp_into_level", "xp_for_next",
    "award", "get", "leaderboard", "levels_path",
]

XP_MIN, XP_MAX = 15, 25
COOLDOWN_S = 60.0

# cumulative xp to REACH level n: A*n^2 + B*n
#
# Deliberately NO constant term. A constant makes the very first level cost
# more than the second (0→1 = A+B+C, but 1→2 = 3A+B), so the curve dips
# instead of rising and level 2 feels easier than level 1 — caught by
# test_curve_is_strictly_increasing. With C dropped, the per-level cost is
# 2A*n + A + B: strictly increasing from the first level onward.
CURVE_A, CURVE_B = 5, 45


def xp_to_reach(level: int) -> int:
    """Total lifetime xp needed to be AT `level`. Level 0 is free."""
    if level <= 0:
        return 0
    return CURVE_A * level * level + CURVE_B * level


def level_for_xp(xp: int) -> int:
    """Highest level this much xp has earned. Monotone; never negative."""
    xp = max(0, int(xp or 0))
    level = 0
    while xp >= xp_to_reach(level + 1):
        level += 1
        if level > 10_000:                 # paranoia: never spin forever
            break
    return level


def xp_into_level(xp: int) -> int:
    """Progress through the CURRENT level — what a progress bar shows."""
    return max(0, int(xp or 0) - xp_to_reach(level_for_xp(xp)))


def xp_for_next(xp: int) -> int:
    """XP still needed for the next level."""
    lvl = level_for_xp(xp)
    return max(0, xp_to_reach(lvl + 1) - int(xp or 0))


# ── store ───────────────────────────────────────────────────────────────
def levels_path(data_dir: Path) -> Path:
    p = Path(data_dir) / "member_levels.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read(data_dir: Path) -> dict:
    path = levels_path(data_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — corrupt file must never break chat
        return {}


def _write(data_dir: Path, data: dict) -> None:
    path = levels_path(data_dir)
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(data), encoding="utf-8")
        with open(tmp, "r+", encoding="utf-8") as fh:
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
    except Exception:  # noqa: BLE001
        pass


def get(data_dir: Path, user_id: str) -> dict:
    """{'xp', 'level', 'messages'} for one member — zeros if unknown."""
    rec = _read(data_dir).get(str(user_id)) or {}
    xp = int(rec.get("xp", 0))
    return {"xp": xp, "level": level_for_xp(xp),
            "messages": int(rec.get("messages", 0)),
            "into_level": xp_into_level(xp), "to_next": xp_for_next(xp)}


def award(data_dir: Path, user_id: str, *, now: float,
          amount: int | None = None,
          cooldown_s: float = COOLDOWN_S) -> dict | None:
    """Grant xp for one message.

    Returns None when the member is still on cooldown — the caller does
    nothing, which is the common case and must stay cheap. Otherwise
    returns the new state plus `leveled_up`, so the bot only announces on
    a real transition.
    """
    uid = str(user_id)
    data = _read(data_dir)
    rec = data.get(uid) or {}
    last = float(rec.get("last_ts", 0) or 0)
    if now - last < cooldown_s:
        return None

    if amount is None:
        amount = random.randint(XP_MIN, XP_MAX)
    before = int(rec.get("xp", 0))
    after = before + int(amount)
    old_level, new_level = level_for_xp(before), level_for_xp(after)

    data[uid] = {"xp": after, "last_ts": now,
                 "messages": int(rec.get("messages", 0)) + 1}
    _write(data_dir, data)
    return {"xp": after, "level": new_level, "gained": int(amount),
            "leveled_up": new_level > old_level,
            "into_level": xp_into_level(after), "to_next": xp_for_next(after)}


def leaderboard(data_dir: Path, limit: int = 10) -> list[dict]:
    rows = []
    for uid, rec in (_read(data_dir) or {}).items():
        xp = int((rec or {}).get("xp", 0))
        rows.append({"user_id": uid, "xp": xp, "level": level_for_xp(xp),
                     "messages": int((rec or {}).get("messages", 0))})
    rows.sort(key=lambda r: -r["xp"])
    return rows[:max(1, limit)]
