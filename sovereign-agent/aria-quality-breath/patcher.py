"""patcher.py — Fable F2: aria-quality-breath.

Measured: SESSION_GUIDANCE_TEMPLATE = 1,326 static chars + goal + subtask
+ the growing completed-summary (cap 4000) + scope contract — TWO output
protocols with worked examples, stacked per-subtask on the base prompt.
The measured suspect for K4's empty-final wrinkle on the 8B vessel.

One anchored patch to agent_session.py: `_format_session_guidance` renders
a COMPACT guidance (one section, terse protocols, summary slice 1200) by
default; `SOV_NO_GUIDANCE_DIET=1` restores the original byte-for-byte.
"""
from __future__ import annotations

MARK = "guidance-diet-d"


class PatchError(Exception):
    pass


def _replace_once(text, old, new, *, label):
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1, found {text.count(old)}")
    return text.replace(old, new, 1)


ANCHOR = '''def _format_session_guidance(state: SessionState, current: Subtask) -> str:
    done, total = state.progress()
    guidance = SESSION_GUIDANCE_TEMPLATE.format('''

NEW = '''_COMPACT_GUIDANCE = """═══ SESSION {session_id} · subtask {n_done}/{n_total} ═══
Goal: {goal}
Done so far: {completed_summary}

THIS SUBTASK: {current_subtask}

When finished, reply WITHOUT tool calls. First line exactly:
RESULT: <one sentence, what happened>
If (and only if) more steps are truly needed, add lines:
NEXT_SUBTASK[tier=N]: <one concrete step>   (tier 0=read 1=sandbox 2=repo 3=external)
Propose few. Stay inside the goal."""  # guidance-diet-d


def _format_session_guidance(state: SessionState, current: Subtask) -> str:
    # guidance-diet-d — the compact guidance is the default: the measured
    # full template (2 protocols + worked examples + 4000-char summary)
    # starved the 8B vessel per-subtask. SOV_NO_GUIDANCE_DIET=1 restores
    # the original byte-for-byte.
    import os as _os

    done, total = state.progress()
    if not _os.environ.get("SOV_NO_GUIDANCE_DIET"):
        guidance = _COMPACT_GUIDANCE.format(
            session_id=state.session_id,
            goal=state.goal[:300],
            n_done=done + 1,
            n_total=total,
            current_subtask=current.description,
            completed_summary=(state.completed_summary_for_prompt(max_chars=1200)
                               or "(none yet)"),
        )
        try:
            from sovereign_agent.scope import load_scope as _qb_load_scope

            _qb_sc = _qb_load_scope(state.session_id)
            if _qb_sc is not None:
                guidance += "\\n\\n" + _qb_sc.format_for_prompt()
        except Exception:  # noqa: BLE001
            pass
        return guidance
    guidance = SESSION_GUIDANCE_TEMPLATE.format('''


def patch_agent_session(text):
    if MARK in text:
        return text, False
    return _replace_once(text, ANCHOR, NEW, label="guidance anchor"), True
