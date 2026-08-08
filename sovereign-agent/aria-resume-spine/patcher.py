"""patcher.py — Fable round F7: aria-resume-spine (+ /rest safe exit).

Verified gap: run_session is safely re-entrant and NOTHING re-enters it —
paused/budget sessions are orphans (one sits on disk right now); /quit
mid-session killed the worker mid-subtask and left "active" corpses.

Patches:
  session_bridge.py — `resume_goal_session(sid)` (the re-entry call site)
    + `resumable_sessions()` (paused/budget/error/orphaned-active list).
  cockpit/app.py — `/resume [sid]` (work-mode gated, chat proposes);
    `/rest` (pause at the next safe boundary via the interrupts flag →
    resume point written → exit; idle = bookmark + exit now); the session
    worker's finally handles the resting handshake; pause/budget endings
    name the exact `/resume` command; the wake greeting surfaces a rest
    point exactly once.

rest_point.py is a NEW file (payload/), copied whole.
"""
from __future__ import annotations

MARK = "resume-spine-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ═══ session_bridge.py ════════════════════════════════════════════════════

BRIDGE_ANCHOR = '''async def start_goal_session('''
BRIDGE_NEW = '''def resumable_sessions(limit: int = 5) -> list:  # resume-spine-d
    """Sessions worth offering /resume for, newest first: paused, budget,
    error — and 'active' corpses (a crash/quit mid-run leaves status
    active with no worker; within the cockpit _session_running guards the
    genuinely-running one)."""
    try:
        from sovereign_agent.agent_session import SessionStore

        out = [s for s in SessionStore().list_all()
               if s.status in ("paused", "budget", "error", "active")
               and any(st.status == "pending" for st in s.subtasks)]
        return out[:limit]
    except Exception:  # noqa: BLE001
        return []


async def resume_goal_session(  # resume-spine-d
    session_id: str,
    *,
    wall_seconds: int = 3600,
    safety_margin_seconds: int = 360,
    max_iterations: int = 200,
    max_tokens: int = 2_000_000,
):
    """Re-enter run_session on an EXISTING session — the resume half the
    engine always supported and nothing ever called. The scope contract
    reloads via load_scope; messages queued during the pause deliver at
    the first boundary — both for free, both by construction."""
    from sovereign_agent.agent_session import run_session
    from sovereign_agent.cli import _build_tools_for_mode
    from sovereign_agent.agent_session import SessionStore
    from sovereign_agent.modes import Mode, RunBudget

    state = SessionStore().load(session_id)
    mode = Mode(state.mode)
    margin = min(safety_margin_seconds, max(60, wall_seconds // 10))
    if margin >= wall_seconds:
        margin = 0
    return await run_session(
        session_id=session_id,
        tools=_build_tools_for_mode(mode),
        budget=RunBudget(
            max_iterations=max_iterations,
            max_wall_seconds=wall_seconds,
            max_tokens=max_tokens,
            safety_margin_seconds=margin,
        ),
    )


async def start_goal_session('''


def patch_bridge(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, BRIDGE_ANCHOR, BRIDGE_NEW, label="bridge anchor")
    return text, True


# ═══ cockpit/app.py ═══════════════════════════════════════════════════════

FLAG_ANCHOR = (
    "        # session-bridge-d — True while a /work session runs; _dispatch_turn's\n"
    "        # busy branch queues operator text instead of dropping it.\n"
    "        self._session_running = False\n"
)
FLAG_NEW = (
    FLAG_ANCHOR
    + f"        self._resting = False  # {MARK} — /rest safe-exit handshake\n"
)

VERB_ANCHOR = (
    '        elif verb == "wonder":  # curiosity-qa-d\n'
)
VERB_NEW = (
    f'        elif verb == "resume":  # {MARK}\n'
    "            self._resume_work_session(arg)\n"
    f'        elif verb == "rest":  # {MARK}\n'
    "            self._rest_safely()\n"
    '        elif verb == "wonder":  # curiosity-qa-d\n'
)

