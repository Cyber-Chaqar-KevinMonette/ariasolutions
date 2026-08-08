"""aria_lm/retrain_trigger.py — bounded, propose-only continual-learning trigger.

Counts lessons distilled by the Reflector (reflector.py -> atoms.db's `lessons`
table) since the last completed training run, and proposes — never
auto-executes — a retrain once enough new lessons have accumulated.

Training a base-weight model is Tier 3 / human-gated per aria_lm_tools.py's
own doctrine ("A base-weight TRAINING run or architecture change is Tier 3
(Ring 3, human-gated)"). This module never calls grow_mind() itself — it
only counts and proposes, matching every other autonomous-adjacent
workstream this session (N's work_interval.py in particular): propose,
don't act.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _marker_path(data_dir: Path) -> Path:
    return Path(data_dir) / "aria_lm" / "last_retrain.json"


def _open_db():
    """Local import — mirrors lessons_tool.py's own pattern of importing db
    lazily so aria_lm's data pipeline stays import-light (data.py's own
    docstring: 'pure-python stdlib, no torch needed here')."""
    from sovereign_agent import db as _db
    return _db.open_atoms_db()


def gather_lesson_text(limit: int = 200) -> str:
    """Format recorded lessons as short training examples: trigger -> rule
    (+ correction). Degrades to "" on any failure (missing db, empty table,
    schema not yet applied) — gather_corpus() must never break because
    lessons aren't available yet."""
    try:
        conn = _open_db()
    except Exception:
        return ""
    try:
        rows = conn.execute(
            "SELECT trigger, rule, correction FROM lessons ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    except Exception:
        return ""
    finally:
        conn.close()

    lines: list[str] = []
    for trigger, rule, correction in rows:
        trigger = (trigger or "").strip()
        rule = (rule or "").strip()
        correction = (correction or "").strip()
        if not (rule or correction):
            continue
        body = f"{rule} {correction}".strip()
        lines.append(f"{trigger}: {body}" if trigger else body)
    return "\n".join(lines)


def total_lesson_count() -> int:
    """Current total row count in the lessons table. 0 on any failure
    (missing db, table not yet created) — never raises."""
    try:
        conn = _open_db()
    except Exception:
        return 0
    try:
        row = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0
    finally:
        conn.close()


def _read_marker(data_dir: Path) -> dict:
    p = _marker_path(data_dir)
    if not p.exists():
        return {"lesson_count_at_last_retrain": 0, "last_retrain_ts": None}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"lesson_count_at_last_retrain": 0, "last_retrain_ts": None}


def record_retrain(data_dir: Path, lesson_count: int | None = None) -> None:
    """Reset the counter. Called ONLY after a real, human-triggered
    grow_mind() run actually completes — never automatically, and never
    from check_retrain_proposal() itself."""
    if lesson_count is None:
        lesson_count = total_lesson_count()
    p = _marker_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({
            "lesson_count_at_last_retrain": lesson_count,
            "last_retrain_ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }),
        encoding="utf-8",
    )


def check_retrain_proposal(data_dir: Path, threshold: int = 20) -> dict | None:
    """Returns a proposal dict once >= threshold new lessons have accumulated
    since the last recorded retrain, else None. NEVER triggers training —
    propose-only. The human decides whether to actually run
    `python -m sovereign_agent.aria_lm.pipeline`."""
    marker = _read_marker(data_dir)
    current = total_lesson_count()
    new_since = max(0, current - marker["lesson_count_at_last_retrain"])
    if new_since < threshold:
        return None
    return {
        "due": True,
        "new_lessons_since_last_retrain": new_since,
        "threshold": threshold,
        "total_lessons": current,
        "last_retrain_ts": marker["last_retrain_ts"],
        "suggested_command": "python -m sovereign_agent.aria_lm.pipeline",
    }
