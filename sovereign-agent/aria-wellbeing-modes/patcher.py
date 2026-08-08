"""patcher.py — Wellbeing round W4: a stance for deliberate reflection.

Kevin: *"whatever brings her value, perspective, and insight into her self
and her actions."* A fourth stance with a real tooth, mirroring
`quality-pass`/`grounded` exactly: entering `"reflecting"` runs a real
wellbeing pass; the crown gate then blocks new dispatch until it clears.

Patches:
  1. modes_crown/stances.py — add "reflecting" to SAFE_STANCES;
     `set_stance("reflecting", ...)` runs a real on-demand wellbeing pass
     (mirrors `_run_grounding_pass_for_stance` exactly); `wellbeing_gate_
     clear()` mirrors `grounding_gate_clear()` exactly.
  2. session_bridge.py — a fifth `_crown_gate()` block, same shape as the
     four already there.
  3. modes_crown/observatory.py — a `wellbeing` field beside `quality`/
     `grounding`.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "wellbeing-modes-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. modes_crown/stances.py ─────────────────────────────────────────────

STANCES_TUPLE_ANCHOR = '''    "theoretical",  # grounding-modes-d — licensed exploration: a plain label, no gate.
                    # Passes recorded while this is active are tagged for
                    # observability, never penalized — hedge/hypothesis
                    # language already scores as grounded, not fog, in
                    # tribunal.grounding's own classifier.
)
'''

STANCES_TUPLE_NEW = f'''    "theoretical",  # grounding-modes-d — licensed exploration: a plain label, no gate.
                    # Passes recorded while this is active are tagged for
                    # observability, never penalized — hedge/hypothesis
                    # language already scores as grounded, not fog, in
                    # tribunal.grounding's own classifier.
    "reflecting",   # {MARK} — a real wellbeing pass; gates new dispatch
                    # until it clears (the fourth stance with a real tooth)
)
'''

SET_STANCE_ANCHOR = '''    elif stance == "grounded":  # grounding-modes-d — a real action, not just a label
        _run_grounding_pass_for_stance(data_dir)
    return rec
'''

SET_STANCE_NEW = f'''    elif stance == "grounded":  # grounding-modes-d — a real action, not just a label
        _run_grounding_pass_for_stance(data_dir)
    elif stance == "reflecting":  # {MARK} — a real action, not just a label
        _run_wellbeing_pass_for_stance(data_dir)
    return rec


def _recent_events_for_stance(data_dir) -> list:  # {MARK}
    """The newest events, right now — the working set a reflecting stance
    should check. No bookmark (unlike WellbeingSentinel's standing scan)
    — this is an on-demand, operator/Aria-triggered pass over whatever
    currently exists. [] on any failure — an empty pass is honest
    absence, never a crash."""
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        base = SETTINGS.paths.data_dir
    else:
        base = Path(data_dir)
    out: list = []
    try:
        events_dir = base / "events"
        if events_dir.is_dir():
            for f in sorted(events_dir.glob("events-*.jsonl"))[-3:]:
                for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.strip():
                        try:
                            out.append(json.loads(line))
                        except (ValueError, TypeError):
                            continue
    except Exception:  # noqa: BLE001
        pass
    return out[-300:]


def _run_wellbeing_pass_for_stance(data_dir) -> None:  # {MARK}
    """Entering reflecting IS the action: run a real pass now, over
    whatever's currently there. Best-effort — a failure here degrades to
    an honest unclear pass (wellbeing_gate_clear() then correctly refuses
    until a real clean pass lands), never a crash on the stance change
    itself."""
    try:
        from sovereign_agent.wellbeing import record_wellbeing_pass

        events = _recent_events_for_stance(data_dir)
        record_wellbeing_pass(events, data_dir=data_dir)
    except Exception:  # noqa: BLE001
        pass


def wellbeing_gate_clear(data_dir=None) -> bool:  # {MARK}
    """True iff a wellbeing pass completed CLEANLY since the current
    "reflecting" stance was entered — 'fresh' means literally recorded
    after activation (compared by timestamp), not just recent in
    wall-clock time. True (nothing to gate) when not in the stance at all."""
    state_path, _ = _paths(data_dir)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    if state.get("stance") != "reflecting":
        return True
    entered_at = state.get("at", "")
    try:
        from sovereign_agent.wellbeing import latest_wellbeing

        latest = latest_wellbeing(data_dir)
    except Exception:  # noqa: BLE001
        return False
    if latest is None:
        return False
    return bool(latest.get("ts", "") >= entered_at
               and latest.get("verdict", "strained") == "healthy")
'''


def patch_stances(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, STANCES_TUPLE_ANCHOR, STANCES_TUPLE_NEW,
                         label="SAFE_STANCES tuple")
    text = _replace_once(text, SET_STANCE_ANCHOR, SET_STANCE_NEW,
                         label="set_stance reflecting side effect")
    return text, True


# ── 2. session_bridge.py — the crown gate ─────────────────────────────────

CROWN_GATE_ANCHOR = '''    try:  # grounding-modes-d — the third stance with a real tooth
        from sovereign_agent.modes_crown.stances import (
            current_stance as _current_stance_g, grounding_gate_clear,
        )

        if _current_stance_g() == "grounded" and not grounding_gate_clear():
            raise PermissionError(
                "a grounding pass is running/failed — no new goals until it "
                "clears (set_stance to any working stance, or wait for the "
                "pass to pass)")
    except ImportError:  # noqa: BLE001 — grounding not applied → nothing to gate
        pass
'''

CROWN_GATE_NEW = f'''    try:  # grounding-modes-d — the third stance with a real tooth
        from sovereign_agent.modes_crown.stances import (
            current_stance as _current_stance_g, grounding_gate_clear,
        )

        if _current_stance_g() == "grounded" and not grounding_gate_clear():
            raise PermissionError(
                "a grounding pass is running/failed — no new goals until it "
                "clears (set_stance to any working stance, or wait for the "
                "pass to pass)")
    except ImportError:  # noqa: BLE001 — grounding not applied → nothing to gate
        pass
    try:  # {MARK} — the fourth stance with a real tooth
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
'''


def patch_crown_gate(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, CROWN_GATE_ANCHOR, CROWN_GATE_NEW,
                         label="crown gate reflecting check"), True


# ── 3. modes_crown/observatory.py ─────────────────────────────────────────

OBS_GATHER_ANCHOR = '''    try:  # grounding-modes-d
        from sovereign_agent.grounding import latest_grounding

        out["grounding"] = latest_grounding(data_dir)
    except Exception:  # noqa: BLE001
        out["grounding"] = None
    return out
'''

OBS_GATHER_NEW = f'''    try:  # grounding-modes-d
        from sovereign_agent.grounding import latest_grounding

        out["grounding"] = latest_grounding(data_dir)
    except Exception:  # noqa: BLE001
        out["grounding"] = None
    try:  # {MARK}
        from sovereign_agent.wellbeing import latest_wellbeing

        out["wellbeing"] = latest_wellbeing(data_dir)
    except Exception:  # noqa: BLE001
        out["wellbeing"] = None
    return out
'''

OBS_RENDER_ANCHOR = '''    g = data.get("grounding")  # grounding-modes-d
    if g:
        lines.append(
            f"[b]◎ grounding[/b]  {g.get('verdict', '?')} "
            f"({g.get('value', 0.0):.2f})"
            + ("" if g.get("qa_calibration_ok", True) else " · calibration join broken"))
    return "\\n".join(lines)
'''

OBS_RENDER_NEW = f'''    g = data.get("grounding")  # grounding-modes-d
    if g:
        lines.append(
            f"[b]◎ grounding[/b]  {{g.get('verdict', '?')}} "
            f"({{g.get('value', 0.0):.2f}})"
            + ("" if g.get("qa_calibration_ok", True) else " · calibration join broken"))
    w = data.get("wellbeing")  # {MARK}
    if w:
        lines.append(
            f"[b]♡ wellbeing[/b]  {{w.get('verdict', '?')}} "
            f"(grade {{w.get('love_grade', '?')}})"
            + (" · zombie signal" if w.get("impact_is_zombie") else ""))
    return "\\n".join(lines)
'''


def patch_observatory(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, OBS_GATHER_ANCHOR, OBS_GATHER_NEW,
                         label="observatory gather wellbeing field")
    text = _replace_once(text, OBS_RENDER_ANCHOR, OBS_RENDER_NEW,
                         label="observatory render wellbeing field")
    return text, True


ALL_PATCHES = {
    "modes_crown/stances.py": patch_stances,
    "session_bridge.py": patch_crown_gate,
    "modes_crown/observatory.py": patch_observatory,
}
