"""modes_crown/stances.py — her own inner stances, observable.
(FABLE II · M6 · modes-crown-d)

Kevin: *"when we put Aria in Auto mode she has her own safe modes she can
switch between — planning, auditing, scoping, horizon… give her a break
or cool down mode if she needs one, thinking modes, audit modes."*

An inner STANCE is not a mode: it never touches authority, leases, or the
operator's mode — it is a declared working posture, Tier-0 by
construction. She may change it freely (the SetStanceTool is T0); every
change is an `inner-stance-d` event and an append-only history line, so
the observatory window can show where her attention lives.

The one stance with a tooth: **cool-down** — a deliberate pause posture.
While she is cooling down, the bridge refuses NEW goal dispatches (the
running one finishes; nothing is interrupted). Stepping out of cool-down
is as free as stepping in.

Kill switch: SOV_NO_STANCES=1 (stance writes become no-ops).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

MARK = "modes-crown-d"
KILL_SWITCH_ENV = "SOV_NO_STANCES"

SAFE_STANCES: tuple[str, ...] = (
    "planning",     # shaping the queue before touching anything
    "thinking",     # working the problem in her head
    "auditing",     # checking her own recent work
    "scoping",      # writing/refining the contract boundary
    "horizon",      # 3m/12m/3y projection of the current decision
    "verifying",    # running tests / proving claims
    "cool-down",    # deliberate pause: no new goals, breathe, re-read
    "quality-pass", # quality-modes-d — a real hardening pass; gates new dispatch
                    # until it clears (the second stance with a real tooth)
    "grounded",     # grounding-modes-d — a real grounding pass; gates new dispatch until
                    # it clears (the third stance with a real tooth)
    "theoretical",  # grounding-modes-d — licensed exploration: a plain label, no gate.
                    # Passes recorded while this is active are tagged for
                    # observability, never penalized — hedge/hypothesis
                    # language already scores as grounded, not fog, in
                    # tribunal.grounding's own classifier.
    "reflecting",   # wellbeing-modes-d — a real wellbeing pass; gates new dispatch
                    # until it clears (the fourth stance with a real tooth)
    "honest",       # integrity-modes-d — a real integrity pass; gates new dispatch
                    # until it clears (the fifth stance with a real tooth)
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _paths(data_dir: Path | None = None) -> tuple[Path, Path]:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    base = Path(data_dir)
    return base / "inner_stance.json", base / "inner_stances.ndjson"


def current_stance(data_dir: Path | None = None) -> str:
    """The active stance ('' when none declared). Never raises."""
    try:
        state_path, _ = _paths(data_dir)
        if not state_path.exists():
            return ""
        return str(json.loads(state_path.read_text(encoding="utf-8"))
                   .get("stance", ""))
    except Exception:  # noqa: BLE001
        return ""


def set_stance(stance: str, *, note: str = "", actor: str = "aria",
               data_dir: Path | None = None) -> dict:
    """Declare a stance (or '' to clear). Only SAFE stances exist — there
    is nothing else to set. Returns the history record."""
    stance = (stance or "").strip().lower()
    if stance and stance not in SAFE_STANCES:
        raise ValueError(f"unknown stance {stance!r} — one of {SAFE_STANCES}")
    if os.environ.get(KILL_SWITCH_ENV):
        return {"stance": stance, "skipped": "kill-switched"}
    state_path, history_path = _paths(data_dir)
    prior = current_stance(data_dir)
    rec = {"stance": stance, "prior": prior, "note": note[:200],
           "actor": actor[:40], "at": _now()}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    os.replace(tmp, state_path)
    with open(history_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    try:
        from sovereign_agent.events import emit_event

        emit_event("inner-stance-d", plane="control", trace_id="inner-stance",
                   payload={"stance": stance or "(cleared)", "prior": prior,
                            "note": note[:200], "actor": actor})
    except Exception:  # noqa: BLE001
        pass
    if stance == "quality-pass":  # quality-modes-d — a real action, not just a label
        _run_quality_pass_for_stance(data_dir)
    elif stance == "grounded":  # grounding-modes-d — a real action, not just a label
        _run_grounding_pass_for_stance(data_dir)
    elif stance == "reflecting":  # wellbeing-modes-d — a real action, not just a label
        _run_wellbeing_pass_for_stance(data_dir)
    elif stance == "honest":  # integrity-modes-d — a real action, not just a label
        _run_integrity_pass_for_stance(data_dir)
    return rec


def _recent_events_for_stance(data_dir) -> list:  # wellbeing-modes-d
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


def _run_wellbeing_pass_for_stance(data_dir) -> None:  # wellbeing-modes-d
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


def wellbeing_gate_clear(data_dir=None) -> bool:  # wellbeing-modes-d
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


def _recent_text_for_stance(data_dir: Path | None) -> list:  # grounding-modes-d
    """The newest few journal entries + QA answers, right now — the
    working set a grounded stance should check. No bookmark (unlike
    GroundingSentinel's standing scan) — this is an on-demand,
    operator/Aria-triggered pass over whatever currently exists. [] on any
    failure — an empty pass is honest absence, never a crash."""
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        base = SETTINGS.paths.data_dir
    else:
        base = Path(data_dir)
    out: list = []
    try:
        journal_dir = base / "journal"
        if journal_dir.is_dir():
            files = sorted(journal_dir.glob("*.md"),
                           key=lambda p: p.stat().st_mtime, reverse=True)[:3]
            for f in files:
                out.append((f"journal:{f.stem}",
                           f.read_text(encoding="utf-8", errors="replace")))
    except Exception:  # noqa: BLE001
        pass
    try:
        from sovereign_agent.read_repair import read_ndjson_tolerant

        records = read_ndjson_tolerant(base / "qa" / "qa.ndjson", store="qa",
                                       emit=False).records[-5:]
        for r in records:
            if r.get("answer"):
                out.append((f"qa:{r.get('qa_id', '?')}", str(r.get("answer", ""))))
    except Exception:  # noqa: BLE001
        pass
    return out


def _run_grounding_pass_for_stance(data_dir: Path | None) -> None:  # grounding-modes-d
    """Entering grounded IS the action: run a real pass now, over
    whatever's currently there. Best-effort — a failure here degrades to
    an honest unclear pass (grounding_gate_clear() then correctly refuses
    until a real clean pass lands), never a crash on the stance change
    itself."""
    try:
        from sovereign_agent.grounding import record_grounding_pass

        texts = _recent_text_for_stance(data_dir)
        record_grounding_pass(texts, data_dir)
    except Exception:  # noqa: BLE001
        pass


def grounding_gate_clear(data_dir: Path | None = None) -> bool:  # grounding-modes-d
    """True iff a grounding pass completed CLEANLY since the current
    "grounded" stance was entered — 'fresh' means literally recorded
    after activation (compared by timestamp), not just recent in
    wall-clock time. True (nothing to gate) when not in the stance at all."""
    state_path, _ = _paths(data_dir)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    if state.get("stance") != "grounded":
        return True
    entered_at = state.get("at", "")
    try:
        from sovereign_agent.grounding import latest_grounding

        latest = latest_grounding(data_dir)
    except Exception:  # noqa: BLE001
        return False
    if latest is None:
        return False
    return bool(latest.get("ts", "") >= entered_at
               and latest.get("verdict", "ungrounded") != "ungrounded"
               and latest.get("qa_calibration_ok", False))


def _changed_py_files_since_head(data_dir: Path | None) -> list:  # quality-modes-d
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


def _run_quality_pass_for_stance(data_dir: Path | None) -> None:  # quality-modes-d
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


def quality_gate_clear(data_dir: Path | None = None) -> bool:  # quality-modes-d
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


def recent_stances(n: int = 8, data_dir: Path | None = None) -> list[dict]:
    """The last n stance transitions, oldest first. Tolerant read."""
    _, history_path = _paths(data_dir)
    try:
        from sovereign_agent.read_repair import read_ndjson_tolerant

        return read_ndjson_tolerant(history_path, store="inner-stances",
                                    emit=False).records[-n:]
    except Exception:  # noqa: BLE001
        return []


def cooling_down(data_dir: Path | None = None) -> bool:
    return current_stance(data_dir) == "cool-down"


def _run_integrity_pass_for_stance(data_dir: Path | None) -> None:  # integrity-modes-d
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


def integrity_gate_clear(data_dir: Path | None = None) -> bool:  # integrity-modes-d
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
