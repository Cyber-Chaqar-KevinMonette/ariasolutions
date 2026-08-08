"""patcher.py — Workstream M follow-up: wire the security strip to J's real
Tier-A scanner findings, now that J is live (it wasn't yet when M was first
built earlier this session — a genuine gap found during the plan's own
accuracy review). Anchored span patches against the CURRENT live app.py,
same discipline as every other patcher this session.

`scan_tree()` walks all ~450 files under src/ and takes ~3s — far too slow
to run inline on the strip's existing 8s refresh timer (it would visibly
stall the cockpit's event loop). So this adds a SEPARATE, infrequent
(5-minute) background worker (`thread=True`, mirroring `_refresh_status_
worker`'s own pattern) that runs the scan off the main thread and caches
the result; the fast 8s strip refresh only ever reads the cache.

REVISED TWICE after a real regression was found live (Kevin's own instinct
to double-check paid off):

  1st pass: the cache/running-flag were INSTANCE attributes, so every
  separate `CockpitApp()` in the same process (normal in production — only
  ever one — but common in the test suite, which boots many short-lived
  cockpit instances back to back) spawned its OWN independent scan thread.
  Fixed by moving to a module-level cache + `threading.Lock`, so every
  CockpitApp in the process shares one scan result and only one scan thread
  ever runs at a time, no matter how many instances exist. This is a real
  improvement regardless of tests: the scan result describes process/
  filesystem state (what live src/ looks like), not per-instance state.

  2nd pass: the module-level lock alone did NOT fully fix it (confirmed by
  re-running the same bisection that reproduced the bug — still failed).
  The deeper issue: Textual's `thread=True` workers dispatch via `asyncio`'s
  `loop.run_in_executor(None, ...)` — a real `ThreadPoolExecutor` thread.
  Cancellation only stops the ASYNC side from awaiting the result; the
  underlying OS thread runs `scan_tree()` (CPU-bound, ~3s) to completion
  regardless, competing for the GIL with whatever pytest is doing next. The
  root fix: stop kicking off an immediate scan on every mount at all — rely
  purely on the 5-minute `set_interval`, which simply never fires during a
  short pytest `run_test()` window. Confirmed via the same bisection: the
  bug reproduces ONLY when something triggers an eager scan on mount;
  removing that trigger (keeping only the periodic timer) closes it for
  real, not just for the specific case this session happened to test.
"""
from __future__ import annotations

MARK = "security-strip-wire-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. module-level cache + lock (near the top of the file, with `logger`) ──

MODULE_STATE_ANCHOR = (
    "logger = logging.getLogger(__name__)\n"
)
MODULE_STATE_NEW = (
    MODULE_STATE_ANCHOR
    + f"\n# {MARK} — process-wide Tier-A scanner cache for the security strip.\n"
    + "# Module-level, not per-instance: the scan result describes live src/ on\n"
    + "# disk, not anything specific to one CockpitApp — sharing it means every\n"
    + "# cockpit instance in the process (normally just one; several in the test\n"
    + "# suite, which boots many short-lived instances back to back) reads the\n"
    + "# same cache and, critically, only ever runs ONE scan thread process-wide\n"
    + "# at a time, instead of each instance spawning its own competing thread.\n"
    + "_SECURITY_SCAN_CACHE: dict | None = None\n"
    + "_SECURITY_SCAN_LOCK = threading.Lock()\n"
    + "_SECURITY_SCAN_RUNNING = False\n"
)


# ── 2. ensure `import threading` is present ─────────────────────────────────

THREADING_IMPORT_ANCHOR = "import subprocess\nimport time\n"
THREADING_IMPORT_NEW = "import subprocess\nimport threading\nimport time\n"


# ── 3. on_mount: register the 5-minute scan-refresh timer ───────────────────

