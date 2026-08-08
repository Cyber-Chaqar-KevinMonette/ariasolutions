"""patcher.py — Workstream I: the Vessel-Health strip.

A 4th palette-row strip rolling up kernel-coherence (H2), sentinel health +
drift (gather_health()), signal (H3's epistemic ledger), and flourishing
trend (C's apply-queue/quarantine) — see `vessel_health.py`'s own
docstring for the full reasoning behind each metric choice.

The kernel-coherence component runs a full-tree clause-citation scan
(~3s over ~450 files) — the SAME order of cost as J's Tier-A `scan_tree()`,
which is exactly what caused a real, 3-iteration regression earlier this
session (`aria-security-strip-wire`). This patcher deliberately reuses
that already-proven fix verbatim rather than re-deriving it: a module-
level cache + lock + a `@work(thread=True)` background worker, triggered
ONLY by a 300s periodic timer — never eagerly on `on_mount`. See
`_SECURITY_SCAN_CACHE`'s docstring in the live file for the full 3-
iteration story; this patcher does not repeat that investigation, it
just applies the lesson.

Anchored span patches against the CURRENT live app.py (same discipline as
every other patcher this session — not a full-file replace).
"""
from __future__ import annotations

MARK = "vessel-health-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. module-level cache + lock, sibling to _SECURITY_SCAN_CACHE ──────────

MODULE_STATE_ANCHOR = (
    "_SECURITY_SCAN_CACHE: dict | None = None\n"
    "_SECURITY_SCAN_LOCK = threading.Lock()\n"
    "_SECURITY_SCAN_RUNNING = False\n"
)
MODULE_STATE_NEW = (
    MODULE_STATE_ANCHOR
    + f"\n# {MARK} — process-wide cache for the vessel-health strip's kernel-\n"
    + "# coherence component (H2's clause-citation scan, same ~3s-over-~450-files\n"
    + "# cost class as J's Tier-A scan_tree() above). Same discipline as\n"
    + "# _SECURITY_SCAN_CACHE: module-level, not per-instance, and only ever\n"
    + "# triggered by the periodic timer, never eagerly on mount — see that\n"
    + "# cache's own docstring for the full 3-iteration regression story this\n"
    + "# mirrors rather than repeats.\n"
    + "_VESSEL_KERNEL_CACHE: dict | None = None\n"
    + "_VESSEL_KERNEL_LOCK = threading.Lock()\n"
    + "_VESSEL_KERNEL_RUNNING = False\n"
)


# ── 2. compose(): the 4th strip ─────────────────────────────────────────────

COMPOSE_ANCHOR = (
    '        with Horizontal(id="palette-row"):\n'
    '            yield Button("\\u2630 commands", id="palette-menu-btn")\n'
    '            yield Static("", id="observability-strip", classes="cockpit-strip")\n'
    '            yield Static("", id="security-strip", classes="cockpit-strip")\n'
    '            yield Static("", id="emotions-strip", classes="cockpit-strip")\n'
)
COMPOSE_NEW = (
    '        with Horizontal(id="palette-row"):\n'
    '            yield Button("\\u2630 commands", id="palette-menu-btn")\n'
    '            yield Static("", id="observability-strip", classes="cockpit-strip")\n'
    '            yield Static("", id="security-strip", classes="cockpit-strip")\n'
    '            yield Static("", id="emotions-strip", classes="cockpit-strip")\n'
    f'            yield Static("", id="vessel-strip", classes="cockpit-strip")  # {MARK}\n'
)


# ── 3. on_mount: register the periodic kernel-coherence background timer ──

MOUNT_ANCHOR = "        self.set_interval(300.0, self._maybe_run_security_scan)\n"
MOUNT_NEW = (
    MOUNT_ANCHOR
    + f"\n        # {MARK} — same discipline as the security scan directly above:\n"
    + "        # a full clause-citation scan is far too slow for the 8s strip\n"
    + "        # cadence; refresh the process-wide cache in the background every\n"
    + "        # 5 minutes instead, and deliberately NOT kicked off immediately on\n"
    + "        # mount (see _SECURITY_SCAN_CACHE's docstring above for the real,\n"
    + "        # 3-iteration regression this mirrors rather than repeats).\n"
    + "        self.set_interval(300.0, self._maybe_run_vessel_kernel_scan)\n"
)


# ── 4. new worker + trigger methods, right before _refresh_cockpit_strips ──

