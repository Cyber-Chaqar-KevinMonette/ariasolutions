"""Tests for cockpit.term_bg_sync — OSC-11 terminal background sync.

Coverage:
  • normalize_hex: #rgb / #rrggbb / bare / object-with-.hex / invalid / None
  • osc_set_background: correct OSC 11 string; '' for invalid input
  • osc_reset_background: OSC 111 string
  • bg_sync_disabled: honours SOV_NO_TERM_BG_SYNC
  • resolve_surface_hex: surface → panel → background fallback; None when absent
  • TerminalBackgroundSync: inert under kill-switch / non-TTY; emits-on-change
    only; registers a poll fallback; restore is idempotent. Uses a fake app, so
    no Textual run loop is required.
"""
from __future__ import annotations

import pytest

from sovereign_agent.cockpit import term_bg_sync as T


# ── pure helpers ──────────────────────────────────────────────────────────────
def test_normalize_hex_forms():
    assert T.normalize_hex("#0E0B14") == "#0E0B14"
    assert T.normalize_hex("0e0b14") == "#0E0B14"
    assert T.normalize_hex("#abc") == "#AABBCC"
    assert T.normalize_hex("abc") == "#AABBCC"
    assert T.normalize_hex("nope") is None
    assert T.normalize_hex("#12345") is None
    assert T.normalize_hex(None) is None


class _Color:
    def __init__(self, hexv):
        self.hex = hexv


def test_normalize_hex_object_with_hex():
    assert T.normalize_hex(_Color("#123456")) == "#123456"
    assert T.normalize_hex(_Color("#abc")) == "#AABBCC"


def test_osc_set_and_reset_strings():
    assert T.osc_set_background("#0E0B14") == "\x1b]11;#0E0B14\x07"
    assert T.osc_set_background("0e0b14") == "\x1b]11;#0E0B14\x07"
    assert T.osc_set_background("garbage") == ""
    assert T.osc_reset_background() == "\x1b]111\x07"


def test_kill_switch(monkeypatch):
    monkeypatch.delenv(T.BG_SYNC_KILL_SWITCH_ENV, raising=False)
    assert T.bg_sync_disabled() is False
    monkeypatch.setenv(T.BG_SYNC_KILL_SWITCH_ENV, "1")
    assert T.bg_sync_disabled() is True


# ── theme resolution ──────────────────────────────────────────────────────────
class _Theme:
    def __init__(self, **kw):
        for slot in ("surface", "panel", "background"):
            setattr(self, slot, kw.get(slot))


class _ThemeApp:
    def __init__(self, theme):
        self._theme = theme

    @property
    def current_theme(self):
        return self._theme


def test_resolve_surface_prefers_surface_then_panel_then_background():
    assert T.resolve_surface_hex(_ThemeApp(_Theme(surface="#111111", panel="#222222"))) == "#111111"
    assert T.resolve_surface_hex(_ThemeApp(_Theme(panel="#222222"))) == "#222222"
    assert T.resolve_surface_hex(_ThemeApp(_Theme(background="#333333"))) == "#333333"
    assert T.resolve_surface_hex(_ThemeApp(_Theme())) is None


def test_resolve_surface_never_raises_on_bad_app():
    class _Bad:
        @property
        def current_theme(self):
            raise RuntimeError("boom")

    assert T.resolve_surface_hex(_Bad()) is None
    assert T.resolve_surface_hex(object()) is None


# ── installer behaviour (no Textual run loop) ─────────────────────────────────
class _FakeApp:
    """Minimal app double: a theme, a no-op signal, and set_interval capture."""

    def __init__(self, surface):
        self._theme = _Theme(surface=surface)
        self.intervals = []

        class _Sig:
            def subscribe(self_, node, cb, immediate=False):
                return None

        self.theme_changed_signal = _Sig()

    @property
    def current_theme(self):
        return self._theme

    def set_interval(self, secs, cb):
        self.intervals.append((secs, cb))
        return _FakeTimer()


class _FakeTimer:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


@pytest.fixture
def captured_writes(monkeypatch):
    writes = []
    monkeypatch.setattr(T, "_write_raw", lambda s: writes.append(s))
    monkeypatch.setattr(T.atexit, "register", lambda *a, **k: None)
    return writes


def test_inert_under_kill_switch(captured_writes, monkeypatch):
    monkeypatch.setenv(T.BG_SYNC_KILL_SWITCH_ENV, "1")
    monkeypatch.setattr(T, "_stdout_is_tty", lambda: True)
    T.install_terminal_bg_sync(_FakeApp("#0E0B14"))
    assert captured_writes == []  # nothing emitted when disabled


def test_inert_when_not_a_tty(captured_writes, monkeypatch):
    monkeypatch.delenv(T.BG_SYNC_KILL_SWITCH_ENV, raising=False)
    monkeypatch.setattr(T, "_stdout_is_tty", lambda: False)
    T.install_terminal_bg_sync(_FakeApp("#0E0B14"))
    assert captured_writes == []


def test_emits_surface_once_and_only_on_change(captured_writes, monkeypatch):
    monkeypatch.delenv(T.BG_SYNC_KILL_SWITCH_ENV, raising=False)
    monkeypatch.setattr(T, "_stdout_is_tty", lambda: True)
    app = _FakeApp("#0E0B14")
    sync = T.install_terminal_bg_sync(app)
    assert captured_writes == ["\x1b]11;#0E0B14\x07"]  # emitted on install
    sync._emit()  # same surface → no new write
    assert captured_writes == ["\x1b]11;#0E0B14\x07"]
    app._theme = _Theme(surface="#202028")  # theme switched
    sync._emit()
    assert captured_writes[-1] == "\x1b]11;#202028\x07"
    # a poll timer was registered as the fallback, at the documented cadence
    assert app.intervals and app.intervals[0][0] == T.TerminalBackgroundSync.POLL_SECONDS


def test_restore_is_idempotent(captured_writes, monkeypatch):
    monkeypatch.delenv(T.BG_SYNC_KILL_SWITCH_ENV, raising=False)
    monkeypatch.setattr(T, "_stdout_is_tty", lambda: True)
    sync = T.install_terminal_bg_sync(_FakeApp("#0E0B14"))
    captured_writes.clear()
    sync._restore()
    sync._restore()
    assert captured_writes == ["\x1b]111\x07"]  # reset emitted exactly once


def test_stop_stops_timer_and_restores(captured_writes, monkeypatch):
    monkeypatch.delenv(T.BG_SYNC_KILL_SWITCH_ENV, raising=False)
    monkeypatch.setattr(T, "_stdout_is_tty", lambda: True)
    app = _FakeApp("#0E0B14")
    sync = T.install_terminal_bg_sync(app)
    captured_writes.clear()
    sync.stop()
    assert captured_writes == ["\x1b]111\x07"]
