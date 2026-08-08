"""Tests for M64 — Protocol Zero hardening.

Tests arm/disarm/is_armed lifecycle, HALT file triggers,
and concurrent arming behavior. Builds on the 1 existing test
in test_v0214_hardening.py.
"""
from __future__ import annotations

import os
import signal
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from sovereign_agent import protocol_zero


# ─── Basic lifecycle ─────────────────────────────────────────────────────────


def test_is_armed_false_on_clean_state():
    assert protocol_zero.is_armed() is False


def test_arm_makes_is_armed_true(tmp_path):
    protocol_zero.arm("test-reason")
    assert protocol_zero.is_armed() is True


def test_disarm_clears_is_armed(tmp_path):
    protocol_zero.arm("test")
    protocol_zero.disarm()
    assert protocol_zero.is_armed() is False


def test_arm_writes_halt_file(tmp_path):
    from sovereign_agent.config import SETTINGS
    protocol_zero.arm("budget exceeded")
    assert SETTINGS.paths.halt_flag.exists()


def test_halt_file_contains_reason(tmp_path):
    from sovereign_agent.config import SETTINGS
    protocol_zero.arm("test reason for halt")
    content = SETTINGS.paths.halt_flag.read_text()
    assert "test reason for halt" in content


def test_disarm_removes_halt_file(tmp_path):
    from sovereign_agent.config import SETTINGS
    protocol_zero.arm("temporary")
    protocol_zero.disarm()
    assert not SETTINGS.paths.halt_flag.exists()


# ─── HALT file trigger ────────────────────────────────────────────────────────


def test_halt_file_present_triggers_is_armed(tmp_path):
    """Writing the HALT file manually (without arm()) also arms the system."""
    from sovereign_agent.config import SETTINGS
    protocol_zero.disarm()  # ensure clean state
    # Manually create HALT file (simulates external operator-created HALT)
    SETTINGS.paths.halt_flag.write_text("manual halt\n")
    assert protocol_zero.is_armed() is True


def test_halt_file_removed_disarms(tmp_path):
    from sovereign_agent.config import SETTINGS
    SETTINGS.paths.halt_flag.write_text("manual halt\n")
    protocol_zero.is_armed()  # triggers _HALT.set() via file detection
    protocol_zero.disarm()
    assert not protocol_zero.is_armed()


# ─── emit_event called ────────────────────────────────────────────────────────


def test_arm_emits_protocol_zero_event(tmp_path):
    from sovereign_agent import events as _events
    emitted = []

    original = _events.emit_event

    def _capture(event_type, **kwargs):
        emitted.append({"type": event_type, **kwargs})
        return original(event_type, **kwargs)

    with patch.object(_events, "emit_event", side_effect=_capture):
        # Also patch protocol_zero's reference to emit_event
        with patch("sovereign_agent.protocol_zero.emit_event", side_effect=_capture):
            protocol_zero.arm("event-test")

    types = [e["type"] for e in emitted]
    assert "protocol-zero-d" in types


def test_halt_file_detection_emits_event(tmp_path):
    from sovereign_agent.config import SETTINGS
    from sovereign_agent import events as _events
    emitted = []

    protocol_zero.disarm()
    SETTINGS.paths.halt_flag.write_text("file-triggered\n")

    with patch("sovereign_agent.protocol_zero.emit_event", side_effect=lambda t, **kw: emitted.append(t)):
        protocol_zero.is_armed()

    assert "protocol-zero-d" in emitted


# ─── Concurrent arming ───────────────────────────────────────────────────────


def test_concurrent_arm_exactly_one_halt_file(tmp_path):
    """Two threads calling arm() concurrently → exactly one HALT file."""
    from sovereign_agent.config import SETTINGS
    results = []

    def _arm():
        try:
            protocol_zero.arm(f"concurrent-{threading.get_ident()}")
            results.append("ok")
        except Exception as e:
            results.append(f"error: {e}")

    protocol_zero.disarm()

    t1 = threading.Thread(target=_arm)
    t2 = threading.Thread(target=_arm)
    t1.start(); t2.start()
    t1.join(timeout=3); t2.join(timeout=3)

    assert SETTINGS.paths.halt_flag.exists()
    assert all(r == "ok" for r in results)


# ─── Signal handler ──────────────────────────────────────────────────────────


def test_install_signal_handlers_no_crash():
    """install_signal_handlers() should not raise."""
    protocol_zero.install_signal_handlers()


def test_sigusr1_sets_halt(tmp_path):
    """Sending SIGUSR1 to self should arm protocol zero via signal handler."""
    protocol_zero.disarm()
    protocol_zero.install_signal_handlers()
    os.kill(os.getpid(), signal.SIGUSR1)
    time.sleep(0.1)
    assert protocol_zero.is_armed() is True


# ─── Repeated operations ─────────────────────────────────────────────────────


def test_double_arm_is_idempotent(tmp_path):
    protocol_zero.arm("first")
    protocol_zero.arm("second")
    assert protocol_zero.is_armed() is True


def test_double_disarm_is_safe(tmp_path):
    protocol_zero.arm("arm")
    protocol_zero.disarm()
    protocol_zero.disarm()  # should not raise
    assert protocol_zero.is_armed() is False
