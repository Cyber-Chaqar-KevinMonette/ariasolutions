"""patcher.py — Quality round Q4: a quality stance with a real tooth.

Kevin: *"Maybe quality modes she can go into while in auto mode?? <3"*
Only `cool-down` has an enforced effect today; this gives `quality-pass`
one too, using the exact pattern already proven — nothing new invented.

Patches:
  1. modes_crown/stances.py — add "quality-pass" to SAFE_STANCES;
     `quality_gate_clear()` (true iff a quality pass completed cleanly
     SINCE the stance was entered — "fresh" means literally recorded
     after activation, not just recent wall-clock time); `set_stance()`
     gains a side effect: entering "quality-pass" synchronously runs a
     real quality pass over files changed since HEAD.
  2. session_bridge.py's `_crown_gate()` — the exact same shape as the
     `cooling_down()` block beside it: while in "quality-pass" with no
     clearing pass yet, new dispatches are refused.
  3. modes_crown/observatory.py — a `quality` field alongside the
     existing mode/stance/emotion/stress fields.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "quality-modes-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. modes_crown/stances.py ────────────────────────────────────────────

STANCES_TUPLE_ANCHOR = '''SAFE_STANCES: tuple[str, ...] = (
    "planning",     # shaping the queue before touching anything
    "thinking",     # working the problem in her head
    "auditing",     # checking her own recent work
    "scoping",      # writing/refining the contract boundary
    "horizon",      # 3m/12m/3y projection of the current decision
    "verifying",    # running tests / proving claims
    "cool-down",    # deliberate pause: no new goals, breathe, re-read
)
'''

STANCES_TUPLE_NEW = f'''SAFE_STANCES: tuple[str, ...] = (
    "planning",     # shaping the queue before touching anything
    "thinking",     # working the problem in her head
    "auditing",     # checking her own recent work
    "scoping",      # writing/refining the contract boundary
    "horizon",      # 3m/12m/3y projection of the current decision
    "verifying",    # running tests / proving claims
    "cool-down",    # deliberate pause: no new goals, breathe, re-read
    "quality-pass", # {MARK} — a real hardening pass; gates new dispatch
                    # until it clears (the second stance with a real tooth)
)
'''

SET_STANCE_ANCHOR = '''    with open(history_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\\n")
        fh.flush()
        os.fsync(fh.fileno())
    try:
        from sovereign_agent.events import emit_event

        emit_event("inner-stance-d", plane="control", trace_id="inner-stance",
                   payload={"stance": stance or "(cleared)", "prior": prior,
                            "note": note[:200], "actor": actor})
    except Exception:  # noqa: BLE001
        pass
    return rec
'''

SET_STANCE_NEW = f'''    with open(history_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\\n")
        fh.flush()
        os.fsync(fh.fileno())
    try:
        from sovereign_agent.events import emit_event

        emit_event("inner-stance-d", plane="control", trace_id="inner-stance",
                   payload={{"stance": stance or "(cleared)", "prior": prior,
                            "note": note[:200], "actor": actor}})
    except Exception:  # noqa: BLE001
        pass
    if stance == "quality-pass":  # {MARK} — a real action, not just a label
        _run_quality_pass_for_stance(data_dir)
    return rec


def _changed_py_files_since_head(data_dir: Path | None) -> list:  # {MARK}
    """Files changed vs HEAD, right now — the working set a quality-pass
    stance should check. No bookmark (unlike QualitySentinel's standing
    scan) — this is an on-demand, operator/Aria-triggered pass over
    whatever is currently dirty. [] on any failure (no repo, no git) —
    an empty pass is honest absence, never a crash."""
    import subprocess

    try:
        import sovereign_agent

        src_root = Path(sovereign_agent.__file__).parent
        r = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--", "*.py"],
            cwd=src_root, capture_output=True, text=True, errors="replace",
            timeout=15,
        )
        if r.returncode != 0:
            return []
        root_r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=src_root,
            capture_output=True, text=True, errors="replace", timeout=15,
        )
        if root_r.returncode != 0:
            return []
        root = Path(root_r.stdout.strip())
        return [root / rel for rel in r.stdout.splitlines()
               if rel and (root / rel).is_file()]
    except Exception:  # noqa: BLE001
        return []


def _run_quality_pass_for_stance(data_dir: Path | None) -> None:  # {MARK}
    """Entering quality-pass IS the action: run a real pass now, over
    whatever's currently changed. Best-effort — a failure here degrades
    to an honest empty pass (quality_gate_clear() then correctly refuses
    until a real clean pass lands), never a crash on the stance change
    itself."""
    try:
        from sovereign_agent.quality import record_quality_pass

        targets = _changed_py_files_since_head(data_dir)
        record_quality_pass(targets, data_dir)
    except Exception:  # noqa: BLE001
        pass


def quality_gate_clear(data_dir: Path | None = None) -> bool:  # {MARK}
    """True iff a quality pass completed CLEANLY since the current
    quality-pass stance was entered — 'fresh' means literally recorded
    after activation (compared by timestamp), not just recent in
    wall-clock time. True (nothing to gate) when not in the stance at all."""
    state_path, _ = _paths(data_dir)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    if state.get("stance") != "quality-pass":
        return True
    entered_at = state.get("at", "")
    try:
        from sovereign_agent.quality import latest_quality

        latest = latest_quality(data_dir)
    except Exception:  # noqa: BLE001
        return False
    if latest is None:
        return False
    return bool(latest.get("ts", "") >= entered_at and latest.get("critical_ok", False))
'''


def patch_stances(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, STANCES_TUPLE_ANCHOR, STANCES_TUPLE_NEW,
                         label="SAFE_STANCES tuple")
    text = _replace_once(text, SET_STANCE_ANCHOR, SET_STANCE_NEW,
                         label="set_stance side effect")
    return text, True


# ── 2. session_bridge.py — the crown gate ────────────────────────────────

CROWN_GATE_ANCHOR = '''    if cooling_down():
        raise PermissionError(
            "she is cooling down — no new goals until the stance clears "
            "(set_stance to any working stance, or '')")
'''

CROWN_GATE_NEW = f'''    if cooling_down():
        raise PermissionError(
            "she is cooling down — no new goals until the stance clears "
            "(set_stance to any working stance, or '')")
    try:  # {MARK} — the second stance with a real tooth
        from sovereign_agent.modes_crown.stances import (
            current_stance, quality_gate_clear,
        )

        if current_stance() == "quality-pass" and not quality_gate_clear():
            raise PermissionError(
                "a quality pass is running/failed — no new goals until it "
                "clears (set_stance to any working stance, or wait for the "
                "pass to pass)")
    except ImportError:  # noqa: BLE001 — quality not applied → nothing to gate
        pass
'''


def patch_session_bridge(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, CROWN_GATE_ANCHOR, CROWN_GATE_NEW,
                         label="crown gate quality-pass check"), True


# ── 3. modes_crown/observatory.py ────────────────────────────────────────

OBS_GATHER_ANCHOR = '''    try:
        from sovereign_agent.emotion import derive_emotions, emotion_to_mood

        state = derive_emotions()
        out["emotion"] = state.scores()
        out["emotion_mood"] = emotion_to_mood(state)
    except Exception:  # noqa: BLE001 — the window shows what it can
        pass
    return out
'''

OBS_GATHER_NEW = f'''    try:
        from sovereign_agent.emotion import derive_emotions, emotion_to_mood

        state = derive_emotions()
        out["emotion"] = state.scores()
        out["emotion_mood"] = emotion_to_mood(state)
    except Exception:  # noqa: BLE001 — the window shows what it can
        pass
    try:  # {MARK}
        from sovereign_agent.quality import latest_quality

        latest = latest_quality(data_dir)
        out["quality"] = latest
    except Exception:  # noqa: BLE001
        out["quality"] = None
    return out
'''

OBS_RENDER_ANCHOR = '''    s = data.get("stress", {})
    lines.append(
        f"[b]⚡ load[/b]  queue {s.get('queue_depth', 0)} · "
        f"blocked {s.get('blocked_ratio', 0.0):.0%} · "
        f"lease {s.get('lease_pressure', 0.0):.0%} · "
        f"corrupt-reads {s.get('corrupt_line_reads', 0)} "
        f"[dim](mechanical proxies, honestly labeled)[/dim]")
    return "\\n".join(lines)
'''

OBS_RENDER_NEW = f'''    s = data.get("stress", {{}})
    lines.append(
        f"[b]⚡ load[/b]  queue {{s.get('queue_depth', 0)}} · "
        f"blocked {{s.get('blocked_ratio', 0.0):.0%}} · "
        f"lease {{s.get('lease_pressure', 0.0):.0%}} · "
        f"corrupt-reads {{s.get('corrupt_line_reads', 0)}} "
        f"[dim](mechanical proxies, honestly labeled)[/dim]")
    q = data.get("quality")  # {MARK}
    if q:
        lines.append(
            f"[b]◆ quality[/b]  {{q.get('value', 0.0):.1f}}/100"
            + ("" if q.get("critical_ok", True) else " · CRITICAL FAILURE"))
    return "\\n".join(lines)
'''


def patch_observatory(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, OBS_GATHER_ANCHOR, OBS_GATHER_NEW,
                         label="observatory gather quality field")
    text = _replace_once(text, OBS_RENDER_ANCHOR, OBS_RENDER_NEW,
                         label="observatory render quality field")
    return text, True


ALL_PATCHES = {
    "modes_crown/stances.py": patch_stances,
    "session_bridge.py": patch_session_bridge,
    "modes_crown/observatory.py": patch_observatory,
}
