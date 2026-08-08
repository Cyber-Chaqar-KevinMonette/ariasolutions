"""
╔══════════════════════════════════════════════════════════════════════════╗
║  interrupts.py — graceful conversation-mode toggle                       ║
║  v0.2.16.0                                                                ║
║                                                                           ║
║  THE PROBLEM                                                             ║
║                                                                           ║
║    Aria can be doing long work (a multi-cycle dream session, a big       ║
║    refactor, a batch of audits) and the operator suddenly wants to      ║
║    talk. Hard-killing the process loses checkpoint state. Letting the   ║
║    operator type messages into a queue is fine, but they may not be     ║
║    answered for a long time. Neither feels good.                         ║
║                                                                           ║
║  THE FIX                                                                 ║
║                                                                           ║
║    A flag file. The operator sets it via CLI (or any UI that drops the  ║
║    file). Long-running loops call ``check_conversation_request()`` at   ║
║    safe checkpoints; when the flag is present, the loop:                ║
║                                                                           ║
║      1. Writes a continuation file so it can resume later                ║
║      2. Acknowledges the request (writes ack file with timestamp)       ║
║      3. Returns control                                                  ║
║                                                                           ║
║    The operator then chats freely. When ready: ``sov resume`` clears    ║
║    the flag and the loop picks up from the continuation.                ║
║                                                                           ║
║  DESIGN PROPERTIES                                                       ║
║                                                                           ║
║    • Flag-file based. No new daemon, no new IPC, no new dependency.    ║
║      Same pattern as the existing HALT flag.                            ║
║    • Polling. The loop checks at safe checkpoints it already has.      ║
║    • Reversible. Setting and clearing the flag are both safe at any    ║
║      time. The agent does not crash if the flag appears mid-checkpoint.║
║    • Observable. ``sov chat status`` shows current state, request time,║
║      and last acknowledgement.                                          ║
║                                                                           ║
║  NOT INCLUDED                                                            ║
║                                                                           ║
║    • Wiring into the actual long-running loops (dream, agentic plan,   ║
║      etc). That is a per-loop integration in a later release; the      ║
║      infrastructure is here, but the existing loops in v0.2.16.0 do    ║
║      not yet call ``check_conversation_request()``. New code should.   ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import SETTINGS


# Flag-file names. Kept lowercase + dotted to distinguish from existing
# HALT (which is uppercase and is a stop-the-world signal). These are
# soft signals: "Aria, when convenient, please come talk to me."
_REQUEST_FILE = "conversation.request"
_ACK_FILE = "conversation.ack"
_RESUME_FILE = "conversation.resume"


def _flag_dir() -> Path:
    return SETTINGS.paths.config_dir


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True)
class ConversationState:
    """Snapshot of the conversation-mode flag set."""
    requested: bool                  # operator has asked Aria to come talk
    requested_at: str | None         # ISO ts when requested
    acknowledged: bool               # Aria has paused and is ready to talk
    acknowledged_at: str | None      # ISO ts when she paused
    resume_pending: bool             # operator has asked her to resume
    resume_at: str | None            # ISO ts of the resume request
    note: str | None                 # optional message attached by operator

    @property
    def is_paused(self) -> bool:
        """Aria is currently in conversation mode."""
        return self.requested and self.acknowledged and not self.resume_pending

    @property
    def is_working(self) -> bool:
        """Aria is currently working (no pending conversation request)."""
        return not self.requested

    def render(self) -> str:
        if self.is_paused:
            head = "● conversation mode (paused)"
        elif self.requested and not self.acknowledged:
            head = "◐ conversation requested (Aria has not yet acknowledged)"
        elif self.resume_pending:
            head = "◑ resume requested (Aria will return to work)"
        else:
            head = "○ working"
        lines = [head]
        if self.requested_at:
            lines.append(f"  requested at: {self.requested_at[:19]}")
        if self.acknowledged_at:
            lines.append(f"  acknowledged: {self.acknowledged_at[:19]}")
        if self.resume_at:
            lines.append(f"  resume at:    {self.resume_at[:19]}")
        if self.note:
            lines.append(f"  note: {self.note}")
        return "\n".join(lines)


# ─── Operator-side actions ────────────────────────────────────────────────


def request_conversation(note: str | None = None) -> ConversationState:
    """Operator: ask Aria to pause and enter conversation mode.

    Idempotent — re-requesting before an ack is fine. If Aria has already
    acknowledged a previous request, this REPLACES the existing request
    (which means she'll re-acknowledge — but since she's already paused,
    this is a cheap no-op for her).
    """
    d = _flag_dir()
    d.mkdir(parents=True, exist_ok=True)
    payload = {"requested_at": _utc_now(), "note": note}
    (d / _REQUEST_FILE).write_text(json.dumps(payload, indent=2))
    return status()


def clear_conversation_request() -> ConversationState:
    """Operator: cancel a pending request (before Aria paused).

    Removes the request file. If Aria already acked, also removes the ack
    so the state returns cleanly to 'working'.
    """
    d = _flag_dir()
    (d / _REQUEST_FILE).unlink(missing_ok=True)
    (d / _ACK_FILE).unlink(missing_ok=True)
    (d / _RESUME_FILE).unlink(missing_ok=True)
    return status()


def request_resume() -> ConversationState:
    """Operator: tell Aria she can return to work.

    Writes the resume file; the next ``check_conversation_request()``
    call by the loop will see this and exit conversation mode.
    """
    d = _flag_dir()
    d.mkdir(parents=True, exist_ok=True)
    payload = {"resume_at": _utc_now()}
    (d / _RESUME_FILE).write_text(json.dumps(payload, indent=2))
    return status()


def status() -> ConversationState:
    """Read the current state. Safe to call any time."""
    d = _flag_dir()
    req_path = d / _REQUEST_FILE
    ack_path = d / _ACK_FILE
    res_path = d / _RESUME_FILE

    requested_at: str | None = None
    note: str | None = None
    if req_path.exists():
        try:
            data = json.loads(req_path.read_text())
            requested_at = data.get("requested_at")
            note = data.get("note")
        except (OSError, ValueError):
            pass

    acknowledged_at: str | None = None
    if ack_path.exists():
        try:
            data = json.loads(ack_path.read_text())
            acknowledged_at = data.get("acknowledged_at")
        except (OSError, ValueError):
            pass

    resume_at: str | None = None
    if res_path.exists():
        try:
            data = json.loads(res_path.read_text())
            resume_at = data.get("resume_at")
        except (OSError, ValueError):
            pass

    return ConversationState(
        requested=req_path.exists(),
        requested_at=requested_at,
        acknowledged=ack_path.exists(),
        acknowledged_at=acknowledged_at,
        resume_pending=res_path.exists(),
        resume_at=resume_at,
        note=note,
    )


# ─── Agent-side hook ──────────────────────────────────────────────────────


def check_conversation_request() -> bool:
    """Loop hook: returns True if Aria should yield to conversation mode.

    Long-running loops call this at safe checkpoints. When True:
      1. The loop should save its continuation state.
      2. The loop should call ``acknowledge_pause()`` to mark itself paused.
      3. The loop should return control to the chat surface.

    When False, the loop continues normally.

    This function does NOT acknowledge — the loop must do that explicitly
    AFTER its checkpoint write succeeds, so that an ack always reflects
    a recoverable state.
    """
    d = _flag_dir()
    return (d / _REQUEST_FILE).exists() and not (d / _RESUME_FILE).exists()


def acknowledge_pause(continuation_id: str | None = None) -> ConversationState:
    """Loop: declare that Aria has reached a safe checkpoint and is pausing.

    Writes the ack file with timestamp and (optionally) the continuation
    id the loop wrote. The operator's ``sov chat status`` will now show
    that Aria is paused and ready.
    """
    d = _flag_dir()
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "acknowledged_at": _utc_now(),
        "continuation_id": continuation_id,
    }
    (d / _ACK_FILE).write_text(json.dumps(payload, indent=2))
    return status()


def consume_resume() -> tuple[bool, str | None]:
    """Loop: check for a resume request and consume it.

    Returns ``(should_resume, continuation_id)``. After this call returns
    True, the request/ack/resume flag set is fully cleared and Aria is
    back in 'working' state.
    """
    d = _flag_dir()
    res_path = d / _RESUME_FILE
    if not res_path.exists():
        return False, None
    # Recover the continuation_id from the ack file if present
    continuation_id: str | None = None
    ack_path = d / _ACK_FILE
    if ack_path.exists():
        try:
            data = json.loads(ack_path.read_text())
            continuation_id = data.get("continuation_id")
        except (OSError, ValueError):
            pass
    # Clear all three flags
    (d / _REQUEST_FILE).unlink(missing_ok=True)
    (d / _ACK_FILE).unlink(missing_ok=True)
    res_path.unlink(missing_ok=True)
    return True, continuation_id


def checkpoint(continuation_id: str | None = None) -> bool:
    """One-line conversation-mode hook for any long-running loop.

    Usage inside a loop body, at a safe place to pause::

        from sovereign_agent.interrupts import checkpoint

        for cycle in range(num_cycles):
            do_work(cycle)
            if checkpoint(continuation_id=f"dream-{dream_id}-{cycle}"):
                break   # exit the loop; operator wants to talk

    Returns True iff the operator has requested conversation mode AND
    the loop should yield. When True, the loop has already acknowledged
    the pause and saved the continuation marker. The loop is expected
    to exit its body cleanly (return or break) — the next time the loop
    is re-entered (e.g. via `sov chat resume`), it should check
    ``consume_resume()`` to learn the saved continuation_id and pick
    up from there.

    Returns False when no conversation request is pending — the common
    case, sub-microsecond cost.
    """
    if not check_conversation_request():
        return False
    acknowledge_pause(continuation_id=continuation_id)
    return True


__all__ = [
    "ConversationState",
    "request_conversation",
    "clear_conversation_request",
    "request_resume",
    "status",
    "check_conversation_request",
    "acknowledge_pause",
    "consume_resume",
    "checkpoint",
]
