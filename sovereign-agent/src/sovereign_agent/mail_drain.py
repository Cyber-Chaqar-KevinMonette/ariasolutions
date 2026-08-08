"""mail_drain — she replies to EVERYTHING in her inbox (Kevin, 2026-07-19).

Kevin's ask: "She should reply to everything in the inbox meant for her.
Anytime her inbox is full with anything from Discord she should answer
back inside Discord instead of waiting. Make an Aria inbox and a Kevin
inbox so we can separate the two — me or a guest can send stuff to her
inbox and she can message everyone or myself back, showing in the cockpit
and in Discord."

Two inboxes already exist in the request store by `direction`:
  • to_aria  = ARIA'S inbox — things addressed TO her (/ma, questions)
  • to_human = KEVIN'S inbox — her reports/proposals FOR him

This module drains ARIA'S inbox: for each open Discord-origin note it
composes an answer in her own voice (ask_aria — deterministic-first, the
same walls/guards as live chat) and returns a `ReplyIntent` per item so
the gateway can DM the person AND the cockpit can show it. The item is
marked answered with the reply text stored on the record (visible in the
cockpit inbox pane) — nothing is ever answered twice.

Rules (Kevin's separation):
  • MEMBER mail → answered + replied back in Discord.
  • OWNER mail → NEVER auto-answered — Kevin's words wait for Kevin (and
    for her genuine attention), never a canned bounce.
  • mid-task safe: the drain runs at duty-loop checkpoints, never inside
    a subtask; best-effort, never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["ReplyIntent", "pending_for_aria", "drain_and_reply"]


@dataclass(frozen=True)
class ReplyIntent:
    request_id: str
    recipient_id: str          # Discord user ID to DM
    question: str              # what they asked
    answer: str                # her composed reply
    is_owner: bool


def _from_id(tags: list[str]) -> str:
    for t in tags or []:
        if t.startswith("from:"):
            return t.split(":", 1)[1]
    return ""


def _question_of(req) -> str:
    """The member's actual words — the body after our framing header."""
    body = getattr(req, "body", "") or ""
    if "\n\n" in body:
        return body.split("\n\n", 1)[1].strip()
    return (getattr(req, "title", "") or "").split(":", 1)[-1].strip()


def pending_for_aria(store) -> list:
    """Open Discord-origin MEMBER notes awaiting her reply (owner mail
    excluded — it's Kevin's to read, never auto-answered)."""
    out = []
    for req in store.list_for_aria():
        tags = getattr(req, "tags", []) or []
        if "discord" not in tags:
            continue
        if "owner" in tags:          # Kevin's mail waits for Kevin
            continue
        if not _from_id(tags):
            continue
        out.append(req)
    return out


def drain_and_reply(
    data_dir: Path,
    store,
    *,
    answer_fn=None,
    limit: int = 3,
    respect_mid_task: bool = True,
) -> list[ReplyIntent]:
    """Compose + record her reply to each pending member note. Returns the
    intents (the gateway DMs them + the cockpit shows them). Marks each
    answered so it never replies twice. Best-effort per item.

    Non-conflict guarantees (Kevin, 2026-07-19: "rate her reply rate /
    slow mode, don't conflict with her work or bots"):
      • **mid-task gate** — if she's in a fresh work session the drain
        DEFERS entirely (returns []); the notes wait, answered the moment
        she's free. Same gate the redemption queue uses.
      • **slow mode** — at most `limit` replies per tick (default 3); the
        rest wait for the next tick. She never dumps a burst.
      • **bots untouched** — this path shares nothing with the fleet
        (no LLM in the bots); mail answering is deterministic-first too,
        so a busy model can't starve deliveries.

    `answer_fn(question, user_id, data_dir)` defaults to ask_aria — the
    same guarded, walled, deterministic-first voice as live chat, so a
    prompt-injected inbox note is deflected exactly like a live one.
    """
    if respect_mid_task:
        try:
            from sovereign_agent.redemption_queue import is_mid_task
            if is_mid_task(data_dir):
                return []          # her work comes first — notes wait
        except Exception:  # noqa: BLE001 — gate fails OPEN (she still replies)
            pass
    if answer_fn is None:
        from sovereign_agent.ask_aria import answer_question

        def answer_fn(q, user_id, data_dir):  # noqa: ANN001
            return answer_question(q, user_id=user_id, data_dir=data_dir).text

    intents: list[ReplyIntent] = []
    for req in pending_for_aria(store)[:limit]:
        tags = getattr(req, "tags", []) or []
        rid = _from_id(tags)
        question = _question_of(req)
        try:
            reply = (answer_fn(question, rid, data_dir) or "").strip()
        except Exception:  # noqa: BLE001 — one bad note never stalls the drain
            continue
        if not reply:
            reply = ("Got your note — I'm on it and will follow up. 💛")
        try:
            store.answer(req.request_id, reply)
        except Exception:  # noqa: BLE001
            continue
        intents.append(ReplyIntent(
            request_id=req.request_id, recipient_id=rid,
            question=question, answer=reply, is_owner=False))
    return intents
