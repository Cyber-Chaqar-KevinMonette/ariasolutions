"""autonomy/session.py — Supervised Autonomy Sessions: time-boxed, observable, resumable.

Kevin's design, made real: Aria PLANS, then presents the human options. Option 1 approves a bounded block
of autonomous work (~90 min) before re-approval. While the block runs she works inside a LEASE whose
blast-radius is tightly bounded — staged drafting, verification, and scrutiny ONLY. No outward actions, no
sealed-file edits, no applying anything. At the timeout she PAUSES with a resumable checkpoint; the human
continues, re-approves another block, or enters plan mode to edit the plan *with* her.

This mirrors the aegis lease doctrine (`aegis/leases.py`: bounded scope + expiry that can't strand
authority) at the workflow scale. God-tier safety: bounded · observable · reversible · always-stoppable.
The human stays present, watching and learning. Raising the timeout is a Tier-3 human decision.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Default block length — short enough to keep a human present, observing and learning.
DEFAULT_TTL_SECONDS = 90 * 60      # 90 minutes
MAX_TTL_SECONDS = 2 * 60 * 60      # 2 hours; beyond this is a Tier-3 decision

# The bounded blast-radius: the ONLY actions allowed inside an autonomy block. Inward, reversible, safe.
ALLOWED_ACTIONS = frozenset({
    "draft_staged_module",   # scaffold an aria-<name>/ enhancement (never applied)
    "edit_staged_payload",   # edit files inside an aria-*/ staging folder
    "write_doc",             # write/update a doc or plan
    "run_tests",             # run pytest on staged work
    "verify_module",         # scripts/verify_module.sh
    "scrutinize",            # Tribunal + 14-gen foresight
    "godtier_scan",          # the scanner
    "record_note",           # log a thought/observation
    "run_goal_session",      # dispatch one /work goal via the session bridge (thread-grooming-d)
})
# Explicitly forbidden, always — named so the boundary is legible.
FORBIDDEN_ACTIONS = frozenset({
    "apply_module", "edit_live_src", "edit_sealed_file", "outward_action", "network_send",
    "raise_tier", "disable_killswitch", "git_push", "git_commit",
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class AutonomySession:
    session_id: str
    plan_id: str
    status: str = "proposed"            # proposed | active | paused | expired | complete
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    started_at: str = ""
    expires_at: str = ""
    blocks_completed: int = 0
    checkpoint: dict = field(default_factory=dict)     # {done, next, notes}
    action_log: list = field(default_factory=list)     # observable stream

    def to_dict(self) -> dict:
        return asdict(self)


def propose_session(plan_id: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict:
    """Aria proposes a session and presents the human their options. She does NOT start it herself."""
    ttl = max(60, min(ttl_seconds, MAX_TTL_SECONDS))
    session = AutonomySession(session_id=f"as-{uuid.uuid4().hex[:8]}", plan_id=plan_id, ttl_seconds=ttl)
    return {
        "session": session.to_dict(),
        "options": [
            f"1. APPROVE — let Aria work autonomously for {ttl // 60} min, then pause for re-approval.",
            "2. EDIT — enter plan mode and shape/extend the plan together before she works.",
            "3. DISCUSS — talk through enhancements or concerns first.",
        ],
        "bounded_to": sorted(ALLOWED_ACTIONS),
        "never": sorted(FORBIDDEN_ACTIONS),
        "note": "Propose-only. The human approves Option 1 to start a bounded, observable, reversible block.",
    }


def start_block(session: AutonomySession, *, approved: bool) -> AutonomySession:
    """Begin a bounded autonomous block. Requires explicit human approval. Sets the lease expiry."""
    if not approved:
        raise PermissionError("autonomy block requires explicit human approval (Option 1).")
    session.status = "active"
    session.started_at = _iso(_now())
    session.expires_at = _iso(_now() + timedelta(seconds=session.ttl_seconds))
    session.action_log.append({"ts": session.started_at, "event": "block_started",
                               "ttl_min": session.ttl_seconds // 60})
    return session


def time_remaining(session: AutonomySession) -> int:
    """Seconds left in the current block (0 if not active/expired)."""
    if session.status != "active" or not session.expires_at:
        return 0
    exp = datetime.strptime(session.expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return max(0, int((exp - _now()).total_seconds()))


def within_lease(session: AutonomySession) -> bool:
    return session.status == "active" and time_remaining(session) > 0


def record_action(session: AutonomySession, action: str, detail: str = "") -> dict:
    """Record (and bound-check) an action. REFUSES anything outside the allowed blast-radius or after expiry.

    This is the safety core: she can only do bounded, inward, reversible work, and only while the lease holds.
    """
    if action in FORBIDDEN_ACTIONS:
        entry = {"ts": _iso(_now()), "action": action, "allowed": False,
                 "reason": "forbidden action — outside the autonomy blast-radius (human-gated)"}
        session.action_log.append(entry)
        return entry
    if action not in ALLOWED_ACTIONS:
        entry = {"ts": _iso(_now()), "action": action, "allowed": False,
                 "reason": "action not in the allowed set — propose it to the human first"}
        session.action_log.append(entry)
        return entry
    if not within_lease(session):
        entry = {"ts": _iso(_now()), "action": action, "allowed": False,
                 "reason": "lease expired or inactive — pause and request re-approval"}
        session.action_log.append(entry)
        return entry
    entry = {"ts": _iso(_now()), "action": action, "allowed": True, "detail": detail[:200]}
    session.action_log.append(entry)
    return entry


def pause(session: AutonomySession, *, done: str, next_up: str, notes: str = "") -> AutonomySession:
    """Pause with a resumable checkpoint (what's done, what's next). Called at timeout or on request."""
    session.status = "paused"
    session.blocks_completed += 1
    session.checkpoint = {"done": done, "next": next_up, "notes": notes, "paused_at": _iso(_now())}
    session.action_log.append({"ts": _iso(_now()), "event": "paused", "checkpoint": session.checkpoint})
    return session


def resume(session: AutonomySession, *, approved: bool) -> AutonomySession:
    """Resume from the checkpoint into a fresh bounded block. Requires re-approval (human stays in the loop)."""
    if session.status != "paused":
        raise ValueError(f"cannot resume a session in status {session.status!r}")
    return start_block(session, approved=approved)


def expire_if_due(session: AutonomySession) -> AutonomySession:
    """Flip an active-but-elapsed session to a pause state (the lease can't strand authority)."""
    if session.status == "active" and time_remaining(session) <= 0:
        pause(session, done="(auto) block time elapsed", next_up="await human: continue / re-approve / plan mode",
              notes="lease expired — paused automatically to keep the human in the loop")
        session.status = "paused"
    return session


# ── persistence (resumable across sessions) ───────────────────────────────────

def _sessions_dir(data_dir: Path) -> Path:
    p = Path(data_dir) / "autonomy"
    p.mkdir(parents=True, exist_ok=True)
    return p


def save(session: AutonomySession, data_dir: Path) -> Path:
    p = _sessions_dir(data_dir) / f"{session.session_id}.json"
    p.write_text(json.dumps(session.to_dict(), indent=2), encoding="utf-8")
    return p


def load(session_id: str, data_dir: Path) -> AutonomySession | None:
    p = _sessions_dir(data_dir) / f"{session_id}.json"
    if not p.exists():
        return None
    return AutonomySession(**json.loads(p.read_text(encoding="utf-8")))


def observe(session: AutonomySession, *, tail: int = 20) -> list[dict]:
    """The live observation stream — what she's doing, for the human watching."""
    return session.action_log[-tail:]
