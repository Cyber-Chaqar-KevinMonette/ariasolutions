"""
╔══════════════════════════════════════════════════════════════════════════╗
║  cockpit_modes.py — explicit `chat` and `work` modes (v0.2.32.0)         ║
║                                                                           ║
║  Humans have modes. Software has modes. v0.2.32.0 makes Aria's implicit  ║
║  modes explicit:                                                          ║
║                                                                           ║
║    `chat` — the default. Conversational. No autonomous agent loops       ║
║             run between operator turns. Tool calls happen only when      ║
║             the operator asks for them directly. The cockpit feels       ║
║             like a chat with a thoughtful partner.                       ║
║                                                                           ║
║    `work` — the high-leverage mode. Multi-tool calling, planned          ║
║             queue execution, queue-of-queues extension when Aria          ║
║             discovers mid-run that more work is needed. Calibrated,      ║
║             measured, audited. Not over-grown. Not over-sequenced.       ║
║             Just precise.                                                ║
║                                                                           ║
║  This module is the source of truth for which mode is active. The        ║
║  cockpit reads it on every input; the agent_session reads it before     ║
║  any autonomous loop; the constitution_check honors it when gating      ║
║  Tier-3 actions.                                                         ║
║                                                                           ║
║  Mode state lives in:                                                    ║
║    <config_dir>/cockpit_mode.txt                                         ║
║                                                                           ║
║  One word per line: "chat" or "work". Anything else → fall back to chat ║
║  (the safer default).                                                   ║
║                                                                           ║
║  Transitions are always operator-initiated and always emit an event:    ║
║                                                                           ║
║    cockpit-mode-changed-d { from: "chat", to: "work", reason: "..." }   ║
║                                                                           ║
║  The seven commitments still bind in both modes — modes are about       ║
║  *initiative*, not about *trust*. In neither mode does Aria authorize   ║
║  another agent. In neither mode does she skip the constitution checks.  ║
║  Work mode just means she's allowed to plan and queue without asking    ║
║  for permission to think.                                                ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)


class CockpitMode(StrEnum):
    """The two operator-facing modes the cockpit (and agent_session) honor.

    Chat is the default — Aria never starts an autonomous loop between
    operator turns. Every action is a direct response to something the
    operator just said.

    Work is the high-leverage mode — Aria can plan, queue, and extend
    queues mid-run when she discovers more work is needed. The queue
    extension mechanism is what makes "I thought 125 runs; turns out we
    need 250" expressible without queue-bursting.
    """
    CHAT = "chat"
    WORK = "work"


@dataclass(frozen=True)
class ModeState:
    """A snapshot of the current mode plus the path it was loaded from.

    Frozen so callers can pass it around without worrying about mutation.
    Use ``set_mode()`` to transition; the new state is returned.
    """
    mode: CockpitMode
    path: Path


def _mode_file_path(config_dir: Path | None = None) -> Path:
    """Resolve the on-disk path where the current mode lives.

    Honors the existing ``SETTINGS.paths.config_dir`` if no override is
    given. This keeps the file alongside ``agent.yaml`` so it's discoverable
    by an operator running ``ls ~/.config/sovereign-agent/``.
    """
    if config_dir is None:
        from .config import SETTINGS  # local import — avoids cycle on cold load
        config_dir = SETTINGS.paths.config_dir
    return config_dir / "cockpit_mode.txt"


def load_mode(config_dir: Path | None = None) -> ModeState:
    """Read the current mode from disk.

    If the file is missing, malformed, or unreadable, we silently return
    ``CHAT`` — the safe default. We never raise from a read path. If you
    need to debug a missing file, check ``stat <path>`` directly.

    Resilience contract (matches aria.load_state):
        Any failure → return CHAT default, log at debug.
    """
    path = _mode_file_path(config_dir)
    try:
        text = path.read_text(encoding="utf-8").strip().lower()
        if text == CockpitMode.WORK.value:
            return ModeState(mode=CockpitMode.WORK, path=path)
        if text == CockpitMode.CHAT.value:
            return ModeState(mode=CockpitMode.CHAT, path=path)
        logger.debug("cockpit_modes: malformed mode value %r; defaulting to chat", text)
    except FileNotFoundError:
        logger.debug("cockpit_modes: %s missing; defaulting to chat", path)
    except OSError as exc:
        logger.debug("cockpit_modes: read failed %r; defaulting to chat", exc)
    return ModeState(mode=CockpitMode.CHAT, path=path)


def set_mode(
    new_mode: CockpitMode,
    *,
    reason: str = "",
    config_dir: Path | None = None,
) -> ModeState:
    """Transition the cockpit mode.

    Writes the new mode to disk atomically (write to temp then rename)
    so a crash mid-write can never leave the file half-baked. Emits a
    ``cockpit-mode-changed-d`` event so the audit trail captures every
    transition.

    Args:
        new_mode: where we're going.
        reason: optional operator-supplied rationale. Captured in the
                emitted event so the audit trail explains WHY a mode
                changed, not just THAT it did.

    Returns:
        The new ModeState. Idempotent — calling with the same mode
        rewrites the file (which is fine) and still emits an event
        (so explicit re-affirmations are visible).
    """
    path = _mode_file_path(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: tempfile + rename. POSIX guarantees rename is
    # atomic within the same filesystem.
    tmp = path.with_suffix(".tmp")
    tmp.write_text(new_mode.value + "\n", encoding="utf-8")
    tmp.replace(path)

    # Best-effort event emission. The events module may not be loaded
    # in tests; we silently no-op if it's unavailable.
    try:
        from .events import emit_event
        emit_event(
            "cockpit-mode-changed-d",
            plane="control",
            trace_id="cockpit-mode",
            payload={"to": new_mode.value, "reason": reason or "(none)"},
        )
    except Exception:  # noqa: BLE001 — events are best-effort
        logger.debug("cockpit_modes: event emission failed; mode change still persisted")

    return ModeState(mode=new_mode, path=path)


def is_work_mode(config_dir: Path | None = None) -> bool:
    """Quick check: are we in work mode?

    Convenience helper for the agent_session and the constitution check.
    Equivalent to ``load_mode().mode == CockpitMode.WORK``.
    """
    return load_mode(config_dir).mode == CockpitMode.WORK


def is_chat_mode(config_dir: Path | None = None) -> bool:
    """Quick check: are we in chat mode?

    Convenience helper. True when the file says ``chat`` or is missing/
    malformed — chat is the safe default.
    """
    return load_mode(config_dir).mode == CockpitMode.CHAT


# ─── Mode-aware decisions ──────────────────────────────────────────────────


def autonomous_loops_allowed(config_dir: Path | None = None) -> bool:
    """Should the agent_session start a new loop without operator input?

    In chat mode: NO. Every loop iteration requires an operator-initiated
    trigger. The session can resume after a budget hit ONLY if the
    operator calls ``sov resume`` — never automatically.

    In work mode: YES. The agent_session can plan, queue, extend, and
    self-resume within configured budgets. The four-gate loop in
    ``run_session`` is the safety net.
    """
    return is_work_mode(config_dir)


def queue_extension_allowed(config_dir: Path | None = None) -> bool:
    """Can the agent extend its own queue mid-run when it discovers
    more work is needed?

    Only in work mode. In chat mode, if Aria discovers a queue is
    inadequate, she stops and asks the operator. No silent queue
    growth.
    """
    return is_work_mode(config_dir)


__all__ = [
    "CockpitMode",
    "ModeState",
    "autonomous_loops_allowed",
    "is_chat_mode",
    "is_work_mode",
    "load_mode",
    "queue_extension_allowed",
    "set_mode",
]