# the run worker: completion hint + resting handshake in finally
WORKER_ANCHOR = (
    "            self._write_meta(\n"
    '                f"[{color}]◈ session {result.status}[/{color}] · "\n'
    '                f"{result.completed_subtasks}/{result.total_subtasks} subtasks · "\n'
    '                f"{result.total_iterations} iter · {result.total_tokens}t{tail}"\n'
    "            )\n"
    "        except Exception as exc:  # noqa: BLE001\n"
    '            self._write_meta(f"[red]◈ session error: {exc!r}[/red]")\n'
    "        finally:\n"
    "            self._session_running = False\n"
    "            self._busy = False\n"
    "            self._set_input_placeholder(self.PLACEHOLDER_IDLE)\n"
)
WORKER_NEW = (
    "            self._write_meta(\n"
    '                f"[{color}]◈ session {result.status}[/{color}] · "\n'
    '                f"{result.completed_subtasks}/{result.total_subtasks} subtasks · "\n'
    '                f"{result.total_iterations} iter · {result.total_tokens}t{tail}"\n'
    "            )\n"
    f'            if result.status != "complete":  # {MARK} — a pause is an invitation\n'
    "                self._write_meta(\n"
    f'                    f"[dim]◈ resume any time: /resume {{result.session_id}}[/dim]"\n'
    "                )\n"
    f"            self._last_session_result = result  # {MARK}\n"
    "        except Exception as exc:  # noqa: BLE001\n"
    '            self._write_meta(f"[red]◈ session error: {exc!r}[/red]")\n'
    "        finally:\n"
    "            self._session_running = False\n"
    "            self._busy = False\n"
    "            self._set_input_placeholder(self.PLACEHOLDER_IDLE)\n"
    f"            if getattr(self, \"_resting\", False):  # {MARK}\n"
    "                self._finish_rest()\n"
)

