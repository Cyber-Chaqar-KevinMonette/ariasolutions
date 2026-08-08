"""patcher.py — Integrity round I4: the "honest" stance.

Patches (pure in-place changes to already-live files — this module ships
no new payload files):
  1. modes_crown/stances.py — add "honest" to SAFE_STANCES, a real action
     on entry (_run_integrity_pass_for_stance), and integrity_gate_clear()
     mirroring quality/grounding/wellbeing's own *_gate_clear() exactly.
  2. session_bridge.py's _crown_gate() — a fifth block, same shape as the
     four already there.
  3. modes_crown/observatory.py — an `integrity` field beside
     quality/grounding/wellbeing.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "integrity-modes-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. modes_crown/stances.py ─────────────────────────────────────────────

STANCES_TUPLE_ANCHOR = '''    "reflecting",   # wellbeing-modes-d — a real wellbeing pass; gates new dispatch
                    # until it clears (the fourth stance with a real tooth)
)'''

STANCES_TUPLE_NEW = f'''    "reflecting",   # wellbeing-modes-d — a real wellbeing pass; gates new dispatch
                    # until it clears (the fourth stance with a real tooth)
    "honest",       # {MARK} — a real integrity pass; gates new dispatch
                    # until it clears (the fifth stance with a real tooth)
)'''

SET_STANCE_ANCHOR = '''    elif stance == "reflecting":  # wellbeing-modes-d — a real action, not just a label
        _run_wellbeing_pass_for_stance(data_dir)
    return rec'''

SET_STANCE_NEW = f'''    elif stance == "reflecting":  # wellbeing-modes-d — a real action, not just a label
        _run_wellbeing_pass_for_stance(data_dir)
    elif stance == "honest":  # {MARK} — a real action, not just a label
        _run_integrity_pass_for_stance(data_dir)
    return rec'''

# Appended at end of file — reuses _recent_text_for_stance (grounding-
# modes-d, generically "recent journal + QA text", not grounding-specific
# in what it fetches) rather than re-deriving the same on-demand sourcing.
STANCES_APPEND = f'''

def _run_integrity_pass_for_stance(data_dir: Path | None) -> None:  # {MARK}
    """Entering honest IS the action: run a real pass now, over whatever's
    currently there. Best-effort — a failure here degrades to an honest
    unclear pass (integrity_gate_clear() then correctly refuses until a
    real clean pass lands), never a crash on the stance change itself.

    Reuses `_recent_text_for_stance` (grounding-modes-d) rather than
    re-deriving the same on-demand journal+QA sourcing a third time."""
    try:
        from sovereign_agent.integrity import record_integrity_pass

        for source, text in _recent_text_for_stance(data_dir):
            record_integrity_pass(text, source=source, data_dir=data_dir)
    except Exception:  # noqa: BLE001
        pass


def integrity_gate_clear(data_dir: Path | None = None) -> bool:  # {MARK}
    """True iff an integrity pass completed CLEANLY since the current
    "honest" stance was entered — 'fresh' means literally recorded after
    activation (compared by timestamp), not just recent in wall-clock
    time. True (nothing to gate) when not in the stance at all."""
    state_path, _ = _paths(data_dir)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    if state.get("stance") != "honest":
        return True
    entered_at = state.get("at", "")
    try:
        from sovereign_agent.integrity import latest_integrity

        latest = latest_integrity(data_dir)
    except Exception:  # noqa: BLE001
        return False
    if latest is None:
        return False
    return bool(latest.get("ts", "") >= entered_at
               and latest.get("verdict", "fail") != "fail")
'''


def patch_stances(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, STANCES_TUPLE_ANCHOR, STANCES_TUPLE_NEW,
                         label="stances SAFE_STANCES tuple")
    text = _replace_once(text, SET_STANCE_ANCHOR, SET_STANCE_NEW,
                         label="stances set_stance branch")
    return text + STANCES_APPEND, True


# ── 2. session_bridge.py — a fifth _crown_gate block ──────────────────────

BRIDGE_ANCHOR = '''    try:  # wellbeing-modes-d — the fourth stance with a real tooth
        from sovereign_agent.modes_crown.stances import (
            current_stance as _current_stance_w, wellbeing_gate_clear,
        )

        if _current_stance_w() == "reflecting" and not wellbeing_gate_clear():
            raise PermissionError(
                "a wellbeing pass is running/failed — no new goals until it "
                "clears (set_stance to any working stance, or wait for the "
                "pass to pass)")
    except ImportError:  # noqa: BLE001 — wellbeing not applied → nothing to gate
        pass'''

BRIDGE_NEW = f'''    try:  # wellbeing-modes-d — the fourth stance with a real tooth
        from sovereign_agent.modes_crown.stances import (
            current_stance as _current_stance_w, wellbeing_gate_clear,
        )

        if _current_stance_w() == "reflecting" and not wellbeing_gate_clear():
            raise PermissionError(
                "a wellbeing pass is running/failed — no new goals until it "
                "clears (set_stance to any working stance, or wait for the "
                "pass to pass)")
    except ImportError:  # noqa: BLE001 — wellbeing not applied → nothing to gate
        pass
    try:  # {MARK} — the fifth stance with a real tooth
        from sovereign_agent.modes_crown.stances import (
            current_stance as _current_stance_i, integrity_gate_clear,
        )

        if _current_stance_i() == "honest" and not integrity_gate_clear():
            raise PermissionError(
                "an integrity pass is running/failed — no new goals until it "
                "clears (set_stance to any working stance, or wait for the "
                "pass to pass)")
    except ImportError:  # noqa: BLE001 — integrity not applied → nothing to gate
        pass'''


def patch_session_bridge(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, BRIDGE_ANCHOR, BRIDGE_NEW, label="session_bridge _crown_gate"), True


# ── 3. modes_crown/observatory.py — the `integrity` field ─────────────────

OBS_FETCH_ANCHOR = '''    try:  # wellbeing-modes-d
        from sovereign_agent.wellbeing import latest_wellbeing

        out["wellbeing"] = latest_wellbeing(data_dir)
    except Exception:  # noqa: BLE001
        out["wellbeing"] = None
    return out'''

OBS_FETCH_NEW = f'''    try:  # wellbeing-modes-d
        from sovereign_agent.wellbeing import latest_wellbeing

        out["wellbeing"] = latest_wellbeing(data_dir)
    except Exception:  # noqa: BLE001
        out["wellbeing"] = None
    try:  # {MARK}
        from sovereign_agent.integrity import latest_integrity

        out["integrity"] = latest_integrity(data_dir)
    except Exception:  # noqa: BLE001
        out["integrity"] = None
    return out'''

OBS_RENDER_ANCHOR = '''    w = data.get("wellbeing")  # wellbeing-modes-d
    if w:
        lines.append(
            f"[b]♡ wellbeing[/b]  {w.get('verdict', '?')} "
            f"(grade {w.get('love_grade', '?')})"
            + (" · zombie signal" if w.get("impact_is_zombie") else ""))
    return "\\n".join(lines)'''

OBS_RENDER_NEW = f'''    w = data.get("wellbeing")  # wellbeing-modes-d
    if w:
        lines.append(
            f"[b]♡ wellbeing[/b]  {{w.get('verdict', '?')}} "
            f"(grade {{w.get('love_grade', '?')}})"
            + (" · zombie signal" if w.get("impact_is_zombie") else ""))
    i = data.get("integrity")  # {MARK}
    if i:
        lines.append(
            f"[b]◈ integrity[/b]  {{i.get('verdict', '?')}} "
            f"({{i.get('value', 0.0):.2f}})")
    return "\\n".join(lines)'''


def patch_observatory(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, OBS_FETCH_ANCHOR, OBS_FETCH_NEW, label="observatory fetch")
    text = _replace_once(text, OBS_RENDER_ANCHOR, OBS_RENDER_NEW, label="observatory render")
    return text, True


ALL_PATCHES = {
    "modes_crown/stances.py": patch_stances,
    "session_bridge.py": patch_session_bridge,
    "modes_crown/observatory.py": patch_observatory,
}
