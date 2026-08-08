"""patcher.py — anchored, idempotent patches for Workstream M (command
palette -> scrollable popup + observability/security/emotions strips).

Every patch is a small, uniquely-anchored span replacement against the
CURRENT live app.py text (4,894 lines) rather than a full-file replace —
same discipline as aria-dual-inbox's patcher, for the same reason: this
file evolves fast and a full-file replace risks losing unrelated content.
"""
from __future__ import annotations

MARK = "command-menu-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. import the new screen ────────────────────────────────────────────────

IMPORT_ANCHOR = (
    "try:\n"
    "    from .apply_queue_screen import ApplyQueueScreen  # apply-queue-import-d\n"
    "except Exception:  # pragma: no cover — apply queue is strictly optional\n"
    "    ApplyQueueScreen = None  # type: ignore[assignment,misc]\n"
)

IMPORT_NEW = (
    IMPORT_ANCHOR
    + "\n"
    + f"try:  # {MARK}\n"
    + "    from .command_palette_screen import CommandPaletteScreen\n"
    + "except Exception:  # pragma: no cover — command palette popup is strictly optional\n"
    + "    CommandPaletteScreen = None  # type: ignore[assignment,misc]\n"
)


# ── 2. key binding ───────────────────────────────────────────────────────────

BINDING_ANCHOR = (
    '        Binding("ctrl+shift+a", "apply_queue", "apply-queue", show=False, priority=True),'
    "  # apply-queue-binding-d\n"
)
BINDING_NEW = (
    BINDING_ANCHOR
    + f'        Binding("ctrl+m", "command_palette", "commands", show=True, priority=True),  # {MARK}\n'
)


# ── 3. action method ─────────────────────────────────────────────────────────

ACTION_ANCHOR = (
    "    def action_apply_queue(self) -> None:  # apply-queue-action-d\n"
    '        """Ctrl+Shift+A → multi-select staged modules into the durable apply queue."""\n'
    "        if ApplyQueueScreen is None:  # pragma: no cover\n"
    "            return\n"
    "        if isinstance(self.screen, ApplyQueueScreen):\n"
    "            self.pop_screen(); return\n"
    "        try:\n"
    "            from pathlib import Path\n"
    "            import sovereign_agent\n"
    "            repo_root = Path(sovereign_agent.__file__).parents[3]\n"
    "            self.push_screen(ApplyQueueScreen(repo_root))\n"
    "        except Exception as exc:  # noqa: BLE001\n"
    "            logger.warning('apply-queue screen failed: %r', exc)\n"
)

ACTION_NEW = (
    ACTION_ANCHOR
    + f"\n    def action_command_palette(self) -> None:  # {MARK}\n"
    + '        """Ctrl+M / "☰ commands" button → scrollable command popup."""\n'
    + "        if CommandPaletteScreen is None:  # pragma: no cover\n"
    + "            return\n"
    + "        if isinstance(self.screen, CommandPaletteScreen):\n"
    + "            self.pop_screen(); return\n"
    + "        try:\n"
    + "            self.push_screen(CommandPaletteScreen())\n"
    + "        except Exception as exc:  # noqa: BLE001\n"
    + "            logger.warning('command-palette screen failed: %r', exc)\n"
)


# ── 4. compose(): three palette rows -> one row + 3 strips ──────────────────

COMPOSE_ANCHOR = (
    '        _row1 = PALETTE_COMMANDS[0:7]\n'
    '        _row2 = PALETTE_COMMANDS[7:14]\n'
    '        _row3 = PALETTE_COMMANDS[14:]\n'
    '        with Horizontal(id="palette-row"):\n'
    '            for palette_cmd in _row1:\n'
    '                yield CommandButton(palette_cmd)\n'
    '        if _row2:\n'
    '            with Horizontal(id="palette-row-2"):\n'
    '                for palette_cmd in _row2:\n'
    '                    yield CommandButton(palette_cmd)\n'
    '        with Horizontal(id="palette-row-3"):\n'
    '            for palette_cmd in _row3:\n'
    '                yield CommandButton(palette_cmd)\n'
    '            # flexible gap pushes the reference buttons to the right edge\n'
    '            yield Static("", classes="palette-spacer")\n'
    '            for ref_cmd in REFERENCE_BUTTONS:\n'
    '                yield CommandButton(ref_cmd)\n'
)