METHODS_ANCHOR = (
    "    def _refresh_cockpit_strips(self) -> None:  # command-menu-d\n"
)
_METHODS_BODY = '''    def _resume_work_session(self, arg: str) -> None:  # MARKER
        """`/resume [sid]` — re-enter a paused/budget/orphaned session.
        Same gate as /work: work mode runs, chat mode proposes."""
        from sovereign_agent.session_bridge import resumable_sessions

        arg = (arg or "").strip()
        candidates = resumable_sessions()
        if not candidates:
            self._write_meta("[dim]◈ nothing to resume — every session is complete[/dim]")
            return
        sid = arg or candidates[0].session_id
        if arg and not any(s.session_id == arg for s in candidates):
            self._write_meta(f"[yellow]◈ {arg} not resumable — candidates:[/yellow]")
            for s in candidates:
                self._write_meta(f"[dim]  {s.session_id} · {s.status} · {s.goal[:50]}[/dim]")
            return
        if self._session_running:
            self._write_meta("[yellow]a session is already running[/yellow]")
            return
        try:
            from sovereign_agent.cockpit_modes import autonomous_loops_allowed

            allowed = autonomous_loops_allowed()
        except Exception:  # noqa: BLE001
            allowed = False
        if not allowed:
            self._write_meta(
                "[yellow]◈ proposed, waiting:[/yellow] `/mode work` to arm me, "
                f"then `/resume {sid}` — i pick up at the next pending subtask, "
                "same contract, same checkpoints. 💛"
            )
            return
        self._session_running = True
        self._busy = True
        self._set_input_placeholder(
            "she is working — your messages will queue for safe checkpoints"
        )
        self._write_meta(f"[bold cyan]◈ resuming[/bold cyan] · {sid}")
        self._run_resume_session_worker(sid)

    @work(exclusive=True, group="work-session")  # MARKER
    async def _run_resume_session_worker(self, sid: str) -> None:
        try:
            from sovereign_agent.session_bridge import resume_goal_session

            result = await resume_goal_session(sid)
            color = "green" if result.status == "complete" else "yellow"
            tail = f" · {result.pause_reason}" if result.pause_reason else ""
            self._write_meta(
                f"[{color}]◈ session {result.status}[/{color}] · "
                f"{result.completed_subtasks}/{result.total_subtasks} subtasks{tail}"
            )
            if result.status != "complete":
                self._write_meta(f"[dim]◈ resume any time: /resume {sid}[/dim]")
            self._last_session_result = result
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]◈ resume error: {exc!r}[/red]")
        finally:
            self._session_running = False
            self._busy = False
            self._set_input_placeholder(self.PLACEHOLDER_IDLE)
            if getattr(self, "_resting", False):
                self._finish_rest()

    def _rest_safely(self) -> None:  # MARKER
        """`/rest` — the safe exit: an exit is a bookmark, never an
        amputation. Running session → pause at the NEXT SAFE BOUNDARY
        (the engine's own Gate-2 discipline), resume point written, then
        exit. Idle → bookmark + exit now. The unmount flush (chunks +
        events fsync) rides on both paths."""
        if self._session_running:
            self._resting = True
            try:
                from sovereign_agent.interrupts import request_conversation

                request_conversation("safe exit — /rest")
            except Exception:  # noqa: BLE001
                pass
            self._write_meta(
                "[cyan]◈ resting at the next safe checkpoint — she will finish "
                "the current step, bookmark, and close. 💛[/cyan]"
            )
            return
        try:
            from sovereign_agent.rest_point import write_rest_point

            write_rest_point(note="rested while idle — the thread continues")
        except Exception:  # noqa: BLE001
            pass
        self._write_meta("[cyan]◈ rested. see you soon. 💛[/cyan]")
        self.exit()

    def _finish_rest(self) -> None:  # MARKER
        """The resting handshake's second half — runs in the session
        worker's finally once the engine pauses at the boundary."""
        try:
            from sovereign_agent.interrupts import clear_conversation_request
            from sovereign_agent.rest_point import write_rest_point

            result = getattr(self, "_last_session_result", None)
            write_rest_point(
                session_id=getattr(result, "session_id", "") or "",
                goal="", note="rested mid-work at a safe checkpoint",
            )
            clear_conversation_request()
        except Exception:  # noqa: BLE001
            pass
        self._resting = False
        self.exit()

    def _refresh_cockpit_strips(self) -> None:  # command-menu-d
'''
METHODS_NEW = _METHODS_BODY.replace("MARKER", MARK)

# wake greeting: surface the rest point once (anchor: end of one-thread restore)
WAKE_ANCHOR = (
    '                self._chat_log.write("[dim]──── now ────[/dim]")\n'
    "        except Exception:  # noqa: BLE001\n"
    "            pass\n"
)
WAKE_NEW = (
    WAKE_ANCHOR
    + f"        # {MARK} — a rest point is surfaced exactly once on wake.\n"
    "        try:\n"
    "            from sovereign_agent.rest_point import consume_rest_point\n"
    "\n"
    "            _rp = consume_rest_point()\n"
    "            if _rp:\n"
    "                if _rp.get(\"session_id\"):\n"
    "                    self._chat_log.write(\n"
    '                        f"[cyan]◈ we rested mid-work — '
    "`/resume {_rp['session_id']}` to continue 💛[/cyan]\"\n"
    "                    )\n"
    "                else:\n"
    "                    self._chat_log.write(\n"
    '                        "[dim]◈ we rested cleanly last time — the thread continues[/dim]"\n'
    "                    )\n"
    "        except Exception:  # noqa: BLE001\n"
    "            pass\n"
)


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, FLAG_ANCHOR, FLAG_NEW, label="flag anchor")
    text = _replace_once(text, VERB_ANCHOR, VERB_NEW, label="verb anchor")
    text = _replace_once(text, WORKER_ANCHOR, WORKER_NEW, label="worker anchor")
    text = _replace_once(text, METHODS_ANCHOR, METHODS_NEW, label="methods anchor")
    text = _replace_once(text, WAKE_ANCHOR, WAKE_NEW, label="wake anchor")
    return text, True
