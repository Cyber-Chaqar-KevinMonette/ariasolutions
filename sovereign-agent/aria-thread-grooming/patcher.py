"""patcher.py — FABLE II M5: the loose-threads first grooming.

Three patches:
  1. scanner.py learns two more of her own idioms (@mcp.tool endpoints,
     MemoryChannel registration-at-import) so it stops crying wolf about
     17 framework-called symbols — Article II of the sentinel, honored.
  2. autonomy/session.py's ALLOWED_ACTIONS gains "run_goal_session" —
     dispatching one /work goal is a legitimate in-lease action.
  3. session_bridge.py wires record_action — the blast-radius enforcer
     finally lives in /work: an armed lease records every goal dispatch
     on its observable action log; an expired lease REFUSES new goals.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "thread-grooming-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. loose_threads/scanner.py — two more idioms ────────────────────────

SCANNER_BASES_ANCHOR = """        if base_strs & {"Tool", "Sentinel", "BaseModel", "Protocol", "StrEnum",
                        "Enum", "Exception", "ModalScreen", "Screen", "Static",
                        "Widget", "Horizontal", "Vertical", "App", "Message"}:
"""

SCANNER_BASES_NEW = f"""        if base_strs & {{"Tool", "Sentinel", "BaseModel", "Protocol", "StrEnum",
                        "Enum", "Exception", "ModalScreen", "Screen", "Static",
                        "Widget", "Horizontal", "Vertical", "App", "Message",
                        "MemoryChannel"}}:  # {MARK} — registration-at-import
"""

SCANNER_DECOS_ANCHOR = """            if dn in {"command", "callback", "work", "on", "property",
                      "cached_property", "contextmanager", "fixture",
                      "asynccontextmanager"}:
"""

SCANNER_DECOS_NEW = f"""            if dn in {{"command", "callback", "work", "on", "property",
                      "cached_property", "contextmanager", "fixture",
                      "asynccontextmanager",
                      "tool", "resource", "prompt"}}:  # {MARK} — MCP endpoints
"""


def patch_scanner(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, SCANNER_BASES_ANCHOR, SCANNER_BASES_NEW,
                         label="scanner bases")
    text = _replace_once(text, SCANNER_DECOS_ANCHOR, SCANNER_DECOS_NEW,
                         label="scanner decorators")
    return text, True


# ── 2. autonomy/session.py — the new in-lease action ─────────────────────

ACTIONS_ANCHOR = '''    "record_note",           # log a thought/observation
})
'''

ACTIONS_NEW = f'''    "record_note",           # log a thought/observation
    "run_goal_session",      # dispatch one /work goal via the session bridge ({MARK})
}})
'''


def patch_autonomy_actions(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, ACTIONS_ANCHOR, ACTIONS_NEW,
                         label="allowed actions"), True


# ── 3. session_bridge.py — the record_action wire ────────────────────────

BRIDGE_START_ANCHOR = """    goal, _scope = parse_goal_with_scope(goal)
    mode = mode or Mode.BUSY
"""

BRIDGE_START_NEW = f"""    goal, _scope = parse_goal_with_scope(goal)
    _lease_check(goal)  # {MARK} — record_action enforces the armed lease
    mode = mode or Mode.BUSY
"""

BRIDGE_RESUME_ANCHOR = """    state = SessionStore().load(session_id)
    mode = Mode(state.mode)
"""

BRIDGE_RESUME_NEW = f"""    _lease_check(f"resume {{session_id}}")  # {MARK}
    state = SessionStore().load(session_id)
    mode = Mode(state.mode)
"""

BRIDGE_TAIL = f'''

# ─── lease wiring (FABLE II M5 · {MARK}) ─────────────────────────────────
# record_action — the blast-radius enforcer — finally lives in /work: when
# an auto-mode lease is armed, every goal the bridge dispatches is bound-
# checked and recorded on the lease's OBSERVABLE action log; an expired
# lease REFUSES new goals (re-approval, full stop — leases never
# self-extend). No lease armed = today's behavior, unchanged.

_ACTIVE_LEASE = None


def arm_lease(lease) -> None:
    """Arm an AutonomySession lease for the bridge (auto modes call this
    after explicit operator approval)."""
    global _ACTIVE_LEASE
    _ACTIVE_LEASE = lease


def disarm_lease() -> None:
    global _ACTIVE_LEASE
    _ACTIVE_LEASE = None


def active_lease():
    return _ACTIVE_LEASE


def _lease_check(detail: str) -> None:
    """The record_action wire. Outside a lease: no-op. Inside: the dispatch
    is recorded (observable) and an expired/over-radius lease refuses."""
    lease = _ACTIVE_LEASE
    if lease is None:
        return
    from sovereign_agent.autonomy.session import record_action, save

    entry = record_action(lease, "run_goal_session", detail=detail[:200])
    try:
        from sovereign_agent.config import SETTINGS

        save(lease, SETTINGS.paths.data_dir)   # the log is durable, watchable
    except Exception:  # noqa: BLE001 — observability must not block work
        pass
    if not entry.get("allowed"):
        raise PermissionError(
            f"lease refuses the goal dispatch: {{entry.get('reason', 'unknown')}}")
'''


def patch_bridge(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, BRIDGE_START_ANCHOR, BRIDGE_START_NEW,
                         label="bridge start")
    text = _replace_once(text, BRIDGE_RESUME_ANCHOR, BRIDGE_RESUME_NEW,
                         label="bridge resume")
    return text + BRIDGE_TAIL, True


ALL_PATCHES = {
    "loose_threads/scanner.py": patch_scanner,
    "autonomy/session.py": patch_autonomy_actions,
    "session_bridge.py": patch_bridge,
}
