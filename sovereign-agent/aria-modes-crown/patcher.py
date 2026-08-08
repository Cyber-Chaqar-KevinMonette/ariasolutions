"""patcher.py — FABLE II M6: the modes crown.

Patches:
  1. tools/__init__.py     — register SetStanceTool + ObservatoryTool
  2. cockpit/app.py        — F2/F3 bindings, actions, /modes + /observatory
                             slash verbs, crown-name overlay in the status bar
  3. curiosity.py          — crown-aware autonomous wondering (companion
                             allows, focus/guardian mute; no crown = today)
  4. session_bridge.py     — the crown gate: non-work modes refuse sessions,
                             focus requires a garden, cool-down pauses NEW
                             dispatches (anchors on M5's lease wire)
  5. loop.py + tool_paging — THE CACHE/SIDE-EFFECT BUG (found by this
                             round's suite): a cached request_tools response
                             skipped the attach block — paging silently
                             broke on any repeated grant within the TTL.
                             Tools now opt out via `cacheable = False`.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "modes-crown-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. tools/__init__.py ─────────────────────────────────────────────────

# Follows the repo's own anchor-chain convention exactly (PLAYBOOK.md:
# "<name>-import-d" / "<name>-all-d") — not just the module-wide MARK —
# so path_scan's ships-tools/no-registration check (and any human reading
# the chain: foresight-import-d → modes-crown-import-d) recognizes it.
TOOLS_IMPORT_MARK = "modes-crown-import-d"

TOOLS_IMPORT_ANCHOR = ("from .foresight_tools import Foresight14GenTool, "
                       "UltimateQuestionTool  # foresight-import-d\n")
TOOLS_IMPORT_NEW = (
    TOOLS_IMPORT_ANCHOR
    + f"from .stance_tools import ObservatoryTool, SetStanceTool  # {TOOLS_IMPORT_MARK}\n"
)
TOOLS_ALL_ANCHOR = '    "Foresight14GenTool",  # foresight-all-d\n'
TOOLS_ALL_NEW = (
    TOOLS_ALL_ANCHOR
    + '    "SetStanceTool",  # modes-crown-all-d\n'
    + '    "ObservatoryTool",  # modes-crown-all-d\n'
)


def patch_tools_init(text: str) -> tuple[str, bool]:
    if TOOLS_IMPORT_MARK in text:
        return text, False
    text = _replace_once(text, TOOLS_IMPORT_ANCHOR, TOOLS_IMPORT_NEW,
                         label="tools import")
    text = _replace_once(text, TOOLS_ALL_ANCHOR, TOOLS_ALL_NEW,
                         label="tools __all__")
    return text, True


# ── 2. cockpit/app.py ────────────────────────────────────────────────────

BINDINGS_ANCHOR = ('        Binding("f1,question_mark", "help",  "help",    '
                   'show=True,  priority=True),\n    ]\n')
BINDINGS_NEW = (
    '        Binding("f1,question_mark", "help",  "help",    '
    'show=True,  priority=True),\n'
    f'        Binding("f2", "modes_crown", "modes", show=True,  priority=True),  # {MARK}\n'
    f'        Binding("f3", "observatory", "observe", show=False, priority=True),  # {MARK}\n'
    '    ]\n'
)

ACTIONS_ANCHOR = """        try:
            self.push_screen(CommandPaletteScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('command-palette screen failed: %r', exc)
    def action_paste_clipboard(self) -> None:
"""

ACTIONS_NEW = f"""        try:
            self.push_screen(CommandPaletteScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('command-palette screen failed: %r', exc)

    def action_modes_crown(self) -> None:  # {MARK}
        \"\"\"F2 / /modes → the mode picker (the crown).\"\"\"
        try:
            from sovereign_agent.cockpit.modes_crown_ui import ModesScreen

            if isinstance(self.screen, ModesScreen):
                self.pop_screen(); return
            self.push_screen(ModesScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('modes screen failed: %r', exc)

    def action_observatory(self) -> None:  # {MARK}
        \"\"\"F3 / /observatory → the watching window.\"\"\"
        try:
            from sovereign_agent.cockpit.modes_crown_ui import ObservatoryScreen

            if isinstance(self.screen, ObservatoryScreen):
                self.pop_screen(); return
            self.push_screen(ObservatoryScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('observatory screen failed: %r', exc)

    def action_paste_clipboard(self) -> None:
"""

SLASH_ANCHOR = """        elif verb == "mode":
            # v0.2.32.0 — /mode chat | /mode work
            # The mode controls whether autonomous agentic loops can run.
            # Chat is the default; work enables planning + queue extension.
            self._handle_mode_slash(arg.strip().lower())
"""

SLASH_NEW = SLASH_ANCHOR + f"""        elif verb == "modes":  # {MARK}
            self.action_modes_crown()
        elif verb in ("observatory", "observe"):  # {MARK}
            self.action_observatory()
"""

STATUSBAR_ANCHOR = "            _rs_mode = _rs_load_mode().mode.value\n"
STATUSBAR_NEW = f"""            _rs_mode = _rs_load_mode().mode.value
            try:  # {MARK} — the crown mode name outranks the base pair
                from sovereign_agent.modes_crown.profiles import (
                    current_profile as _mc_current_profile,
                )

                _rs_mode = _mc_current_profile().mode_id
            except Exception:  # noqa: BLE001
                pass
"""


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, BINDINGS_ANCHOR, BINDINGS_NEW, label="bindings")
    text = _replace_once(text, ACTIONS_ANCHOR, ACTIONS_NEW, label="actions")
    text = _replace_once(text, SLASH_ANCHOR, SLASH_NEW, label="slash verbs")
    text = _replace_once(text, STATUSBAR_ANCHOR, STATUSBAR_NEW,
                         label="status bar")
    return text, True


# ── 3. curiosity.py ──────────────────────────────────────────────────────

CURIOSITY_ANCHOR = """    try:
        from sovereign_agent.cockpit_modes import autonomous_loops_allowed

        if not autonomous_loops_allowed():
            return False
    except Exception:  # noqa: BLE001
        return False
    return _autonomous_count_today(data_dir) < MAX_AUTONOMOUS_PER_DAY
"""

CURIOSITY_NEW = f"""    try:  # {MARK} — the crown's wondering flag outranks the base pair
        from sovereign_agent.modes_crown.profiles import crown_wondering_allowed

        _crown = crown_wondering_allowed()
    except Exception:  # noqa: BLE001
        _crown = None
    if _crown is False:
        return False
    if _crown is None:
        try:
            from sovereign_agent.cockpit_modes import autonomous_loops_allowed

            if not autonomous_loops_allowed():
                return False
        except Exception:  # noqa: BLE001
            return False
    return _autonomous_count_today(data_dir) < MAX_AUTONOMOUS_PER_DAY
"""


def patch_curiosity(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, CURIOSITY_ANCHOR, CURIOSITY_NEW,
                         label="curiosity gate"), True


# ── 4. session_bridge.py — the crown gate (anchors on M5's wire) ─────────

BRIDGE_START_ANCHOR = ("    _lease_check(goal)  # thread-grooming-d — "
                       "record_action enforces the armed lease\n")
BRIDGE_START_NEW = (
    BRIDGE_START_ANCHOR
    + f"    _crown_gate(goal, _scope)  # {MARK} — profile walls: work/garden/cool-down\n"
)

# NOTE: _scope is parsed one line above the M5 anchor in start_goal_session.
# For resume, the persisted contract reloads inside the gate itself.
BRIDGE_RESUME_ANCHOR = '    _lease_check(f"resume {session_id}")  # thread-grooming-d\n'
BRIDGE_RESUME_NEW = (
    BRIDGE_RESUME_ANCHOR
    + f'    _crown_gate("resume", None, session_id=session_id)  # {MARK}\n'
)

BRIDGE_TAIL = f'''

def _crown_gate(goal: str, scope=None, *, session_id: str = "") -> None:
    """{MARK} — the profile walls, enforced at the front door:
    non-work modes refuse sessions; focus requires a garden; cool-down
    pauses NEW dispatches (running work is never interrupted). A NO-OP
    until the operator explicitly arms a crown mode (F2 / /modes) —
    today's behavior (an explicit /work dispatch always ran regardless of
    the passive chat/work toggle) stays byte-identical until then."""
    try:
        from sovereign_agent.modes_crown.profiles import (
            crown_armed, current_profile,
        )
        from sovereign_agent.modes_crown.stances import cooling_down
    except Exception:  # noqa: BLE001 — crown not applied → nothing to gate
        return
    if not crown_armed():
        return
    profile = current_profile()
    if not profile.work_allowed:
        raise PermissionError(
            f"mode {{profile.mode_id!r}} does not run work sessions — "
            f"switch modes (F2 / /modes) to work her")
    if profile.garden_required:
        if scope is None and session_id:
            try:
                from sovereign_agent.scope import load_scope

                scope = load_scope(session_id)
            except Exception:  # noqa: BLE001
                scope = None
        if scope is None or not getattr(scope, "garden_dir", ""):
            raise PermissionError(
                "focus mode requires a garden — declare one: "
                "/work <goal> | scope: dir: <path>")
    if cooling_down():
        raise PermissionError(
            "she is cooling down — no new goals until the stance clears "
            "(set_stance to any working stance, or '')")
'''


def patch_bridge(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, BRIDGE_START_ANCHOR, BRIDGE_START_NEW,
                         label="bridge start gate")
    text = _replace_once(text, BRIDGE_RESUME_ANCHOR, BRIDGE_RESUME_NEW,
                         label="bridge resume gate")
    return text + BRIDGE_TAIL, True


# ── 5. loop.py + tool_paging.py — the cache/side-effect bug ─────────────

LOOP_GET_ANCHOR = """                # ── Cache check (T0 read-only tools only) ──────────────  # cache-crown-dispatch-d
                if meta.tier == 0:
"""

LOOP_GET_NEW = f"""                # ── Cache check (T0 read-only tools only) ──────────────  # cache-crown-dispatch-d
                # {MARK} — tools with loop/session side effects opt out via
                # `cacheable = False`: a cached request_tools response once
                # SKIPPED the attach block below (cache and session state
                # disagreed — the one-truth failure class, in miniature).
                if meta.tier == 0 and getattr(tool, "cacheable", True):
"""

LOOP_PUT_ANCHOR = ("                if meta.tier == 0 and result.ok:  "
                   "# cache-crown-store-d\n")
LOOP_PUT_NEW = ("                if (meta.tier == 0 and result.ok\n"
                "                        and getattr(tool, \"cacheable\", True)):"
                f"  # cache-crown-store-d  # {MARK}\n")


def patch_loop(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, LOOP_GET_ANCHOR, LOOP_GET_NEW, label="cache get")
    text = _replace_once(text, LOOP_PUT_ANCHOR, LOOP_PUT_NEW, label="cache put")
    return text, True


PAGING_ANCHOR = '    failure_modes = ("none_granted",)\n'
PAGING_NEW = (
    PAGING_ANCHOR
    + f"    cacheable = False  # {MARK} — granting ATTACHES tools mid-loop; "
    + "a cached\n    # response would skip that side effect (real bug, "
    + "caught 2026-07-05)\n"
)


def patch_tool_paging(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, PAGING_ANCHOR, PAGING_NEW,
                         label="request_tools cacheable"), True


ALL_PATCHES = {
    "tools/__init__.py": patch_tools_init,
    "cockpit/app.py": patch_app,
    "curiosity.py": patch_curiosity,
    "session_bridge.py": patch_bridge,
    "loop.py": patch_loop,
    "tools/tool_paging.py": patch_tool_paging,
}
