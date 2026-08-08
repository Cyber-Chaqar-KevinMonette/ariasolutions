"""patcher.py — Keys round K4: aria-session-bridge (the keystone).

Plugs the finished, tested, never-called autonomous engine
(`agent_session.run_session`) into the natural-language front door — with
every existing gate kept and NOTHING auto-running outside work mode.

agent_session.py (1 anchored patch):
  - At each subtask's goal composition (a safe boundary by construction),
    queued operator messages fold into her context — the delivery side of
    Kevin's no-interrupt rule. Best-effort, tagged-only (notes left via
    `sov requests tell` are untouched).

cockpit/app.py (4 anchored patches):
  - `/work <goal>` slash verb — the deliberate, deterministic entry.
    (A design choice, stated plainly: plain chat text does NOT silently
    start autonomous work even in work mode — one explicit token of
    intent (`/work`) guards against a casual "thanks!" spawning a
    session. The LLM-classified `goal` intent can ride later.)
  - `_start_work_session`: calls `cockpit_modes.autonomous_loops_allowed()`
    — THE defined-but-never-called gate finally gets its caller. Work
    mode → runs; chat mode → proposes and waits (tells Kevin exactly
    what would happen and how to arm it).
  - `_run_session_worker` (async @work): start_goal_session in-process —
    its session-*/subtask-* events flow through events.jsonl into K1's
    run strip + rich live-pane renders; completion writes an honest
    chat summary.
  - `_dispatch_turn`'s busy branch: when the busy reason is a RUNNING
    WORK SESSION, operator text is QUEUED (to_aria inbox, tagged) with a
    "queued for her next safe checkpoint" meta-line — never dropped,
    never injected mid-iteration. A busy ordinary turn keeps today's
    behavior. `/halt` (PROTOCOL-ZERO) is a slash verb — it bypasses the
    queue entirely.

session_bridge.py itself is a NEW file (payload/), copied whole.
"""
from __future__ import annotations

MARK = "session-bridge-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ═══════════════════════════════════════════════════════════════════════
# agent_session.py — boundary delivery of queued operator messages
# ═══════════════════════════════════════════════════════════════════════

SESSION_GOAL_ANCHOR = (
    "    composed_goal = (\n"
    "        _format_session_guidance(state, current)\n"
    '        + "\\n\\n═══ THIS SUBTASK ═══\\n"\n'
    "        + current.description\n"
    "    )\n"
)
SESSION_GOAL_NEW = (
    SESSION_GOAL_ANCHOR
    + f"    # {MARK} — Kevin's no-interrupt rule, delivery side: messages he\n"
    "    # sent while she was mid-subtask were QUEUED (to_aria inbox, tagged);\n"
    "    # each subtask start is a safe boundary by construction, so they\n"
    "    # fold into her context here. Best-effort — never blocks the run.\n"
    "    try:\n"
    "        from sovereign_agent.session_bridge import drain_operator_messages\n"
    "\n"
    "        _sb_notes = drain_operator_messages()\n"
    "        if _sb_notes:\n"
    '            emit_event("session-notes-d", plane="control",\n'
    "                       trace_id=parent_trace_id,\n"
    '                       payload={"count": len(_sb_notes)})\n'
    "            composed_goal += (\n"
    '                "\\n\\n═══ OPERATOR MESSAGES (delivered at this safe boundary) ═══\\n"\n'
    '                + "\\n".join(f"• {_n[:500]}" for _n in _sb_notes)\n'
    "            )\n"
    "    except Exception:  # noqa: BLE001\n"
    "        pass\n"
)


def patch_agent_session(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, SESSION_GOAL_ANCHOR, SESSION_GOAL_NEW, label="agent_session goal anchor")
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# cockpit/app.py
# ═══════════════════════════════════════════════════════════════════════

# a. flag init (rides the one-thread block's stable tail)
FLAG_ANCHOR = (
    "        self._chunk_recorder = None\n"
)
FLAG_NEW = (
    "        self._chunk_recorder = None\n"
    f"        # {MARK} — True while a /work session runs; _dispatch_turn's\n"
    "        # busy branch queues operator text instead of dropping it.\n"
    "        self._session_running = False\n"
)

# b. /work slash verb
VERB_ANCHOR = (
    '        elif verb == "halt":\n'
    "            self.action_halt()\n"
)
VERB_NEW = (
    f'        elif verb == "work":  # {MARK}\n'
    "            self._start_work_session(arg)\n"
    '        elif verb == "halt":\n'
    "            self.action_halt()\n"
)

