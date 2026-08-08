"""autonomy/plan_forge.py — god-tier plan building/enhancing that grows over time, even as she works.

A plan is a living, versioned artifact. The human and Aria co-author it; it can be extended between blocks
(or proposed-for-extension during one). Each step has a status so a paused session resumes exactly where it
left off. Plans are the spine of supervised autonomy: she works the plan, observed; the plan evolves with
what's learned. Append-only history so nothing is silently lost.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


def _iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Step:
    id: str
    text: str
    status: str = "pending"        # pending | in_progress | done | deferred
    note: str = ""


@dataclass
class LivingPlan:
    plan_id: str
    title: str
    version: int = 1
    steps: list = field(default_factory=list)
    history: list = field(default_factory=list)     # append-only change log
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def new_plan(title: str, steps: list[str] | None = None) -> LivingPlan:
    p = LivingPlan(plan_id=f"plan-{uuid.uuid4().hex[:8]}", title=title, created_at=_iso(), updated_at=_iso())
    for s in (steps or []):
        p.steps.append(asdict(Step(id=f"s{len(p.steps)+1}", text=s)))
    p.history.append({"ts": _iso(), "event": "created", "version": 1, "n_steps": len(p.steps)})
    return p


def add_step(plan: LivingPlan, text: str, *, at: int | None = None) -> LivingPlan:
    """Extend the plan — it grows over time, even mid-session (proposed, then approved)."""
    step = asdict(Step(id=f"s{len(plan.steps)+1}", text=text))
    if at is None:
        plan.steps.append(step)
    else:
        plan.steps.insert(max(0, at), step)
    _bump(plan, f"added step: {text[:60]}")
    return plan


def set_status(plan: LivingPlan, step_id: str, status: str, note: str = "") -> LivingPlan:
    for s in plan.steps:
        if s["id"] == step_id:
            s["status"] = status
            if note:
                s["note"] = note
            _bump(plan, f"step {step_id} -> {status}")
            break
    return plan


def revise_step(plan: LivingPlan, step_id: str, new_text: str) -> LivingPlan:
    for s in plan.steps:
        if s["id"] == step_id:
            s["text"] = new_text
            _bump(plan, f"revised step {step_id}")
            break
    return plan


def next_step(plan: LivingPlan) -> dict | None:
    """The next actionable step (resume point)."""
    return next((s for s in plan.steps if s["status"] in ("pending", "in_progress")), None)


def progress(plan: LivingPlan) -> dict:
    done = sum(1 for s in plan.steps if s["status"] == "done")
    return {"done": done, "total": len(plan.steps),
            "fraction": round(done / len(plan.steps), 2) if plan.steps else 0.0,
            "next": next_step(plan)}


def _bump(plan: LivingPlan, what: str) -> None:
    plan.version += 1
    plan.updated_at = _iso()
    plan.history.append({"ts": _iso(), "event": what, "version": plan.version})


# ── persistence ───────────────────────────────────────────────────────────────

def _dir(data_dir: Path) -> Path:
    p = Path(data_dir) / "autonomy" / "plans"
    p.mkdir(parents=True, exist_ok=True)
    return p


def save(plan: LivingPlan, data_dir: Path) -> Path:
    p = _dir(data_dir) / f"{plan.plan_id}.json"
    p.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    return p


def load(plan_id: str, data_dir: Path) -> LivingPlan | None:
    p = _dir(data_dir) / f"{plan_id}.json"
    if not p.exists():
        return None
    return LivingPlan(**json.loads(p.read_text(encoding="utf-8")))
