"""modes_crown/observatory.py — the watching window's data, gathered.
(FABLE II · M6 · modes-crown-d)

Kevin: *"make it an observability window so we can watch what modes she
goes into while in auto mode… watch her modes, and add her emotion
observability window also, and a stress and/or thinking observability."*

One mechanical gather — mode + lease, stance + transitions, emotion
surface (emotion.py's derive_emotions, already hers), and a stress/load
read built ONLY from signals that exist (queue depth, blocked ratio,
lease pressure, recent corrupt-line events). Honestly labeled: these are
mechanical proxies, not feelings. Watching, never steering.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

MARK = "modes-crown-d"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gather_stress(data_dir: Path | None = None) -> dict:
    """Mechanical load proxies. Each named, each sourced, none invented."""
    out = {
        "queue_depth": 0,          # pending subtasks across resumable sessions
        "blocked_ratio": 0.0,      # blocked / total subtasks (recent sessions)
        "lease_pressure": 0.0,     # 1 - remaining/total on the armed lease
        "corrupt_line_reads": 0,   # corrupt-lines-d events, today
    }
    try:
        from sovereign_agent.agent_session import SessionStore

        pending = blocked = total = 0
        for s in SessionStore().list_all()[:10]:
            for st in s.subtasks:
                total += 1
                if st.status == "pending":
                    pending += 1
                elif st.status == "blocked":
                    blocked += 1
        out["queue_depth"] = pending
        out["blocked_ratio"] = round(blocked / total, 3) if total else 0.0
    except Exception:  # noqa: BLE001
        pass
    try:
        from sovereign_agent import session_bridge
        from sovereign_agent.autonomy.session import time_remaining

        lease = session_bridge.active_lease()
        if lease is not None and lease.ttl_seconds:
            remaining = time_remaining(lease)
            out["lease_pressure"] = round(
                1.0 - (remaining / lease.ttl_seconds), 3)
    except Exception:  # noqa: BLE001
        pass
    try:
        from sovereign_agent.config import SETTINGS

        base = Path(data_dir) if data_dir is not None else SETTINGS.paths.data_dir
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        events_file = base / "events" / f"events-{today}.jsonl"
        if events_file.exists():
            out["corrupt_line_reads"] = sum(
                1 for line in events_file.read_text(
                    encoding="utf-8", errors="replace").splitlines()
                if '"corrupt-lines-d"' in line)
    except Exception:  # noqa: BLE001
        pass
    return out


def gather_observatory(data_dir: Path | None = None) -> dict:
    """Everything the watching window renders, in one honest dict."""
    from sovereign_agent.modes_crown.profiles import (
        current_profile, lease_remaining_seconds,
    )
    from sovereign_agent.modes_crown.stances import current_stance, recent_stances

    profile = current_profile(data_dir)
    out = {
        "at": _now(),
        "mode": profile.mode_id,
        "mode_title": profile.title,
        "mode_description": profile.description,
        "lease_remaining_s": lease_remaining_seconds(),
        "lease_seconds": profile.lease_seconds,
        "stance": current_stance(data_dir) or "(none declared)",
        "stance_history": recent_stances(8, data_dir),
        "stress": gather_stress(data_dir),
        "emotion": {},
        "emotion_mood": "",
    }
    try:
        from sovereign_agent.emotion import derive_emotions, emotion_to_mood

        state = derive_emotions()
        out["emotion"] = state.scores()
        out["emotion_mood"] = emotion_to_mood(state)
    except Exception:  # noqa: BLE001 — the window shows what it can
        pass
    return out


def render_observatory_text(data: dict) -> str:
    """Rich-markup render shared by the modal screen and `/observatory`."""
    lines = [
        f"[b]◈ mode[/b]  {data['mode']}  [dim]{data['mode_description']}[/dim]",
    ]
    if data.get("lease_seconds"):
        rem = int(data.get("lease_remaining_s", 0))
        lines.append(f"[b]⏱ lease[/b]  {rem // 60}m {rem % 60}s remaining "
                     f"of {data['lease_seconds'] // 60}m "
                     f"[dim](expiry refuses new goals — never self-extends)[/dim]")
    lines.append(f"[b]◇ stance[/b]  {data['stance']}")
    history = data.get("stance_history", [])
    if history:
        trail = " → ".join(h.get("stance") or "·" for h in history)
        lines.append(f"   [dim]trail: {trail}[/dim]")
    mood = data.get("emotion_mood")
    if data.get("emotion"):
        top = sorted(data["emotion"].items(), key=lambda kv: -kv[1])[:4]
        emo = "  ".join(f"{k} {v:.2f}" for k, v in top)
        lines.append(f"[b]♥ emotion[/b]  {mood or '?'}  [dim]{emo}[/dim]")
    s = data.get("stress", {})
    lines.append(
        f"[b]⚡ load[/b]  queue {s.get('queue_depth', 0)} · "
        f"blocked {s.get('blocked_ratio', 0.0):.0%} · "
        f"lease {s.get('lease_pressure', 0.0):.0%} · "
        f"corrupt-reads {s.get('corrupt_line_reads', 0)} "
        f"[dim](mechanical proxies, honestly labeled)[/dim]")
    return "\n".join(lines)
