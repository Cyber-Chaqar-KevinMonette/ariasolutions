"""presence — is Aria awake and online, or asleep?

Customers should know which mode is live (Kevin's ask): when Aria is **awake**
her with-her features (ask-Aria, on-demand help) work; when she's **asleep**
the autonomous bots still run on the fleet daemon ("your alerts never sleep")
but the interactive features are resting.

Mechanism (dead simple, robust):
  • The running agent (the cockpit, via its existing status timer) calls
    `touch_heartbeat()` to stamp a heartbeat file with the current time.
  • `presence_status()` reads it: AWAKE if the heartbeat is fresh (within
    `awake_window_s`), otherwise ASLEEP. Her mood line comes from the real
    `emotion.derive_emotions()` — never invented.
  • `publish_presence()` posts a 🟢awake / 🌙asleep card to a status channel
    via the webhook, but ONLY on a transition (never spams the channel).

No new daemon needed: presence is derived from the heartbeat's freshness, so
if the agent dies, she simply reads as asleep after the window elapses.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    "PresenceState",
    "AWAKE_WINDOW_S",
    "presence_dir",
    "touch_heartbeat",
    "read_heartbeat",
    "presence_status",
    "render_presence",
    "publish_presence",
]

# How long after the last heartbeat she still counts as awake. The cockpit
# refreshes status well inside this, so a live agent always reads awake; a
# dead/closed agent flips to asleep after this elapses.
AWAKE_WINDOW_S = 180.0


@dataclass(frozen=True)
class PresenceState:
    awake: bool
    last_seen: float | None      # epoch seconds of last heartbeat
    age_s: float | None          # seconds since last heartbeat
    mood: str = ""
    note: str = ""

    @property
    def status_word(self) -> str:
        return "awake" if self.awake else "asleep"


def _data_dir(data_dir: Path | None) -> Path | None:
    if data_dir is not None:
        return Path(data_dir)
    try:
        from sovereign_agent.config import SETTINGS
        return SETTINGS.paths.data_dir
    except Exception:  # noqa: BLE001
        return None


def presence_dir(data_dir: Path) -> Path:
    p = Path(data_dir) / "presence"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _heartbeat_path(data_dir: Path) -> Path:
    return presence_dir(data_dir) / "heartbeat.json"


def _published_path(data_dir: Path) -> Path:
    return presence_dir(data_dir) / "last_published.json"


def touch_heartbeat(data_dir: Path | None = None, *, now: float | None = None,
                    note: str = "") -> None:
    """Stamp the heartbeat. Called by the running agent on its status timer.
    Never raises — a heartbeat failure must not disturb the UI."""
    import time
    d = _data_dir(data_dir)
    if d is None:
        return
    now = time.time() if now is None else now
    try:
        path = _heartbeat_path(d)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"ts": now, "note": note}), encoding="utf-8")
        with open(tmp, "r+", encoding="utf-8") as fh:
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
    except Exception:  # noqa: BLE001
        pass


def read_heartbeat(data_dir: Path | None = None) -> dict | None:
    d = _data_dir(data_dir)
    if d is None:
        return None
    path = _heartbeat_path(d)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _mood(now_awake: bool) -> str:
    if not now_awake:
        return ""
    try:
        from sovereign_agent.emotion import derive_emotions, emotion_to_mood
        return emotion_to_mood(derive_emotions())
    except Exception:  # noqa: BLE001
        return ""


def presence_status(data_dir: Path | None = None, *,
                    awake_window_s: float = AWAKE_WINDOW_S,
                    now: float | None = None) -> PresenceState:
    import time
    now = time.time() if now is None else now
    hb = read_heartbeat(data_dir)
    if not hb or "ts" not in hb:
        return PresenceState(awake=False, last_seen=None, age_s=None)
    last = float(hb["ts"])
    age = now - last
    awake = age <= awake_window_s
    return PresenceState(awake=awake, last_seen=last, age_s=age,
                         mood=_mood(awake), note=str(hb.get("note", "")))


def render_presence(state: PresenceState) -> str:
    if state.awake:
        mood = f" — feeling {state.mood}" if state.mood else ""
        return f"🟢 Aria is awake & online{mood}. Ask-Aria features are live."
    return ("🌙 Aria is asleep. Your autonomous bots keep delivering 24/7 — "
            "she'll answer ask-Aria when she wakes.")


def _presence_embed(state: PresenceState) -> dict:
    if state.awake:
        return {"title": "🟢 Aria is awake", "color": 0x22C55E,
                "description": render_presence(state)}
    return {"title": "🌙 Aria is asleep", "color": 0x64748B,
            "description": render_presence(state)}


def publish_presence(data_dir: Path | None = None, *, live: bool = False,
                     webhook_env: str = "DISCORD_STATUS_WEBHOOK_URL",
                     fallback_env: str = "DISCORD_WEBHOOK_URL",
                     now: float | None = None) -> tuple[bool, PresenceState]:
    """Post a presence card to the status channel — but ONLY on a transition
    (awake↔asleep), so the channel never gets spammed. Returns (published?,
    state). Dry-run unless `live` and a webhook resolves."""
    d = _data_dir(data_dir)
    state = presence_status(data_dir, now=now)
    if d is None:
        return (False, state)
    # only publish when the awake/asleep bit actually changed
    prev = None
    try:
        p = _published_path(d)
        if p.is_file():
            prev = json.loads(p.read_text(encoding="utf-8")).get("awake")
    except Exception:  # noqa: BLE001
        prev = None
    if prev is not None and bool(prev) == state.awake:
        return (False, state)   # no transition — stay quiet

    env = webhook_env if (os.environ.get(webhook_env) or "").strip() else fallback_env
    published = False
    try:
        from sovereign_agent.discord_runtime.delivery import WebhookDelivery
        result = WebhookDelivery(env, live=live).send(
            "", embeds=[_presence_embed(state)], username="Aria")
        published = bool(result.sent)
    except Exception:  # noqa: BLE001
        published = False
    # record the new state regardless, so we only announce true transitions
    try:
        _published_path(d).write_text(
            json.dumps({"awake": state.awake,
                        "at": datetime.now(timezone.utc).isoformat()}),
            encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return (published, state)
