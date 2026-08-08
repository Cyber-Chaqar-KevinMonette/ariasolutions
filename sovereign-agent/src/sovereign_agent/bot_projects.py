"""bot_projects — define bot projects (name, kind, concept) before building.

Kevin's ask: a studio where he names a project, names the bot, picks its
kind (from a list + Other), and writes a description of the concept — so he
and Aria share where they're heading. This is the DIRECTION-SETTING layer:
the mature "define before build" first floor toward income (his own kernel:
build a stable floor for ourselves first, then build floor under others).

The actual bot runtime (discord.py client, monitors, delivery) is a later,
separate build (Plans/NextPlan3/DiscordBotStudio/DESIGN.md) that reads these
project records. This module is only the definition + durable store.

Storage: one JSON file per project under `<data>/bot_projects/<slug>.json`.
Simple, durable, greppable, easy to back up. Pure model + thin file I/O.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "BotProject",
    "BOT_KINDS",
    "slugify",
    "validate",
    "save",
    "load",
    "list_all",
    "delete",
    "projects_dir",
    "is_bots_query",
    "compose_bots_report",
]

# Curated, extensible bot-kind categories. (key, human label). "other" lets
# the operator name a kind we haven't catalogued.
BOT_KINDS: list[tuple[str, str]] = [
    ("restock-alert", "Restock / price-alert"),
    ("community-mod", "Community / moderation"),
    ("notification-feed", "Notification / feed (RSS · API · sports · releases)"),
    ("reminder-schedule", "Reminder / scheduling"),
    ("welcome-onboard", "Welcome / onboarding"),
    ("role-reaction", "Role / reaction-role"),
    ("support-ticket", "Support / ticket"),
    ("analytics-stats", "Analytics / stats"),
    ("other", "Other (name it below)"),
]
_KIND_KEYS = {k for k, _ in BOT_KINDS}

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,60}$")


@dataclass
class BotProject:
    """One bot project's definition (the concept, not the code)."""
    project_name: str
    bot_name: str = ""
    kind: str = "other"
    kind_other: str = ""          # freeform kind when kind == "other"
    description: str = ""         # the concept / direction
    # optional details, requested as needed
    audience: str = ""
    monetization: str = ""
    sources: str = ""            # feeds / retailers / APIs to monitor
    platform: str = "discord"
    notes: str = ""
    # scout-d: optional per-project delivery target — the NAME of the env
    # var holding this bot's webhook (empty = fleet default). The scout
    # posts to #live-demo via DISCORD_DEMO_WEBHOOK_URL.
    webhook_env: str = ""
    status: str = "concept"      # concept | building | live | paused | retired
    created_at: str = ""
    modified_at: str = ""

    @property
    def kind_label(self) -> str:
        if self.kind == "other" and self.kind_other:
            return self.kind_other
        return dict(BOT_KINDS).get(self.kind, self.kind)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "BotProject":
        data = json.loads(text)
        known = {f for f in BotProject("x").as_dict()}
        return cls(**{k: v for k, v in data.items() if k in known})


def slugify(name: str) -> str:
    s = "".join(c if (c.isalnum() or c in "-_") else "-" for c in (name or "").lower())
    s = re.sub(r"-{2,}", "-", s).strip("-.")
    return s[:48] or "project"


def validate(p: BotProject) -> list[str]:
    errs: list[str] = []
    if not (p.project_name or "").strip():
        errs.append("project name is required")
    elif not _NAME_RE.match(p.project_name.strip()):
        errs.append("project name has invalid characters (letters/numbers/space/-/_ only)")
    if p.kind not in _KIND_KEYS:
        errs.append(f"kind {p.kind!r} not one of {sorted(_KIND_KEYS)}")
    if p.kind == "other" and not (p.kind_other or "").strip():
        errs.append("kind is 'other' — please name the kind in kind_other")
    return errs


def projects_dir(data_dir: Path) -> Path:
    p = Path(data_dir) / "bot_projects"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(data_dir: Path, project_name: str) -> Path:
    return projects_dir(data_dir) / f"{slugify(project_name)}.json"


def save(p: BotProject, data_dir: Path) -> Path:
    errs = validate(p)
    if errs:
        raise ValueError("bot project invalid:\n  - " + "\n  - ".join(errs))
    now = datetime.now(timezone.utc).isoformat()
    if not p.created_at:
        p.created_at = now
    p.modified_at = now
    path = _path(data_dir, p.project_name)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(p.to_json(), encoding="utf-8")
    with open(tmp, "r+", encoding="utf-8") as fh:
        fh.flush(); os.fsync(fh.fileno())
    tmp.replace(path)
    return path


def load(project_name: str, data_dir: Path) -> BotProject | None:
    path = _path(data_dir, project_name)
    if not path.is_file():
        return None
    try:
        return BotProject.from_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def list_all(data_dir: Path) -> list[BotProject]:
    out: list[BotProject] = []
    d = projects_dir(data_dir)
    for f in sorted(d.glob("*.json")):
        try:
            out.append(BotProject.from_json(f.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 — skip a corrupt file, never crash the list
            continue
    return out


def delete(project_name: str, data_dir: Path) -> bool:
    path = _path(data_dir, project_name)
    if not path.is_file():
        return False
    path.unlink()
    return True


# ── chat bridge: "what are we building?" ─────────────────────────────────
# NOTE: bare "our bots" removed — it greedily captured "how are our bots"
# (a bot-HEALTH question; caught by the collision matrix in
# tests/test_bridge_patterns.py). Keep these unambiguous about LISTING.
_BOTS_TRIGGERS = (
    "what bots", "what are we building", "our bot projects", "what bot projects",
    "what discord bots", "list our bots", "list the bots", "what are we making",
)


def is_bots_query(text: str) -> bool:
    if not text:
        return False
    from sovereign_agent.bridge_patterns import match_any
    return match_any(text, _BOTS_TRIGGERS)


def compose_bots_report(data_dir: Path | None = None) -> str:
    """Deterministic, grounded answer to 'what are we building?' — reads the
    real bot-project store so she shares the direction, never invents it."""
    if data_dir is None:
        try:
            from sovereign_agent.config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
        except Exception:  # noqa: BLE001
            return ("We haven't defined any bot projects yet. Open the Bot "
                    "Studio (/bots) to name our first one — the mature "
                    "first floor toward income.")
    try:
        projects = list_all(data_dir)
    except Exception:  # noqa: BLE001
        projects = []
    if not projects:
        return ("No bot projects defined yet — a clean slate. Open the Bot "
                "Studio (/bots) and we'll name our first project, pick its "
                "kind, and write the concept so we share where we're heading. "
                "Define before build; a stable floor for us first.")
    lines = [f"We're building {len(projects)} bot "
             f"project{'s' if len(projects) != 1 else ''}:"]
    for p in projects:
        bot = f" · bot: {p.bot_name}" if p.bot_name else ""
        desc = f" — {p.description}" if p.description else ""
        lines.append(f"  • [b]{p.project_name}[/b] ({p.kind_label}, {p.status}){bot}{desc}")
    lines.append("Open the Bot Studio (/bots) to add, edit, or refine any of these.")
    return "\n".join(lines)
