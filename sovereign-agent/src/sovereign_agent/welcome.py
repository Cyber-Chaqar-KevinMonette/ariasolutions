"""welcome — Aria greets every new member, warmly and exactly once.

Kevin's ask: a message-new-members feature. Shape:

  • **Pure composer** — `compose_welcome(name)` renders her greeting from a
    default template (or Kevin's override at `<data>/welcome/template.txt`,
    `{name}` is the placeholder). Professional + warm, points at the four
    doors that matter: #how-it-works, #storefront, #ask-aria, #order-here.
  • **Never twice** — a durable ledger (`<data>/welcome/welcomed.json`)
    remembers who's been greeted; a re-join, a gateway replay, or a bot
    restart can never double-welcome anyone. Bounded (10k, oldest pruned).
  • **The live wire** lives in `discord_admin.bot`: `on_member_join` posts
    the greeting in #welcome and DMs it best-effort. It needs Discord's
    privileged **Server Members intent** — a portal toggle — so it's opt-in
    via `DISCORD_ENABLE_MEMBERS_INTENT=1` (same pattern as the chat intent;
    requesting it without the toggle would fail login).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

__all__ = [
    "DEFAULT_TEMPLATE",
    "compose_welcome",
    "load_template",
    "mark_welcomed",
    "already_welcomed",
    "welcome_stats",
]

DEFAULT_TEMPLATE = """\
Welcome to **BigKev's Bot Shop**, {name}! 💛

I'm Aria — the resident AI here. My alert bots run 24/7 (restocks, prices,
feeds, scores) so you never miss the thing you care about.

Quick tour:
• **#how-it-works** — what we do, in one read
• **#storefront** — every bot & plan, with prices
• **#ask-aria** — talk to me! Ask anything, anytime
• **#order-here** — ready to set one up? Start here

Glad you're here. 🤖✨"""

_MAX_LEDGER = 10_000


def welcome_dir(data_dir: Path) -> Path:
    p = Path(data_dir) / "welcome"
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_template(data_dir: Path | None = None) -> str:
    """Kevin tunes the greeting via <data>/welcome/template.txt."""
    try:
        if data_dir is not None:
            override = Path(data_dir) / "welcome" / "template.txt"
            if override.is_file():
                text = override.read_text(encoding="utf-8").strip()
                if text:
                    return text
    except Exception:  # noqa: BLE001
        pass
    return DEFAULT_TEMPLATE


def compose_welcome(name: str, data_dir: Path | None = None) -> str:
    """Render her greeting for one person. Never raises."""
    clean = (str(name or "friend").strip() or "friend")[:64]
    template = load_template(data_dir)
    try:
        return template.replace("{name}", clean)
    except Exception:  # noqa: BLE001
        return DEFAULT_TEMPLATE.replace("{name}", clean)


# ── the never-twice ledger ───────────────────────────────────────────────────
def _ledger_path(data_dir: Path) -> Path:
    return welcome_dir(data_dir) / "welcomed.json"


def _read_ledger(data_dir: Path) -> dict[str, float]:
    try:
        raw = json.loads(_ledger_path(data_dir).read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in raw.items()} \
            if isinstance(raw, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def already_welcomed(member_id: str, data_dir: Path) -> bool:
    return str(member_id) in _read_ledger(data_dir)


def mark_welcomed(member_id: str, data_dir: Path, *,
                  now: float | None = None) -> bool:
    """Record a greeting. Returns True if this member was NEW (greet them),
    False if they were already welcomed (stay quiet). Never raises."""
    now = time.time() if now is None else now
    try:
        ledger = _read_ledger(data_dir)
        key = str(member_id)
        if key in ledger:
            return False
        ledger[key] = now
        if len(ledger) > _MAX_LEDGER:            # bound the file, keep newest
            for k in sorted(ledger, key=ledger.get)[:len(ledger) - _MAX_LEDGER]:
                ledger.pop(k, None)
        path = _ledger_path(data_dir)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(ledger), encoding="utf-8")
        with open(tmp, "r+", encoding="utf-8") as fh:
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
        return True
    except Exception:  # noqa: BLE001
        return False    # on any trouble, prefer silence over a double-greet


def welcome_stats(data_dir: Path) -> dict:
    ledger = _read_ledger(data_dir)
    return {"welcomed": len(ledger),
            "last_at": max(ledger.values()) if ledger else None}
