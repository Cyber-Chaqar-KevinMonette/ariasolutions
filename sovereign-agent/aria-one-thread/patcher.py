"""patcher.py — Keys round K3: aria-one-thread.

Three anchored, idempotent patches to cockpit/app.py:
  1. The chunk-recorder session id becomes the PERSISTED thread id
     (`thread_identity.thread_id()`, default "aria-main") instead of a
     fresh per-launch uuid — every launch's chunks land in one
     addressable thread (uuid fallback kept if the module is missing).
  2. Wake restore: after the greeting, the last ~30 verbatim turns from
     the thread's sealed chunks render dimmed under "──── earlier, from
     our thread ────". Best-effort — a restore failure never blocks boot.
  3. The transcript line gains the thread id — the one join key across
     chunks/transcript/(K4's) sessions.

thread_identity.py itself is a NEW file (payload/), copied whole.
"""
from __future__ import annotations

MARK = "one-thread-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# 1. persisted thread id
SESSION_ID_ANCHOR = (
    "        import uuid as _uuid_ccd\n"
    '        self._chunk_session_id = f"cockpit-{_uuid_ccd.uuid4().hex[:12]}"\n'
)
SESSION_ID_NEW = (
    f"        # {MARK} — ONE universal continuous thread: the persisted id\n"
    "        # replaces the per-launch uuid that orphaned every prior\n"
    "        # launch's chunks (uuid kept as the fallback if the module is\n"
    "        # somehow missing — a boot must never fail over an id).\n"
    "        import uuid as _uuid_ccd\n"
    "        try:\n"
    "            from sovereign_agent.thread_identity import thread_id as _thread_id\n"
    "\n"
    "            self._chunk_session_id = _thread_id()\n"
    "        except Exception:  # noqa: BLE001\n"
    '            self._chunk_session_id = f"cockpit-{_uuid_ccd.uuid4().hex[:12]}"\n'
)

# 2. wake restore
RESTORE_ANCHOR = (
    "        self._chat_log.write(\n"
    '            "[dim]just talk to me. plain english is enough — "\n'
    '            "no need for `sov ask` in here.[/dim]"\n'
    "        )\n"
)
RESTORE_NEW = (
    RESTORE_ANCHOR
    + f"        # {MARK} — restore the tail of the one continuous thread from\n"
    "        # her sealed chunks (verbatim by design — Workstream P), so\n"
    "        # closing the cockpit never loses the conversation. A gift,\n"
    "        # never a boot blocker.\n"
    "        try:\n"
    "            from rich.markup import escape as _ot_escape\n"
    "\n"
    "            from sovereign_agent.thread_identity import restore_tail as _ot_tail\n"
    "\n"
    "            _ot_turns = _ot_tail(n_turns=30)\n"
    "            if _ot_turns:\n"
    "                self._chat_log.write(\n"
    '                    "[dim]──── earlier, from our thread ────[/dim]"\n'
    "                )\n"
    "                for _ot_t in _ot_turns:\n"
    '                    _ot_role = _ot_escape(str(_ot_t.get("role", "?")))\n'
    '                    _ot_text = _ot_escape(str(_ot_t.get("content", ""))[:400])\n'
    '                    self._chat_log.write(f"[dim]{_ot_role}: {_ot_text}[/dim]")\n'
    '                self._chat_log.write("[dim]──── now ────[/dim]")\n'
    "        except Exception:  # noqa: BLE001\n"
    "            pass\n"
)

# 3. transcript join key
TRANSCRIPT_ANCHOR = (
    '            line = f"[{ts}] {speaker}: {text}\\n"\n'
)
TRANSCRIPT_NEW = (
    f'            line = f"[{{ts}}·{{self._chunk_session_id}}] {{speaker}}: {{text}}\\n"  # {MARK}\n'
)


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, SESSION_ID_ANCHOR, SESSION_ID_NEW, label="app session-id anchor")
    text = _replace_once(text, RESTORE_ANCHOR, RESTORE_NEW, label="app restore anchor")
    text = _replace_once(text, TRANSCRIPT_ANCHOR, TRANSCRIPT_NEW, label="app transcript anchor")
    return text, True
