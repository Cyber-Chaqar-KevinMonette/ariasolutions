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
    return rec


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
