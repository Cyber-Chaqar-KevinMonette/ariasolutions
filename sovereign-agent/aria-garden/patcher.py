"""patcher.py — Fable round F8: aria-garden.

Kevin: assign her to folders — not a cage, a GARDEN: an assigned place she
tends, granted explicitly by the human in the /work line, enforced by the
REAL wall (pathguard), visible in her own written contract, surviving
/resume because it lives in the persisted scope.

Patches: pathguard.py (the garden wall), scope.py (dir: grammar + field +
prompt line + persistence), agent_session.py (plant on entry / clear in
finally), cockpit/app.py (/garden verb).
"""
from __future__ import annotations

MARK = "garden-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ═══ pathguard.py — the wall ═══════════════════════════════════════════════

GUARD_ANCHOR = '''def check_write_path(target: str | Path, mode: Mode) -> Path:
    """Validate a write/edit destination for the given mode.

    Returns the resolved Path on success.
    Raises PathScopeViolation if mode == BUSY and target is outside sandbox.

    Non-BUSY modes have no path guard here — they delegate to the bwrap mount
    layout and per-tool confirmation prompts (see §7 matrix).
    """
    resolved = _realpath(target)
    if mode == Mode.BUSY:
        sandbox = SETTINGS.paths.sandbox_dir
        if not is_under(resolved, sandbox):
            raise PathScopeViolation(
                str(resolved), mode=mode, allowed=str(sandbox)
            )
    return resolved'''

GUARD_NEW = '''# garden-d — her assigned garden: a per-session workspace granted
# EXPLICITLY by the operator in the /work line (scope `dir:`). Declared →
# ALL modes: writes must land under garden ∪ sandbox (in BUSY this extends
# beyond the sandbox — by the human's own written grant; elsewhere it ADDS
# a wall where none existed). Not declared → behavior byte-for-byte as
# before. Module state is process-scoped: one session runs per process.
_ACTIVE_GARDEN: Path | None = None


def set_garden(path: str | Path) -> Path:
    global _ACTIVE_GARDEN
    _ACTIVE_GARDEN = _realpath(path)
    return _ACTIVE_GARDEN


def clear_garden() -> None:
    global _ACTIVE_GARDEN
    _ACTIVE_GARDEN = None


def active_garden() -> Path | None:
    return _ACTIVE_GARDEN


def check_write_path(target: str | Path, mode: Mode) -> Path:
    """Validate a write/edit destination for the given mode.

    Returns the resolved Path on success.
    Raises PathScopeViolation if mode == BUSY and target is outside sandbox.

    Non-BUSY modes have no path guard here — they delegate to the bwrap mount
    layout and per-tool confirmation prompts (see §7 matrix).

    garden-d: when a garden is planted (set_garden), EVERY mode requires
    writes under garden ∪ sandbox — see the module note above.
    """
    resolved = _realpath(target)
    if _ACTIVE_GARDEN is not None:
        sandbox = SETTINGS.paths.sandbox_dir
        if not (is_under(resolved, _ACTIVE_GARDEN) or is_under(resolved, sandbox)):
            raise PathScopeViolation(
                str(resolved), mode=mode, allowed=f"{_ACTIVE_GARDEN} (garden) or {sandbox}"
            )
        return resolved
    if mode == Mode.BUSY:
        sandbox = SETTINGS.paths.sandbox_dir
        if not is_under(resolved, sandbox):
            raise PathScopeViolation(
                str(resolved), mode=mode, allowed=str(sandbox)
            )
    return resolved'''


def patch_pathguard(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, GUARD_ANCHOR, GUARD_NEW, label="pathguard anchor")
    return text, True


# ═══ scope.py — grammar + field + prompt ═══════════════════════════════════

SCOPE_FIELD_ANCHOR = (
    "    observe: list[str] = field(default_factory=list)\n"
    "    security: list[str] = field(default_factory=list)\n"
)
SCOPE_FIELD_NEW = (
    SCOPE_FIELD_ANCHOR
    + f"    # {MARK} — her assigned garden for this work (operator-granted\n"
    "    # directory; ENFORCED by pathguard, not just self-policed).\n"
    '    garden_dir: str = ""\n'
)

SCOPE_PARSE_ANCHOR = (
    '        if low.startswith("watch:"):\n'
)
SCOPE_PARSE_NEW = (
    f'        if low.startswith("dir:"):  # {MARK}\n'
    "            contract.garden_dir = chunk[4:].strip()\n"
    '        elif low.startswith("watch:"):\n'
)