MOUNT_ANCHOR = (
    "        # command-menu-d — the 3 palette-row strips, same 8s cadence as inbox.\n"
    "        self.set_interval(8.0, self._refresh_cockpit_strips)\n"
    "        self.call_after_refresh(self._refresh_cockpit_strips)\n"
)
MOUNT_NEW = (
    MOUNT_ANCHOR
    + f"\n        # {MARK} — a full Tier-A scan is far too slow for the 8s strip\n"
    + "        # cadence above; refresh the process-wide cache in the background\n"
    + "        # every 5 minutes instead. Deliberately NOT kicked off immediately on\n"
    + "        # mount (an earlier version of this fix did, and a real regression\n"
    + "        # was found live: Textual's thread=True workers dispatch to a real\n"
    + "        # ThreadPoolExecutor — once started, the thread runs scan_tree() to\n"
    + "        # completion no matter what; cancellation only stops the async side\n"
    + "        # from awaiting it, never the thread itself. A test suite that boots\n"
    + "        # many CockpitApp instances rapidly triggered many such threads,\n"
    + "        # whose real CPU-bound work genuinely starved the GIL enough to break\n"
    + "        # unrelated, timing-sensitive tests elsewhere in the suite — confirmed\n"
    + "        # by bisection. Relying purely on the 300s interval means the scan\n"
    + "        # never fires during a short-lived test at all; the strip shows its\n"
    + "        # graceful interim fallback for the first 5 minutes of a real session,\n"
    + "        # which is an acceptable, honest UX tradeoff for a security posture\n"
    + "        # widget, not a broken/blank one.\n"
    + "        self.set_interval(300.0, self._maybe_run_security_scan)\n"
)


# ── 4. new worker + trigger methods, right before _refresh_cockpit_strips ──

STRIPS_METHOD_ANCHOR = (
    "    def _refresh_cockpit_strips(self) -> None:  # command-menu-d\n"
)
STRIPS_METHOD_NEW = f'''    def _maybe_run_security_scan(self) -> None:  # {MARK}
        """Kick off the background Tier-A scan if one isn't already running
        ANYWHERE in this process (module-level guard, not per-instance — see
        the docstring on _SECURITY_SCAN_CACHE above). Only ever called from
        the 300s periodic timer, never from mount directly — see the module
        docstring's "2nd pass" note on why an eager on-mount kickoff was
        removed (it's what caused the real GIL-contention regression)."""
        global _SECURITY_SCAN_RUNNING
        with _SECURITY_SCAN_LOCK:
            if _SECURITY_SCAN_RUNNING:
                return
            _SECURITY_SCAN_RUNNING = True
        self._run_security_scan_worker()

    @work(exclusive=True, group="security-scan", thread=True)  # {MARK}
    def _run_security_scan_worker(self) -> None:
        """Runs scan_tree() off the main thread — ~3s over ~450 files. Only
        ever updates the process-wide cache; every cockpit instance's 8s
        strip refresh just reads it."""
        global _SECURITY_SCAN_CACHE, _SECURITY_SCAN_RUNNING
        try:
            from pathlib import Path

            from sovereign_agent.scanner_tier_a.scanner import scan_tree
            import sovereign_agent

            src_root = Path(sovereign_agent.__file__).parent
            result = scan_tree(src_root)
            _SECURITY_SCAN_CACHE = {{
                "blocks": len(result.blocks),
                "warns": len(result.warns),
                "files_scanned": result.files_scanned,
            }}
        except Exception:  # noqa: BLE001 — cache just stays stale/empty on failure
            pass
        finally:
            with _SECURITY_SCAN_LOCK:
                _SECURITY_SCAN_RUNNING = False

    def _refresh_cockpit_strips(self) -> None:  # command-menu-d
'''


# ── 5. rewrite _refresh_security_strip to blend in the cached scan ─────────

