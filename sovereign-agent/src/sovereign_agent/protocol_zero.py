"""PROTOCOL-ZERO — the killswitch. Architecture §5.

Triggers (any one):
  - kill -USR1 <pid>
  - ~/.config/sovereign-agent/HALT exists
  - daily token budget exceeded (caller checks)
  - 3 consecutive poison-d in 1 hour (caller checks)
  - disk free < 5 GB on $HOME (caller checks)

Restart after a halt requires manual ack: delete the HALT file.
"""
from __future__ import annotations

import signal
import sys
import threading

from .config import SETTINGS
from .events import emit_event

_HALT = threading.Event()


def _on_sigusr1(_signum, _frame) -> None:  # noqa: ANN001
    _HALT.set()
    emit_event(
        "protocol-zero-d",
        plane="control",
        trace_id="protocol-zero",
        payload={"trigger": "SIGUSR1"},
    )


def install_signal_handlers() -> None:
    """Wire SIGUSR1. Call once at startup.

    No-op on Windows — SIGUSR1 is not available there. Use the HALT file
    or arm() programmatically on that platform.
    """
    if sys.platform == "win32":
        return
    signal.signal(signal.SIGUSR1, _on_sigusr1)


def is_armed() -> bool:
    """Check all kill triggers. Should be called between agent loop iterations."""
    if _HALT.is_set():
        return True
    if SETTINGS.paths.halt_flag.exists():
        if not _HALT.is_set():
            _HALT.set()
            emit_event(
                "protocol-zero-d",
                plane="control",
                trace_id="protocol-zero",
                payload={"trigger": "HALT_file"},
            )
        return True
    return False


def arm(reason: str) -> None:
    """Trip PROTOCOL-ZERO programmatically (e.g., from a budget check)."""
    _HALT.set()
    SETTINGS.paths.halt_flag.write_text(reason + "\n")
    emit_event(
        "protocol-zero-d",
        plane="control",
        trace_id="protocol-zero",
        payload={"trigger": "programmatic", "reason": reason},
    )


def disarm() -> None:
    """Manual ack: clear the halt state. CLI invokes this after operator review."""
    _HALT.clear()
    SETTINGS.paths.halt_flag.unlink(missing_ok=True)
