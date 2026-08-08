"""patcher.py — Keys round K10: aria-scope-contract.

Four anchored, idempotent patches:

session_bridge.py (1): `start_goal_session` parses `<goal> | scope: ...`,
  persists the contract beside the session file, and passes the bare goal
  on — `/work fix the parser | scope: only src/parser; out: tests; done:
  parse errors gone; max: 8` just works.

agent_session.py (2):
  - `_format_session_guidance` appends the contract (when one exists) —
    she self-polices against her own written words.
  - The NEXT_SUBTASK growth site gains the teeth: proposals tripping the
    contract's out_of_scope terms are marked BLOCKED with a scope-review
    note (emitting `scope-review-d`) instead of silently joining the
    queue; and when the queue crosses DRIFT_THRESHOLD of the contract's
    max_subtasks, a one-time `scope-drift-d` fires — drift visible long
    before the budget wall stops things bluntly.

cockpit/run_surface.py (1): rich renders for scope-review-d /
  scope-drift-d — the discipline is observable, not buried.

scope.py itself is a NEW file (payload/), copied whole.
"""
from __future__ import annotations

MARK = "scope-contract-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ═══ session_bridge.py ════════════════════════════════════════════════════

BRIDGE_ANCHOR = (
    "    mode = mode or Mode.BUSY\n"
    "    state = new_session(goal=goal, mode=mode)\n"
)
BRIDGE_NEW = (
    f"    # {MARK} — `<goal> | scope: ...` declares a ScopeContract up front:\n"
    "    # pre-registered honesty at the boundary of the work.\n"
    "    from sovereign_agent.scope import parse_goal_with_scope, save_scope\n"
    "\n"
    "    goal, _scope = parse_goal_with_scope(goal)\n"
    "    mode = mode or Mode.BUSY\n"
    "    state = new_session(goal=goal, mode=mode)\n"
    "    if _scope is not None:\n"
    "        try:\n"
    "            save_scope(state.session_id, _scope)\n"
    "        except Exception:  # noqa: BLE001 — scope is a discipline, never a crash\n"
    "            pass\n"
)


def patch_bridge(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, BRIDGE_ANCHOR, BRIDGE_NEW, label="bridge anchor")
    return text, True


# ═══ agent_session.py ═════════════════════════════════════════════════════

GUIDANCE_ANCHOR = (
    "def _format_session_guidance(state: SessionState, current: Subtask) -> str:\n"
    "    done, total = state.progress()\n"
    "    return SESSION_GUIDANCE_TEMPLATE.format(\n"
    "        session_id=state.session_id,\n"
    "        goal=state.goal,\n"
    "        n_done=done + 1,\n"
    "        n_total=total,\n"
    "        current_subtask=current.description,\n"
    '        completed_summary=state.completed_summary_for_prompt() or "(none yet)",\n'
    "    )\n"
)
GUIDANCE_NEW = (
    "def _format_session_guidance(state: SessionState, current: Subtask) -> str:\n"
    "    done, total = state.progress()\n"
    "    guidance = SESSION_GUIDANCE_TEMPLATE.format(\n"
    "        session_id=state.session_id,\n"
    "        goal=state.goal,\n"
    "        n_done=done + 1,\n"
    "        n_total=total,\n"
    "        current_subtask=current.description,\n"
    '        completed_summary=state.completed_summary_for_prompt() or "(none yet)",\n'
    "    )\n"
    f"    # {MARK} — the contract she wrote before starting rides in the\n"
    "    # guidance: she self-polices against her own words.\n"
    "    try:\n"
    "        from sovereign_agent.scope import load_scope\n"
    "\n"
    "        _sc = load_scope(state.session_id)\n"
    "        if _sc is not None:\n"
    '            guidance += "\\n\\n" + _sc.format_for_prompt()\n'
    "    except Exception:  # noqa: BLE001\n"
    "        pass\n"
    "    return guidance\n"
)