COMPOSE_NEW = (
    f"        # {MARK} — the palette collapsed into one button + a scrollable\n"
    '        # popup (CommandPaletteScreen); the freed rows now carry 3 live\n'
    '        # strips (sentinel health / security posture / emotional state).\n'
    '        with Horizontal(id="palette-row"):\n'
    '            yield Button("\\u2630 commands", id="palette-menu-btn")\n'
    '            yield Static("", id="observability-strip", classes="cockpit-strip")\n'
    '            yield Static("", id="security-strip", classes="cockpit-strip")\n'
    '            yield Static("", id="emotions-strip", classes="cockpit-strip")\n'
)


# ── 5. CSS: simplify per-row selectors to plain CommandButton, add strip CSS ─

CSS_ANCHOR = (
    "    #palette-row, #palette-row-2, #palette-row-3 {\n"
    "        height: 3;\n"
    "        width: 100%;\n"
    "        margin: 1 0 0 0;\n"
    "        padding: 0;\n"
    "        background: $surface;\n"
    "        layout: horizontal;\n"
    "    }\n"
    "    #palette-row-2 {\n"
    "        margin: 0 0 0 0;\n"
    "    }\n"
    "    #palette-row-3 {\n"
    "        margin: 0 0 0 0;\n"
    "    }\n"
    "    #palette-row CommandButton, #palette-row-2 CommandButton, #palette-row-3 CommandButton {\n"
    "        height: 3;\n"
    "        min-width: 10;\n"
    "        margin: 0 1 0 0;\n"
    "        padding: 0 1;\n"
    "        border: round $primary;\n"
    "        background: $surface;\n"
    "        color: $text;\n"
    "    }\n"
    "    /* Gentle focus: brighten the border only — never a filled (white) box that\n"
    "       looks stuck. Pairs with returning focus to the input after a click. */\n"
    "    #palette-row CommandButton:focus, #palette-row-2 CommandButton:focus, #palette-row-3 CommandButton:focus {\n"
    "        border: round $accent;\n"
    "        background: $surface;\n"
    "        color: $text;\n"
    "        text-style: none;\n"
    "    }\n"
    "    /* CSS class applied briefly on click — operator feedback */\n"
    "    #palette-row CommandButton.flash, #palette-row-2 CommandButton.flash, #palette-row-3 CommandButton.flash {\n"
    "        border: round $success;\n"
    "        background: $success 20%;\n"
    "        color: $success;\n"
    "    }\n"
    "    /* cockpit-god-d — Aria active: button glows when Aria uses the mapped tool */\n"
    "    #palette-row CommandButton.aria-active,\n"
    "    #palette-row-2 CommandButton.aria-active,\n"
    "    #palette-row-3 CommandButton.aria-active {\n"
    "        border: round $warning;\n"
    "        background: $warning 20%;\n"
    "        color: $warning;\n"
    "    }\n"
    "    /* CSS class applied while a matching subprocess is running */\n"
    "    #palette-row CommandButton.running, #palette-row-2 CommandButton.running, #palette-row-3 CommandButton.running {\n"
    "        border: round $accent;\n"
    "        background: $accent 15%;\n"
    "        color: $accent;\n"
    "    }\n"
    "    /* Flexible gap on the last palette row: expands to push the\n"
    "       reference buttons (legend / help) to the right edge. */\n"
    "    .palette-spacer {\n"
    "        width: 1fr;\n"
    "        height: 3;\n"
    "        background: $surface;\n"
    "    }\n"
)

CSS_NEW = (
    f"    /* {MARK} — one palette row now: the commands trigger button + 3\n"
    "       live strips. CommandButton's visual states apply globally (it now\n"
    "       lives both here — none remain directly in this row — and inside\n"
    "       CommandPaletteScreen's popup list). */\n"
    "    #palette-row {\n"
    "        height: 3;\n"
    "        width: 100%;\n"
    "        margin: 1 0 0 0;\n"
    "        padding: 0;\n"
    "        background: $surface;\n"
    "        layout: horizontal;\n"
    "    }\n"
    '    #palette-menu-btn {\n'
    "        height: 3;\n"
    "        min-width: 14;\n"
    "        margin: 0 1 0 0;\n"
    "        padding: 0 1;\n"
    "        border: round $primary;\n"
    "        background: $surface;\n"
    "        color: $text;\n"
    "    }\n"
    "    .cockpit-strip {\n"
    "        height: 3;\n"
    "        width: 1fr;\n"
    "        margin: 0 1 0 0;\n"
    "        padding: 1 1 0 1;\n"
    "        border: round $surface-lighten-2;\n"
    "        color: $text-muted;\n"
    "    }\n"
    "    CommandButton {\n"
    "        height: 3;\n"
    "        min-width: 10;\n"
    "        margin: 0 1 0 0;\n"
    "        padding: 0 1;\n"
    "        border: round $primary;\n"
    "        background: $surface;\n"
    "        color: $text;\n"
    "    }\n"
    "    /* Gentle focus: brighten the border only — never a filled (white) box that\n"
    "       looks stuck. Pairs with returning focus to the input after a click. */\n"
    "    CommandButton:focus {\n"
    "        border: round $accent;\n"
    "        background: $surface;\n"
    "        color: $text;\n"
    "        text-style: none;\n"
    "    }\n"
    "    /* CSS class applied briefly on click — operator feedback */\n"
    "    CommandButton.flash {\n"
    "        border: round $success;\n"
    "        background: $success 20%;\n"
    "        color: $success;\n"
    "    }\n"
    "    /* cockpit-god-d — Aria active: button glows when Aria uses the mapped tool */\n"
    "    CommandButton.aria-active {\n"
    "        border: round $warning;\n"
    "        background: $warning 20%;\n"
    "        color: $warning;\n"
    "    }\n"
    "    /* CSS class applied while a matching subprocess is running */\n"
    "    CommandButton.running {\n"
    "        border: round $accent;\n"
    "        background: $accent 15%;\n"
    "        color: $accent;\n"
    "    }\n"
)