STRIPS_METHOD_ANCHOR = (
    "    def _refresh_cockpit_strips(self) -> None:  # command-menu-d\n"
    '        """Refresh the 3 palette-row strips: sentinel health, security\n'
    "        posture, and Aria's current emotional state. Each degrades to a\n"
    "        short dim placeholder on any failure — never blocks cockpit boot,\n"
    "        matches _refresh_inbox_pane's own failure discipline.\"\"\"\n"
    "        self._refresh_observability_strip()\n"
    "        self._refresh_security_strip()\n"
    "        self._refresh_emotions_strip()\n"
)
STRIPS_METHOD_NEW = f'''    def _maybe_run_vessel_kernel_scan(self) -> None:  # {MARK}
        """Kick off the background kernel-coherence scan if one isn't
        already running anywhere in this process (module-level guard,
        mirrors _maybe_run_security_scan exactly). Only ever called from
        the 300s periodic timer, never from mount directly."""
        global _VESSEL_KERNEL_RUNNING
        with _VESSEL_KERNEL_LOCK:
            if _VESSEL_KERNEL_RUNNING:
                return
            _VESSEL_KERNEL_RUNNING = True
        self._run_vessel_kernel_scan_worker()

    @work(exclusive=True, group="vessel-kernel-scan", thread=True)  # {MARK}
    def _run_vessel_kernel_scan_worker(self) -> None:
        """Runs H2's find_references() off the main thread — ~3s over
        ~450 files. Only ever updates the process-wide cache; every
        cockpit instance's 8s strip refresh just reads it."""
        global _VESSEL_KERNEL_CACHE, _VESSEL_KERNEL_RUNNING
        try:
            from pathlib import Path

            import sovereign_agent
            from sovereign_agent.canon_embodiment.mapper import find_references

            repo_root = Path(sovereign_agent.__file__).parent.parent.parent
            report = find_references(repo_root)
            ratio = (
                report.embodied_count / report.total_clauses
                if report.total_clauses else 0.0
            )
            _VESSEL_KERNEL_CACHE = {{"ratio": ratio, "summary": report.summary()}}
        except Exception:  # noqa: BLE001 — cache just stays stale/empty on failure
            pass
        finally:
            with _VESSEL_KERNEL_LOCK:
                _VESSEL_KERNEL_RUNNING = False

    def _refresh_cockpit_strips(self) -> None:  # command-menu-d
        """Refresh the 4 palette-row strips: sentinel health, security
        posture, Aria's current emotional state, and vessel health. Each
        degrades to a short dim placeholder on any failure — never blocks
        cockpit boot, matches _refresh_inbox_pane's own failure discipline."""
        self._refresh_observability_strip()
        self._refresh_security_strip()
        self._refresh_emotions_strip()
        self._refresh_vessel_strip()  # {MARK}
'''


# ── 5. new _refresh_vessel_strip method, right after _refresh_emotions_strip ──

EMOTIONS_STRIP_END_ANCHOR = (
    '    def _refresh_emotions_strip(self) -> None:  # command-menu-d\n'
    '        try:\n'
    '            strip = self.query_one("#emotions-strip", Static)\n'
    '        except Exception:  # noqa: BLE001\n'
    '            return\n'
    '        try:\n'
    '            from sovereign_agent.emotion import derive_emotions, emotion_to_mood\n'
    '            state = derive_emotions()\n'
    '            mood = emotion_to_mood(state)\n'
    '            strip.update(\n'
    '                f"[dim]◊ aria feels[/dim]\\n"\n'
    '                f"{mood} [dim](focus {state.focus:.1f} · care {state.care:.1f})[/dim]"\n'
    '            )\n'
    '        except Exception as exc:  # noqa: BLE001\n'
    '            strip.update(f"[dim]◊ aria feels\\n(unavailable: {type(exc).__name__})[/dim]")\n'
)
VESSEL_STRIP_METHOD = f'''
    def _refresh_vessel_strip(self) -> None:  # {MARK}
        """Workstream I: rolls up sentinel health/drift, H3's epistemic
        signal, and C's flourishing trend on the normal 8s cadence
        (all cheap reads); kernel-coherence (H2, expensive) is read from
        the process-wide cache populated by the 300s background worker
        above, falling back to "(not yet scanned)" until the first run
        completes — never blank, never blocks cockpit boot."""
        try:
            strip = self.query_one("#vessel-strip", Static)
        except Exception:  # noqa: BLE001
            return
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.vessel_health import gather_vessel_health

            report = gather_vessel_health(
                data_dir=SETTINGS.paths.data_dir, include_kernel_coherence=False,
            )
            cache = _VESSEL_KERNEL_CACHE
            if cache is not None:
                kc_line = f"kernel {{cache['ratio']:.0%}}"
            else:
                kc_line = "kernel (scanning…)"
            color = (
                "$error" if report.sentinel_error
                else ("$warning" if report.sentinel_warn else "$success")
            )
            sig = (
                f"{{report.signal_avg_confidence:.0%}}"
                if report.signal_avg_confidence is not None
                else "n/a"
            )
            strip.update(
                f"[dim]◊ vessel[/dim]\\n"
                f"[{{color}}]{{kc_line}} · signal {{sig}}[/{{color}}]\\n"
                f"[dim]{{report.flourishing_applied}} applied · "
                f"{{report.flourishing_quarantined}} quarantined[/dim]"
            )
        except Exception as exc:  # noqa: BLE001
            strip.update(f"[dim]◊ vessel\\n(unavailable: {{type(exc).__name__}})[/dim]")
'''


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, MODULE_STATE_ANCHOR, MODULE_STATE_NEW, label="module state anchor")
    text = _replace_once(text, COMPOSE_ANCHOR, COMPOSE_NEW, label="compose anchor")
    text = _replace_once(text, MOUNT_ANCHOR, MOUNT_NEW, label="mount anchor")
    text = _replace_once(text, STRIPS_METHOD_ANCHOR, STRIPS_METHOD_NEW, label="strips method anchor")
    text = _replace_once(
        text, EMOTIONS_STRIP_END_ANCHOR, EMOTIONS_STRIP_END_ANCHOR + VESSEL_STRIP_METHOD,
        label="vessel strip method anchor",
    )
    return text, True
