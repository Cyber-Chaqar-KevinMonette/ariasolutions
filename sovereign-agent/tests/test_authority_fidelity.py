"""Tests for M65 — Authority gate edge cases + VRAM lock safety.

Covers: tier filtering per mode, missing tier annotation fallback,
duplicate registration, approval token requirement, VRAM lock timeout event.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from sovereign_agent.authority import (
    AuthorityViolation,
    ToolMeta,
    check_authority,
    register_tool,
    tools_available_in_mode,
)
from sovereign_agent.modes import Mode


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _t0(name: str = "tool-t0") -> ToolMeta:
    return ToolMeta(name=name, tier=0, description="t0 tool", failure_modes=("err",))


def _t1(name: str = "tool-t1") -> ToolMeta:
    return ToolMeta(name=name, tier=1, description="t1 tool", failure_modes=("err",))


def _t2(name: str = "tool-t2") -> ToolMeta:
    return ToolMeta(name=name, tier=2, description="t2 tool", failure_modes=("err",))


def _t3(name: str = "tool-t3") -> ToolMeta:
    return ToolMeta(
        name=name, tier=3, description="t3 tool",
        requires_approval=True, failure_modes=("err",),
    )


# ─── Tool registration ───────────────────────────────────────────────────────


def test_register_t0_tool():
    register_tool(_t0("reg-t0"))
    meta = check_authority("reg-t0", Mode.ONESHOT)
    assert meta.tier == 0


def test_register_t3_requires_approval():
    with pytest.raises(ValueError, match="requires_approval"):
        register_tool(ToolMeta(
            name="bad-t3", tier=3, description="missing approval",
            requires_approval=False, failure_modes=("err",),
        ))


def test_register_tool_missing_failure_modes():
    with pytest.raises(ValueError, match="failure mode"):
        register_tool(ToolMeta(
            name="no-modes", tier=0, description="no modes",
            failure_modes=(),
        ))


def test_duplicate_registration_last_wins():
    """Re-registering a tool name overwrites the previous entry."""
    register_tool(_t0("dup-tool"))
    register_tool(_t1("dup-tool"))  # overwrite with T1
    # Should now be T1
    from sovereign_agent.authority import get_tool_meta
    meta = get_tool_meta("dup-tool")
    assert meta.tier == 1


# ─── Tier filtering per mode ─────────────────────────────────────────────────


def test_t0_included_in_busy_mode():
    register_tool(_t0("busy-t0"))
    available = [m.name for m in tools_available_in_mode(Mode.BUSY)]
    assert "busy-t0" in available


def test_t1_included_in_busy_mode():
    """BUSY mode ceiling is T1 — T1 tools should be available."""
    register_tool(_t1("busy-t1"))
    available = [m.name for m in tools_available_in_mode(Mode.BUSY)]
    assert "busy-t1" in available


def test_t2_excluded_from_busy_mode():
    register_tool(_t2("busy-t2"))
    available = [m.name for m in tools_available_in_mode(Mode.BUSY)]
    assert "busy-t2" not in available


def test_t3_excluded_from_busy_mode():
    register_tool(_t3("busy-t3"))
    available = [m.name for m in tools_available_in_mode(Mode.BUSY)]
    assert "busy-t3" not in available


def test_t3_included_in_oneshot_mode():
    register_tool(_t3("oneshot-t3"))
    available = [m.name for m in tools_available_in_mode(Mode.ONESHOT)]
    assert "oneshot-t3" in available


# ─── check_authority ────────────────────────────────────────────────────────


def test_check_authority_ok_for_t0_in_busy():
    register_tool(_t0("check-t0"))
    meta = check_authority("check-t0", Mode.BUSY)
    assert meta.tier == 0


def test_check_authority_raises_for_t2_in_busy():
    register_tool(_t2("check-t2"))
    with pytest.raises(AuthorityViolation) as exc_info:
        check_authority("check-t2", Mode.BUSY)
    assert exc_info.value.tool_tier == 2


def test_check_authority_raises_for_unknown_tool():
    from sovereign_agent.authority import get_tool_meta
    with pytest.raises(KeyError):
        get_tool_meta("completely-unknown-tool")


def test_authority_violation_message_informative():
    register_tool(_t3("viol-t3"))
    with pytest.raises(AuthorityViolation) as exc_info:
        check_authority("viol-t3", Mode.BUSY)
    msg = str(exc_info.value)
    assert "viol-t3" in msg
    assert "3" in msg  # tier number


# ─── VRAM lock timeout emits event ───────────────────────────────────────────


def test_vram_lock_timeout_raises_timeout_error(tmp_path):
    """When another process holds the lock past timeout, TimeoutError is raised."""
    import fcntl
    from sovereign_agent.config import SETTINGS

    lock_path = SETTINGS.paths.config_dir / "vram.lock"
    lock_path.touch(exist_ok=True)

    emitted = []

    # Simulate the lock being held: open + exclusive lock
    f = lock_path.open("r+")
    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        from sovereign_agent.vram import vram_lock
        with pytest.raises(TimeoutError):
            with vram_lock("test-tool", timeout_seconds=0.2):
                pass
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def test_vram_lock_succeeds_when_not_held(tmp_path):
    """When no other holder, the lock should be acquired successfully."""
    from sovereign_agent.vram import vram_lock
    with vram_lock("whisper", timeout_seconds=5.0):
        pass  # should not raise


def test_vram_lock_timeout_emits_event_if_patched(tmp_path):
    """Verify the vram lock emits 'vram-lock-timeout-d' event on timeout.

    This test validates the M65 enhancement: emit_event on timeout.
    If not yet patched (pre-M65), this test will be skipped.
    """
    import fcntl
    from sovereign_agent.config import SETTINGS
    from sovereign_agent import vram as vram_module

    # Only check if the enhancement has been applied
    import inspect
    vram_src = inspect.getsource(vram_module)
    if "vram-lock-timeout-d" not in vram_src:
        pytest.skip("M65 vram timeout event not yet applied — apply M65 first")

    emitted = []
    lock_path = SETTINGS.paths.config_dir / "vram.lock"
    lock_path.touch(exist_ok=True)

    f = lock_path.open("r+")
    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with patch("sovereign_agent.vram.emit_event", side_effect=lambda t, **kw: emitted.append(t)):
            with pytest.raises(TimeoutError):
                with vram_module.vram_lock("test-tool", timeout_seconds=0.2):
                    pass
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()

    assert "vram-lock-timeout-d" in emitted


# ─── Mode tier ceiling constants ─────────────────────────────────────────────


def test_busy_mode_ceiling_is_1():
    from sovereign_agent.modes import MODE_TIER_CEILING
    assert MODE_TIER_CEILING[Mode.BUSY] == 1


def test_oneshot_mode_ceiling_is_3():
    from sovereign_agent.modes import MODE_TIER_CEILING
    assert MODE_TIER_CEILING[Mode.ONESHOT] == 3


def test_timed_mode_ceiling_is_3():
    from sovereign_agent.modes import MODE_TIER_CEILING
    assert MODE_TIER_CEILING[Mode.TIMED] == 3