# ── 6. on_mount: register the strips' refresh timer ──────────────────────────

MOUNT_ANCHOR = (
    "        self.set_interval(8.0, self._refresh_inbox_pane)\n"
    "        self.call_after_refresh(self._refresh_inbox_pane)\n"
)
MOUNT_NEW = (
    MOUNT_ANCHOR
    + f"\n        # {MARK} — the 3 palette-row strips, same 8s cadence as inbox.\n"
    + "        self.set_interval(8.0, self._refresh_cockpit_strips)\n"
    + "        self.call_after_refresh(self._refresh_cockpit_strips)\n"
)


# ── 7. on_button_pressed: auto-close the popup on any command click ────────

ON_BUTTON_PRESSED_ANCHOR = (
    "        button = event.button\n"
    "        # v0.2.41 — inline glyph picker buttons (Ctrl-G strip). Insert the\n"
)
ON_BUTTON_PRESSED_NEW = (
    "        button = event.button\n"
    f"        # {MARK} — a click on any CommandButton while the popup is open\n"
    "        # closes it first, so the paste/action logic below always runs\n"
    "        # against the base screen (matches the historical direct-click\n"
    "        # behavior exactly — just with one extra pop first).\n"
    "        if (\n"
    "            CommandPaletteScreen is not None\n"
    "            and isinstance(self.screen, CommandPaletteScreen)\n"
    "            and isinstance(button, CommandButton)\n"
    "        ):\n"
    "            self.pop_screen()\n"
    "        # v0.2.41 — inline glyph picker buttons (Ctrl-G strip). Insert the\n"
)


# ── 7b. FIX: the "☰ commands" button itself never opened the popup ─────────
# Real bug found live (Kevin caught it): `on_button_pressed` only acts on
# CommandButton instances (the early `if not isinstance(button, CommandButton):
# return` a few lines down) — but the "☰ commands" trigger is a plain
# Button (id="palette-menu-btn"), so clicking it hit that early return and
# did nothing. Ctrl+M (the key binding) called action_command_palette()
# directly and worked; the button never did. Missed because every test in
# this module called action_command_palette() directly to open the popup
# and never actually clicked the trigger button itself — a real gap in test
# coverage, not just in the patch.

MENU_BTN_MARK = "command-menu-btn-fix-d"

MENU_BTN_FIX_ANCHOR = (
    "        button = event.button\n"
    f"        # {MARK} — a click on any CommandButton while the popup is open\n"
)
MENU_BTN_FIX_NEW = (
    "        button = event.button\n"
    f"        # {MENU_BTN_MARK} — the trigger button itself is a plain Button,\n"
    "        # not a CommandButton, so it must be handled before the\n"
    "        # CommandButton-only logic below (which would otherwise ignore it).\n"
    '        if getattr(button, "id", None) == "palette-menu-btn":\n'
    "            self.action_command_palette()\n"
    "            return\n"
    f"        # {MARK} — a click on any CommandButton while the popup is open\n"
)


def patch_menu_button_click(text: str) -> tuple[str, bool]:
    if MENU_BTN_MARK in text:
        return text, False
    new_text = _replace_once(
        text, MENU_BTN_FIX_ANCHOR, MENU_BTN_FIX_NEW, label="menu button click fix anchor"
    )
    return new_text, True