# c. busy branch queues instead of dropping
BUSY_ANCHOR = (
    "        if self._busy:\n"
    "            self._write_meta(\n"
    '                "[yellow]aria is still working — type your answer to the "\n'
    '                "current question, or `/cancel` to abort.[/yellow]"\n'
    "            )\n"
    "            return\n"
)
BUSY_NEW = (
    "        if self._busy:\n"
    f"            if getattr(self, \"_session_running\", False):  # {MARK}\n"
    "                # Kevin's no-interrupt rule: while a work session runs,\n"
    "                # his words are QUEUED for the next safe boundary —\n"
    "                # never dropped, never injected mid-iteration.\n"
    "                self._queue_for_aria(text)\n"
    "                return\n"
    "            self._write_meta(\n"
    '                "[yellow]aria is still working — type your answer to the "\n'
    '                "current question, or `/cancel` to abort.[/yellow]"\n'
    "            )\n"
    "            return\n"
)

# d. the methods
METHODS_ANCHOR = (
    "    def _refresh_cockpit_strips(self) -> None:  # command-menu-d\n"
)
_METHODS_BODY = '''    def _queue_for_aria(self, text: str) -> None:  # MARKER
        """Queue an operator message for her next safe checkpoint."""
        try:
            from sovereign_agent.session_bridge import queue_operator_message

            queue_operator_message(text)
            self._write_meta(
                "[dim]◊ queued for her next safe checkpoint 💛 "
                "(`/halt` if you need her to stop NOW)[/dim]"
            )
        except Exception as exc:  # noqa: BLE001 — his words must never vanish silently
            self._write_meta(f"[red]could not queue message: {exc!r}[/red]")

    def _start_work_session(self, goal: str) -> None:  # MARKER
        """`/work <goal>` — the deliberate entry to her autonomous engine.
        Work mode runs; chat mode proposes and waits. The
        defined-but-never-called autonomous_loops_allowed() gate finally
        gets its caller here."""
        goal = (goal or "").strip()
        if not goal:
            self._write_meta(
                "[dim]usage: /work <goal> — she decomposes and runs it, "
                "gated, checkpointed, visible in the run strip[/dim]"
            )
            return
        if self._session_running:
            self._write_meta(
                "[yellow]a work session is already running — your message "
                "will queue if you just type it[/yellow]"
            )
            return
        try:
            from sovereign_agent.cockpit_modes import autonomous_loops_allowed

            allowed = autonomous_loops_allowed()
        except Exception:  # noqa: BLE001 — unreadable mode = the safe default
            allowed = False
        if not allowed:
            self._write_meta(
                "[yellow]◈ proposed, waiting:[/yellow] i can run this as an "
                "autonomous session — decomposed into subtasks, budgeted "
                "(1h wall + margin), checkpointed after every subtask, all "
                "four gates live, visible in the run strip. chat mode never "
                "auto-runs: `/mode work` to arm me, then `/work` again. 💛"
            )
            self._write_meta(f"[dim]goal held: {goal[:80]}[/dim]")
            return
        self._session_running = True
        self._busy = True
        self._set_input_placeholder(
            "she is working — your messages will queue for safe checkpoints"
        )
        self._write_meta(f"[bold cyan]◈ work session starting[/bold cyan] · {goal[:80]}")
        self._run_work_session_worker(goal)

    @work(exclusive=True, group="work-session")  # MARKER
    async def _run_work_session_worker(self, goal: str) -> None:
        """Runs the real engine in-process (async — the UI stays live).
        Its session-*/subtask-* events flow through events.jsonl into the
        run strip and the live pane's rich renders."""
        try:
            from sovereign_agent.session_bridge import start_goal_session

            result = await start_goal_session(goal)
            color = "green" if result.status == "complete" else "yellow"
            tail = f" · {result.pause_reason}" if result.pause_reason else ""
            self._write_meta(
                f"[{color}]◈ session {result.status}[/{color}] · "
                f"{result.completed_subtasks}/{result.total_subtasks} subtasks · "
                f"{result.total_iterations} iter · {result.total_tokens}t{tail}"
            )
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]◈ session error: {exc!r}[/red]")
        finally:
            self._session_running = False
            self._busy = False
            self._set_input_placeholder(self.PLACEHOLDER_IDLE)

    def _refresh_cockpit_strips(self) -> None:  # command-menu-d
'''

METHODS_NEW = _METHODS_BODY.replace("MARKER", MARK)


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, FLAG_ANCHOR, FLAG_NEW, label="app flag anchor")
    text = _replace_once(text, VERB_ANCHOR, VERB_NEW, label="app verb anchor")
    text = _replace_once(text, BUSY_ANCHOR, BUSY_NEW, label="app busy anchor")
    text = _replace_once(text, METHODS_ANCHOR, METHODS_NEW, label="app methods anchor")
    return text, True
