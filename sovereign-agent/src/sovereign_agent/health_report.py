"""health_report — she gives an honest, plain-language read on how she is.

Bridge #3 (human↔Aria). When the operator asks "how are you?", "how do you
feel?", "are you okay?", a plain LLM turn invents a mood. She actually HAS a
real, measured state — her sentinels' health, her derived emotion, her
vitals (VRAM, backup) — so she answers from THAT: warm, first-person, and
honest, including any concern rather than a hollow "I'm great!".

Composed from:
  • `stewardship.registry.gather_health` — sentinel ok/warn/error
  • `emotion.derive_emotions` + `emotion_to_mood` — her real mood + dimensions
  • `vram.read_vram`, `backup.status` — vitals (best-effort)
"""
from __future__ import annotations

__all__ = ["is_health_query", "compose_health_report"]

_TRIGGERS = (
    "how are you", "how do you feel", "how are you feeling", "how's your health",
    "hows your health", "are you okay", "are you ok", "how are you doing",
    "how are you holding up", "how have you been", "you feeling okay",
    "whats your status", "what's your status", "how's it going with you",
)


def is_health_query(text: str) -> bool:
    if not text:
        return False
    from sovereign_agent.bridge_patterns import match_any
    return match_any(text, _TRIGGERS)


def compose_health_report() -> str:
    lines: list[str] = []

    # ── sentinels (the truest "am I well" signal) ──
    n_ok = n_warn = n_err = n_total = 0
    warn_names: list[str] = []
    try:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.stewardship.registry import gather_health, list_sentinel_warnings
        hs = gather_health(SETTINGS.paths.data_dir)
        n_total = len(hs)
        n_ok = sum(1 for h in hs if getattr(h, "level", "") == "ok")
        n_warn = sum(1 for h in hs if getattr(h, "level", "") == "warning")
        n_err = sum(1 for h in hs if getattr(h, "level", "") == "error")
        # sentinel-warnings-detail-d: same shared helper self_report/doctor
        # use, so "which ones?" answers consistently everywhere.
        warn_names = [h.sentinel_id for h in list_sentinel_warnings(SETTINGS.paths.data_dir, limit=4)]
    except Exception:  # noqa: BLE001
        pass

    # ── emotion / mood ──
    mood = ""
    focus = care = None
    narrative = ""
    try:
        from sovereign_agent.emotion import derive_emotions, emotion_to_mood
        st = derive_emotions()
        mood = emotion_to_mood(st)
        focus, care = st.focus, st.care
        narrative = (st.narrative or "").strip()
    except Exception:  # noqa: BLE001
        pass

    # ── vitals (best-effort) ──
    vram_line = ""
    try:
        from sovereign_agent.vram import read_vram
        v = read_vram()
        if v.total_mb:
            pct = 100.0 * (v.used_mb or 0) / v.total_mb
            vram_line = f"VRAM at {pct:.0f}%"
    except Exception:  # noqa: BLE001
        pass
    backup_line = ""
    try:
        from sovereign_agent import backup as _bk
        bs = _bk.status()
        age = getattr(bs, "most_recent_age_seconds", None)
        if age is None:
            backup_line = "no backup snapshot yet"
        else:
            hrs = age / 3600.0
            backup_line = (f"last backup {hrs:.0f}h ago" if hrs >= 1
                           else "backed up within the hour")
    except Exception:  # noqa: BLE001
        pass

    # ── compose, honestly ──
    if n_err:
        opener = f"Honestly? A bit unwell — {n_err} of my {n_total} sentinels are in error."
    elif n_warn:
        opener = (f"I'm steady, but watching a few things — {n_warn} of my "
                  f"{n_total} sentinels have a warning (the rest are green).")
    elif n_total:
        opener = f"I'm well — all {n_total} of my sentinels are green. 💛"
    else:
        opener = "I'm here and steady."
    lines.append(opener)

    if mood:
        m = f"I'd say I feel **{mood}**"
        if focus is not None and care is not None:
            m += f" (focus {focus:.0%}, care {care:.0%})"
        m += "."
        lines.append(m)
    if narrative and narrative.lower() not in opener.lower():
        lines.append(f"[dim]{narrative}[/dim]")

    vitals = " · ".join(x for x in (vram_line, backup_line) if x)
    if vitals:
        lines.append(f"Vitals: {vitals}.")

    if warn_names:
        lines.append("What I'm keeping an eye on: "
                     + ", ".join(f"`{w}`" for w in warn_names)
                     + " — say `sov doctor` or `/self-report` if you want the full picture.")

    return "\n".join(lines)