SCOPE_PROMPT_ANCHOR = (
    "        if self.security:\n"
)
SCOPE_PROMPT_NEW = (
    f"        if self.garden_dir:  # {MARK}\n"
    "            lines.append(\n"
    '                "YOUR GARDEN: " + self.garden_dir\n'
    '                + " — tend here; the loop refuses writes outside it."\n'
    "            )\n"
    "        if self.security:\n"
)

SCOPE_LOAD_ANCHOR = (
    '            observe=list(data.get("observe", [])),\n'
    '            security=list(data.get("security", [])),\n'
)
SCOPE_LOAD_NEW = (
    SCOPE_LOAD_ANCHOR
    + f'            garden_dir=str(data.get("garden_dir", "")),  # {MARK}\n'
)


def patch_scope(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, SCOPE_FIELD_ANCHOR, SCOPE_FIELD_NEW, label="scope field anchor")
    text = _replace_once(text, SCOPE_PARSE_ANCHOR, SCOPE_PARSE_NEW, label="scope parse anchor")
    text = _replace_once(text, SCOPE_PROMPT_ANCHOR, SCOPE_PROMPT_NEW, label="scope prompt anchor")
    text = _replace_once(text, SCOPE_LOAD_ANCHOR, SCOPE_LOAD_NEW, label="scope load anchor")
    return text, True


# ═══ agent_session.py — plant on entry, clear in finally ═══════════════════

SESSION_PLANT_ANCHOR = (
    "    state = store.load(session_id)\n"
    '    state.status = "active"\n'
)
SESSION_PLANT_NEW = (
    "    state = store.load(session_id)\n"
    f"    # {MARK} — plant her garden from the persisted contract (survives\n"
    "    # /resume for free); cleared in the finally below.\n"
    "    _garden_planted = False\n"
    "    try:\n"
    "        from sovereign_agent.scope import load_scope as _g_load_scope\n"
    "\n"
    "        _g_sc = _g_load_scope(session_id)\n"
    "        if _g_sc is not None and _g_sc.garden_dir:\n"
    "            from sovereign_agent.pathguard import set_garden as _g_set\n"
    "\n"
    "            _g_set(_g_sc.garden_dir)\n"
    "            _garden_planted = True\n"
    "    except Exception:  # noqa: BLE001\n"
    "        pass\n"
    '    state.status = "active"\n'
)

SESSION_CLEAR_ANCHOR = (
    "        # ── Final write ──────────────────────────────────────────────\n"
)
SESSION_CLEAR_NEW = (
    f"        # {MARK} — the garden is per-session: clear before the final write.\n"
    "        if _garden_planted:\n"
    "            try:\n"
    "                from sovereign_agent.pathguard import clear_garden as _g_clear\n"
    "\n"
    "                _g_clear()\n"
    "            except Exception:  # noqa: BLE001\n"
    "                pass\n"
    "        # ── Final write ──────────────────────────────────────────────\n"
)


def patch_agent_session(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, SESSION_PLANT_ANCHOR, SESSION_PLANT_NEW, label="session plant anchor")
    text = _replace_once(text, SESSION_CLEAR_ANCHOR, SESSION_CLEAR_NEW, label="session clear anchor")
    return text, True


# ═══ cockpit/app.py — /garden ═══════════════════════════════════════════════

VERB_ANCHOR = (
    '        elif verb == "resume":  # resume-spine-d\n'
)
VERB_NEW = (
    f'        elif verb == "garden":  # {MARK}\n'
    "            try:\n"
    "                from sovereign_agent.pathguard import active_garden\n"
    "\n"
    "                _g = active_garden()\n"
    "                self._write_meta(\n"
    '                    f"[green]◈ garden: {_g}[/green]" if _g else\n'
    '                    "[dim]◈ no garden planted — grant one per work: "\n'
    '                    "`/work <goal> | scope: dir: <path>`[/dim]"\n'
    "                )\n"
    "            except Exception as exc:  # noqa: BLE001\n"
    '                self._write_meta(f"[red]garden read error: {exc!r}[/red]")\n'
    '        elif verb == "resume":  # resume-spine-d\n'
)


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, VERB_ANCHOR, VERB_NEW, label="app verb anchor")
    return text, True