# ── 9. missing-button audit: 3 genuinely missing, already-safe commands ─────
# (a 4th candidate — quarantine review — needs a `sov apply-queue` CLI
# wrapper first, since it's currently only a `python -m` entry point with
# no `sov`-prefixed form; normalize_sov_prefix only recognizes `sov`/
# `sovereign`-prefixed input, so a `python -m ...` palette command would be
# silently misrouted to the chat pipeline instead of executing. Deferred,
# not silently dropped — named in the module README.)

PALETTE_COMMANDS_ANCHOR = (
    '    PaletteCommand("vault",    "sov vault status",                 "vault",\n'
    '                   "Owner encryption vault status (never shows the key)"),\n'
    ")\n"
)
PALETTE_COMMANDS_NEW = (
    f'    PaletteCommand("vault",    "sov vault status",                 "vault",\n'
    f'                   "Owner encryption vault status (never shows the key)"),\n'
    f'    # {MARK} — 3 commands found missing by the palette gap-audit: each\n'
    f'    # was already a real, registered, safe `sov` command with zero\n'
    f'    # palette presence.\n'
    f'    PaletteCommand("sentinels", "sov sentinels scan",              "sentinels",\n'
    f'                   "Scan every registered sentinel — health status at a glance"),\n'
    f'    PaletteCommand("dreams",   "sov dream list",                   "dream-list",\n'
    f'                   "List all dream sessions (pre-approved safe subcommand)"),\n'
    f'    PaletteCommand("all-asks", "sov requests list --all",          "requests-all",\n'
    f'                   "Every request ever filed — full history, not just open"),\n'
    ")\n"
)


# ── 10. sentinels allowlist fix ──────────────────────────────────────────────
# `sentinels` was a real, registered typer app with NO entry in
# _KNOWN_SOV_SUBCOMMANDS — meaning a typed `sov sentinels scan` didn't even
# auto-execute. Found by the same gap-audit as the 3 new buttons above.

SUBCMD_ANCHOR = (
    '    # v0.2.36.0+ — collaboration inbox, capability awareness, owner vault\n'
    '    "requests", "capabilities", "vault",\n'
)
SUBCMD_NEW = (
    SUBCMD_ANCHOR
    + f"    # {MARK} — sentinels was missing entirely (gap-audit finding)\n"
    + '    "sentinels",\n'
)


# ── 11. fix a real, pre-existing flake found while testing this workstream ──
# `_check_sentinel_transitions` compares against `self._prev_sentinel_states.
# get(sid, "ok")` — on the VERY FIRST call each session, every sentinel is
# implicitly compared against an assumed "ok" baseline it never actually had,
# so a freshly-started cockpit with any non-"ok" sentinel (normal on a fresh/
# empty data dir — confirmed via test_cockpit.py's isolated tmp_path) fires a
# spurious "regression" alert into chat on first read. This was already
# latent; adding the 3 strips' own call_after_refresh at mount shifted enough
# scheduling timing to make tests/test_cockpit.py::test_clear_chat_binding
# flake on it (alerts landing after the test's clear rather than before).
# Root-cause fix, not a timing workaround: seed the baseline silently on the
# first call — you cannot regress from a state you never observed.

SENTINEL_TRANSITIONS_ANCHOR = (
    '    def _check_sentinel_transitions(self) -> None:  # sentinel-chat-method-d\n'
    '        """Compare current sentinel states to previous; emit chat alerts on change."""\n'
    "        try:\n"
    "            from sovereign_agent.config import SETTINGS\n"
    "            from sovereign_agent.stewardship.registry import gather_health\n"
    "            statuses = gather_health(SETTINGS.paths.data_dir)\n"
    "        except Exception:\n"
    "            return\n"
    "\n"
    '        WORSE = {"ok": 0, "warning": 1, "error": 2, "unknown": 1}\n'
    "        new_states: dict[str, str] = {h.sentinel_id: str(h.level) for h in statuses}\n"
    "\n"
    "        for sid, level in new_states.items():\n"
)

SENTINEL_TRANSITIONS_NEW = (
    '    def _check_sentinel_transitions(self) -> None:  # sentinel-chat-method-d\n'
    '        """Compare current sentinel states to previous; emit chat alerts on change."""\n'
    "        try:\n"
    "            from sovereign_agent.config import SETTINGS\n"
    "            from sovereign_agent.stewardship.registry import gather_health\n"
    "            statuses = gather_health(SETTINGS.paths.data_dir)\n"
    "        except Exception:\n"
    "            return\n"
    "\n"
    '        WORSE = {"ok": 0, "warning": 1, "error": 2, "unknown": 1}\n'
    "        new_states: dict[str, str] = {h.sentinel_id: str(h.level) for h in statuses}\n"
    "\n"
    f"        # {MARK} — first call each session: seed the baseline silently.\n"
    "        # There is no real 'regression' from a state that was never\n"
    "        # actually observed — comparing against an assumed 'ok' default\n"
    "        # produced spurious alerts on a fresh/empty data dir.\n"
    "        if not self._prev_sentinel_states:\n"
    "            self._prev_sentinel_states = new_states\n"
    "            return\n"
    "\n"
    "        for sid, level in new_states.items():\n"
)