GROWTH_ANCHOR = (
    "        for desc, tier in proposals[:max(0, room)]:\n"
    "            new = Subtask(\n"
    '                id=_new_id("st"),\n'
    "                description=desc,\n"
    "                required_tier=tier,\n"
    "                parent_id=current.id,\n"
    "            )\n"
    "            state.subtasks.append(new)\n"
    '            emit_event("subtask-proposed-d", plane="control",\n'
    "                       trace_id=parent_trace_id,\n"
    '                       payload={"subtask_id": new.id,\n'
    '                                "parent_id": current.id,\n'
    '                                "tier": tier,\n'
    '                                "description": desc[:200]})\n'
)
GROWTH_NEW = (
    f"        # {MARK} — the teeth, at the exact door scope creep enters:\n"
    "        # proposals tripping the contract's out list are HELD (blocked,\n"
    "        # scope-review) instead of silently joining the queue; crossing\n"
    "        # the drift threshold fires a one-time scope-drift-d.\n"
    "        _sc_contract = None\n"
    "        try:\n"
    "            from sovereign_agent.scope import DRIFT_THRESHOLD, load_scope\n"
    "\n"
    "            _sc_contract = load_scope(state.session_id)\n"
    "        except Exception:  # noqa: BLE001\n"
    "            _sc_contract = None\n"
    "        for desc, tier in proposals[:max(0, room)]:\n"
    "            new = Subtask(\n"
    '                id=_new_id("st"),\n'
    "                description=desc,\n"
    "                required_tier=tier,\n"
    "                parent_id=current.id,\n"
    "            )\n"
    "            if _sc_contract is not None and _sc_contract.is_out_of_scope(desc):\n"
    '                new.status = "blocked"\n'
    '                new.error = "scope-review: outside the declared contract"\n'
    "                state.subtasks.append(new)\n"
    '                emit_event("scope-review-d", plane="control",\n'
    "                           trace_id=parent_trace_id,\n"
    '                           payload={"subtask_id": new.id,\n'
    '                                    "description": desc[:200]})\n'
    "                continue\n"
    "            state.subtasks.append(new)\n"
    '            emit_event("subtask-proposed-d", plane="control",\n'
    "                       trace_id=parent_trace_id,\n"
    '                       payload={"subtask_id": new.id,\n'
    '                                "parent_id": current.id,\n'
    '                                "tier": tier,\n'
    '                                "description": desc[:200]})\n'
    "        if (_sc_contract is not None\n"
    "                and len(state.subtasks) >= DRIFT_THRESHOLD * _sc_contract.max_subtasks\n"
    '                and not getattr(state, "_scope_drift_emitted", False)):\n'
    "            state._scope_drift_emitted = True  # in-memory once-per-run guard\n"
    '            emit_event("scope-drift-d", plane="control",\n'
    "                       trace_id=parent_trace_id,\n"
    '                       payload={"subtasks": len(state.subtasks),\n'
    '                                "max": _sc_contract.max_subtasks})\n'
)


def patch_agent_session(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, GUIDANCE_ANCHOR, GUIDANCE_NEW, label="guidance anchor")
    text = _replace_once(text, GROWTH_ANCHOR, GROWTH_NEW, label="growth anchor")
    return text, True


# ═══ cockpit/run_surface.py ═══════════════════════════════════════════════

SURFACE_ANCHOR = (
    '        if flag == "qa-start-d":\n'
)
SURFACE_NEW = (
    f'        if flag == "scope-review-d":  # {MARK}\n'
    '            return (f"[yellow]◈ scope review:[/yellow] held — "\n'
    "                    f\"{str(p.get('description', ''))[:70]}\")\n"
    f'        if flag == "scope-drift-d":  # {MARK}\n'
    '            return (f"[yellow]◈ scope drift:[/yellow] {p.get(\'subtasks\', \'?\')}/"\n'
    "                    f\"{p.get('max', '?')} subtasks — nearing the contract ceiling\")\n"
    '        if flag == "qa-start-d":\n'
)


def patch_run_surface(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, SURFACE_ANCHOR, SURFACE_NEW, label="run_surface anchor")
    return text, True