SECURITY_STRIP_ANCHOR = (
    "    def _refresh_security_strip(self) -> None:  # command-menu-d\n"
    "        try:\n"
    '            strip = self.query_one("#security-strip", Static)\n'
    "        except Exception:  # noqa: BLE001\n"
    "            return\n"
    "        try:\n"
    "            from sovereign_agent.authority import tools_available_in_mode\n"
    "            from sovereign_agent.modes import Mode\n"
    "            all_tools = tools_available_in_mode(Mode.ONESHOT)  # ceiling 3 == everything\n"
    "            tiers: dict[int, int] = {}\n"
    "            for meta in all_tools:\n"
    '                tiers[meta.tier] = tiers.get(meta.tier, 0) + 1\n'
    '            t3 = tiers.get(3, 0)\n'
    "            eval_sandboxed = True\n"
    "            try:\n"
    "                from sovereign_agent.workflow import safe_eval  # noqa: F401\n"
    "            except Exception:  # noqa: BLE001\n"
    "                eval_sandboxed = False\n"
    '            eval_mark = "[green]✓[/green]" if eval_sandboxed else "[red]✗[/red]"\n'
    "            strip.update(\n"
    '                f"[dim]◊ security[/dim]\\n"\n'
    '                f"T3: {t3} tools · eval sandboxed {eval_mark}"\n'
    "            )\n"
    "        except Exception as exc:  # noqa: BLE001\n"
    '            strip.update(f"[dim]◊ security\\n(unavailable: {type(exc).__name__})[/dim]")\n'
)

SECURITY_STRIP_NEW = f'''    def _refresh_security_strip(self) -> None:  # command-menu-d
        try:
            strip = self.query_one("#security-strip", Static)
        except Exception:  # noqa: BLE001
            return
        try:
            from sovereign_agent.authority import tools_available_in_mode
            from sovereign_agent.modes import Mode
            all_tools = tools_available_in_mode(Mode.ONESHOT)  # ceiling 3 == everything
            tiers: dict[int, int] = {{}}
            for meta in all_tools:
                tiers[meta.tier] = tiers.get(meta.tier, 0) + 1
            t3 = tiers.get(3, 0)
            eval_sandboxed = True
            try:
                from sovereign_agent.workflow import safe_eval  # noqa: F401
            except Exception:  # noqa: BLE001
                eval_sandboxed = False
            eval_mark = "[green]✓[/green]" if eval_sandboxed else "[red]✗[/red]"
            # {MARK} — J's real Tier-A scanner findings, once the process-wide
            # background scan has completed at least once; falls back to just
            # the tier census (the original interim design) until then.
            cache = _SECURITY_SCAN_CACHE
            if cache is not None:
                n_blocks, n_warns = cache["blocks"], cache["warns"]
                scan_color = "$error" if n_blocks else ("$warning" if n_warns else "$success")
                strip.update(
                    f"[dim]◊ security[/dim]\\n"
                    f"T3: {{t3}} · eval {{eval_mark}}\\n"
                    f"[{{scan_color}}]{{n_blocks}} block · {{n_warns}} warn[/{{scan_color}}]"
                )
            else:
                strip.update(
                    f"[dim]◊ security[/dim]\\n"
                    f"T3: {{t3}} tools · eval sandboxed {{eval_mark}}"
                )
        except Exception as exc:  # noqa: BLE001
            strip.update(f"[dim]◊ security\\n(unavailable: {{type(exc).__name__}})[/dim]")
'''


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    if "\nimport threading\n" not in text:
        text = _replace_once(
            text, THREADING_IMPORT_ANCHOR, THREADING_IMPORT_NEW, label="threading import anchor"
        )
    text = _replace_once(text, MODULE_STATE_ANCHOR, MODULE_STATE_NEW, label="module state anchor")
    text = _replace_once(text, MOUNT_ANCHOR, MOUNT_NEW, label="mount anchor")
    text = _replace_once(text, STRIPS_METHOD_ANCHOR, STRIPS_METHOD_NEW, label="strips method anchor")
    text = _replace_once(text, SECURITY_STRIP_ANCHOR, SECURITY_STRIP_NEW, label="security strip anchor")
    return text, True