# ── 8. new refresh methods for the 3 strips ─────────────────────────────────

REFRESH_METHODS_ANCHOR = "    def _refresh_memory_pane(self) -> None:\n"

REFRESH_METHODS_NEW = f'''    def _refresh_cockpit_strips(self) -> None:  # {MARK}
        """Refresh the 3 palette-row strips: sentinel health, security
        posture, and Aria's current emotional state. Each degrades to a
        short dim placeholder on any failure — never blocks cockpit boot,
        matches _refresh_inbox_pane's own failure discipline."""
        self._refresh_observability_strip()
        self._refresh_security_strip()
        self._refresh_emotions_strip()

    def _refresh_observability_strip(self) -> None:  # {MARK}
        try:
            strip = self.query_one("#observability-strip", Static)
        except Exception:  # noqa: BLE001
            return
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.stewardship.registry import gather_health
            statuses = gather_health(SETTINGS.paths.data_dir)
            n_ok = sum(1 for s in statuses if s.level == "ok")
            n_warn = sum(1 for s in statuses if s.level == "warning")
            n_err = sum(1 for s in statuses if s.level == "error")
            color = "$error" if n_err else ("$warning" if n_warn else "$success")
            strip.update(
                f"[dim]◊ sentinels[/dim]\\n"
                f"[{{color}}]{{n_ok}} ok · {{n_warn}} warn · {{n_err}} err[/{{color}}]"
            )
        except Exception as exc:  # noqa: BLE001
            strip.update(f"[dim]◊ sentinels\\n(unavailable: {{type(exc).__name__}})[/dim]")

    def _refresh_security_strip(self) -> None:  # {MARK}
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
            strip.update(
                f"[dim]◊ security[/dim]\\n"
                f"T3: {{t3}} tools · eval sandboxed {{eval_mark}}"
            )
        except Exception as exc:  # noqa: BLE001
            strip.update(f"[dim]◊ security\\n(unavailable: {{type(exc).__name__}})[/dim]")

    def _refresh_emotions_strip(self) -> None:  # {MARK}
        try:
            strip = self.query_one("#emotions-strip", Static)
        except Exception:  # noqa: BLE001
            return
        try:
            from sovereign_agent.emotion import derive_emotions, emotion_to_mood
            state = derive_emotions()
            mood = emotion_to_mood(state)
            strip.update(
                f"[dim]◊ aria feels[/dim]\\n"
                f"{{mood}} [dim](focus {{state.focus:.1f}} · care {{state.care:.1f}})[/dim]"
            )
        except Exception as exc:  # noqa: BLE001
            strip.update(f"[dim]◊ aria feels\\n(unavailable: {{type(exc).__name__}})[/dim]")

    def _refresh_memory_pane(self) -> None:
'''


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, IMPORT_ANCHOR, IMPORT_NEW, label="import anchor")
    text = _replace_once(text, BINDING_ANCHOR, BINDING_NEW, label="binding anchor")
    text = _replace_once(text, ACTION_ANCHOR, ACTION_NEW, label="action anchor")
    text = _replace_once(text, COMPOSE_ANCHOR, COMPOSE_NEW, label="compose anchor")
    text = _replace_once(text, CSS_ANCHOR, CSS_NEW, label="css anchor")
    text = _replace_once(text, MOUNT_ANCHOR, MOUNT_NEW, label="mount anchor")
    text = _replace_once(
        text, ON_BUTTON_PRESSED_ANCHOR, ON_BUTTON_PRESSED_NEW, label="on_button_pressed anchor"
    )
    text, _ = patch_menu_button_click(text)
    text = _replace_once(
        text, REFRESH_METHODS_ANCHOR, REFRESH_METHODS_NEW, label="refresh methods anchor"
    )
    text = _replace_once(
        text, PALETTE_COMMANDS_ANCHOR, PALETTE_COMMANDS_NEW, label="palette commands anchor"
    )
    text = _replace_once(text, SUBCMD_ANCHOR, SUBCMD_NEW, label="known subcommands anchor")
    text = _replace_once(
        text, SENTINEL_TRANSITIONS_ANCHOR, SENTINEL_TRANSITIONS_NEW,
        label="sentinel transitions first-call anchor",
    )
    return text, True
