"""test_movie_clip_generation_release.py — _release_gpu_and_cpu_memory's
extra malloc_trim(0) step (2026-07-29 incident: RAM plateaued below the
clip threshold even after gc.collect() + empty_cache() because glibc
never handed the freed pipeline's pages back to the OS)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from sovereign_agent.movie_clip_generation import _release_gpu_and_cpu_memory


def test_release_calls_malloc_trim_via_libc():
    """torch's own import machinery also calls ctypes.CDLL internally (to
    load its shared libs), so assert on the libc.so.6 call specifically
    rather than call-count — the real behavior under test is "malloc_trim
    gets invoked," not "CDLL is called exactly once."""
    fake_libc = MagicMock()
    with patch("ctypes.CDLL", return_value=fake_libc) as cdll:
        _release_gpu_and_cpu_memory()
    assert any(call.args == ("libc.so.6",) for call in cdll.call_args_list)
    fake_libc.malloc_trim.assert_called_once_with(0)


def test_release_never_raises_when_libc_unavailable():
    """Non-glibc platforms (e.g. macOS) — ctypes.CDLL raising must never
    break the caller; this is a best-effort release, not a hard
    requirement."""
    with patch("ctypes.CDLL", side_effect=OSError("no libc.so.6 here")):
        _release_gpu_and_cpu_memory()  # must not raise


def test_release_never_raises_when_malloc_trim_missing():
    fake_libc = MagicMock()
    del fake_libc.malloc_trim  # simulate an attribute error on lookup
    fake_libc.malloc_trim = MagicMock(side_effect=AttributeError("no such symbol"))
    with patch("ctypes.CDLL", return_value=fake_libc):
        _release_gpu_and_cpu_memory()  # must not raise


def test_release_still_calls_gc_collect_and_empty_cache():
    with (
        patch("gc.collect") as gc_collect,
        patch("ctypes.CDLL", return_value=MagicMock()),
    ):
        _release_gpu_and_cpu_memory()
    gc_collect.assert_called_once()
