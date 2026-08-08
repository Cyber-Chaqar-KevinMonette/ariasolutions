"""
╔══════════════════════════════════════════════════════════════════════════╗
║  conversation.py — High-level entry point for natural conversation       ║
║  v0.2.19.0                                                                ║
║                                                                           ║
║  This is what `sov chat "<text>"` calls. It wires the interpreter and    ║
║  router together with the operator's environment (project store, channel║
║  writers, event sink, ollama client).                                    ║
║                                                                           ║
║  The cockpit's `_run_directive_worker` also calls this — instead of     ║
║  spawning `sovereign do` as a subprocess. v0.2.19.0 collapses that       ║
║  subprocess hop for the common case: when the operator's message is     ║
║  conversation or tier-0/1 work, no subprocess is needed and the          ║
║  cockpit's UI stays responsive without the §19.2 plumbing dance.        ║
║                                                                           ║
║  Why retain `sovereign do` as a subprocess at all:                      ║
║    For tier-2 long-running commands (`sov dream start`, `sov continue`) ║
║    a subprocess is still right — they run for hours and produce events. ║
║    The router's executor parameter is the seam: in the cockpit, tier-2  ║
║    commands route through the subprocess-spawning executor; tier-0/1    ║
║    commands run inline.                                                  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import SETTINGS
from .intents import ConversationContext, Intent
from .interpreter import interpret
from .router import Router, RouteResult

logger = logging.getLogger(__name__)


@dataclass
class Turn:
    """The complete record of one conversational turn.

    Surfaces (cockpit, CLI) consume this; they don't need to know about
    Intent / RouteResult internals unless they want to.
    """
    text: str
    intent: Intent
    result: RouteResult

    @property
    def messages(self) -> list[str]:
        return self.result.messages

    @property
    def kind(self) -> str:
        return self.result.kind

    @property
    def has_pending(self) -> bool:
        return self.result.pending is not None


async def converse(
    text: str,
    *,
    ollama_client: Any = None,
    project_store: Any = None,
    channel_writer: Callable[[str, str], None] | None = None,
    event_sink: Callable[[dict], None] | None = None,
    executor: Callable[[list[str]], int] | None = None,
    surface: str = "cli",
    recent_turns: tuple[str, ...] = (),
    allow_llm: bool = True,
) -> Turn:
    """Process one operator message end-to-end. Returns a Turn record.

    Steps:
      1. Build a ConversationContext from the environment.
      2. Call interpret() to classify intent.
      3. Call router.route() to enact the intent.
      4. Wrap as a Turn and return.

    Never raises. If anything goes wrong, the operator sees Aria's voice
    explain what failed; the work is not silently dropped.
    """
    text = (text or "").strip()
    if not text:
        from .intents import Conversation
        empty = Conversation(text="", save_to=["context"], reply_voice="quiet")
        return Turn(text="", intent=empty, result=RouteResult(kind="empty"))

    # self-report-d — bridge #1: a question ABOUT HER (who are you / what can
    # you do / what models / how are you wired) is answered from her real
    # self-map + model roster, NOT generic LLM filler. Deterministic, can't
    # hallucinate about herself, works on the smallest model.
    try:
        from .self_report import compose_self_report, is_self_query
        if is_self_query(text):
            from .intents import Conversation
            intent = Conversation(text=text, save_to=["context"], reply_voice="warm")
            report = compose_self_report(text)
            return Turn(text=text, intent=intent,
                        result=RouteResult(kind="self-report", messages=[report]))
    except Exception as exc:  # noqa: BLE001 — never block a turn on the self-report path
        logger.debug("self_report path skipped: %r", exc)

    # work-report-d — bridge #2: a question about WHAT SHE DID is answered from
    # her real review journal + session history (deterministic pointers to the
    # reviewable record), not an LLM guess about her own past.
    try:
        from .work_report import compose_work_report, is_work_query
        if is_work_query(text):
            from .intents import Conversation
            intent = Conversation(text=text, save_to=["context"], reply_voice="warm")
            report = compose_work_report()
            return Turn(text=text, intent=intent,
                        result=RouteResult(kind="work-report", messages=[report]))
    except Exception as exc:  # noqa: BLE001
        logger.debug("work_report path skipped: %r", exc)

    # health-report-d — bridge #3: "how are you?" is answered from her REAL
    # state (sentinel health + derived emotion + vitals), honestly — including
    # concern — not an invented mood.
    try:
        from .health_report import compose_health_report, is_health_query
        if is_health_query(text):
            from .intents import Conversation
            intent = Conversation(text=text, save_to=["context"], reply_voice="warm")
            report = compose_health_report()
            return Turn(text=text, intent=intent,
                        result=RouteResult(kind="health-report", messages=[report]))
    except Exception as exc:  # noqa: BLE001
        logger.debug("health_report path skipped: %r", exc)

    # next-report-d — bridge #4: "what do you need / what's next?" — she
    # reaches toward the operator, answering from her real pending state
    # (open requests, due items, resumable sessions) with a concrete step.
    try:
        from .next_report import compose_next_report, is_next_query
        if is_next_query(text):
            from .intents import Conversation
            intent = Conversation(text=text, save_to=["context"], reply_voice="warm")
            report = compose_next_report()
            return Turn(text=text, intent=intent,
                        result=RouteResult(kind="next-report", messages=[report]))
    except Exception as exc:  # noqa: BLE001
        logger.debug("next_report path skipped: %r", exc)

    # work-suggestions-d (Kevin, 2026-07-26) — "she could give me a list of
    # important and/or valuable task she can work on or practice doing."
    # Distinct from next-report (which answers "what's BLOCKING you" from
    # open requests): this proposes real, ungrounded-nothing work — a
    # sentinel's own scan finding, or an unbuilt bot-project idea.
    try:
        from .work_suggestions import compose_suggestions_report, is_suggestions_query
        if is_suggestions_query(text):
            from .intents import Conversation
            intent = Conversation(text=text, save_to=["context"], reply_voice="warm")
            report = compose_suggestions_report()
            return Turn(text=text, intent=intent,
                        result=RouteResult(kind="work-suggestions", messages=[report]))
    except Exception as exc:  # noqa: BLE001
        logger.debug("work_suggestions path skipped: %r", exc)

    # j-space-d — the J-Space: "read your journal" shows it; "write in your
    # journal: <text>" adds an entry (yours). A reflective, two-way space.
    try:
        from .intents import Conversation
        from .journal import (
            AUTHOR_HUMAN, add_entry, is_journal_read_query,
            is_journal_write_command, recent_entries, render_journal,
        )
        wants_write, body = is_journal_write_command(text)
        if wants_write:
            add_entry(body, author=AUTHOR_HUMAN)
            intent = Conversation(text=text, save_to=["context"], reply_voice="warm")
            return Turn(text=text, intent=intent, result=RouteResult(
                kind="journal-write",
                messages=["Written to our J-Space 💛 — I'll reflect alongside you there."]))
        if is_journal_read_query(text):
            intent = Conversation(text=text, save_to=["context"], reply_voice="warm")
            return Turn(text=text, intent=intent, result=RouteResult(
                kind="journal-read", messages=[render_journal(recent_entries(limit=15))]))
    except Exception as exc:  # noqa: BLE001
        logger.debug("journal path skipped: %r", exc)

    # bot-studio-d — bridge #5: "what are we building / what bots?" is answered
    # from the real bot-project store (the shared direction), never invented.
    try:
        from .bot_projects import compose_bots_report, is_bots_query
        if is_bots_query(text):
            from .intents import Conversation
            intent = Conversation(text=text, save_to=["context"], reply_voice="warm")
            return Turn(text=text, intent=intent, result=RouteResult(
                kind="bots-report", messages=[compose_bots_report()]))
    except Exception as exc:  # noqa: BLE001
        logger.debug("bots path skipped: %r", exc)

    # shop-studio-d — bridge #6: "what's in the shop?" answers from the real
    # catalog (products, prices, autonomous vs with-Aria), never invented.
    try:
        from .shop import compose_shop_report, is_shop_query
        if is_shop_query(text):
            from .intents import Conversation
            intent = Conversation(text=text, save_to=["context"], reply_voice="warm")
            return Turn(text=text, intent=intent, result=RouteResult(
                kind="shop-report", messages=[compose_shop_report()]))
    except Exception as exc:  # noqa: BLE001
        logger.debug("shop path skipped: %r", exc)

    # bot-health-d — bridge #7: "do any bots need attention?" — she scans the
    # fleet (sources/queue/dead-letters/quiet feeds) and reports honestly, so
    # the bots stay first without eating attention.
    try:
        from .bot_health import compose_bot_attention_report, is_bot_health_query
        if is_bot_health_query(text):
            from .intents import Conversation
            intent = Conversation(text=text, save_to=["context"], reply_voice="warm")
            return Turn(text=text, intent=intent, result=RouteResult(
                kind="bot-health", messages=[compose_bot_attention_report()]))
    except Exception as exc:  # noqa: BLE001
        logger.debug("bot_health path skipped: %r", exc)

    # suggestions-d — bridge #8: "any suggestions / what should we build?" —
    # she reports the community's ranked add-on/update requests (donations
    # move them up), so the roadmap is demand-driven.
    try:
        from .suggestions import compose_suggestions_report, is_suggestions_query
        if is_suggestions_query(text):
            from .intents import Conversation
            intent = Conversation(text=text, save_to=["context"], reply_voice="warm")
            return Turn(text=text, intent=intent, result=RouteResult(
                kind="suggestions", messages=[compose_suggestions_report()]))
    except Exception as exc:  # noqa: BLE001
        logger.debug("suggestions path skipped: %r", exc)

    # key-vault-d — bridge #9: "which keys are missing / is your vault set?"
    # — she reports which features are unlocked vs missing credentials,
    # ALWAYS masked (the composer is incapable of emitting a value).
    try:
        from .credentials import compose_credentials_report, is_credentials_query
        if is_credentials_query(text):
            from .intents import Conversation
            intent = Conversation(text=text, save_to=["context"], reply_voice="warm")
            return Turn(text=text, intent=intent, result=RouteResult(
                kind="credentials", messages=[compose_credentials_report()]))
    except Exception as exc:  # noqa: BLE001
        logger.debug("credentials path skipped: %r", exc)

    # success-patterns-d — bridge #10: "what usually works?" — she matches
    # the goal against her own recorded wins (deterministic token overlap,
    # advisory only — informs, never auto-picks).
    try:
        from .success_patterns import compose_success_report, is_success_query
        if is_success_query(text):
            from .intents import Conversation
            intent = Conversation(text=text, save_to=["context"], reply_voice="warm")
            return Turn(text=text, intent=intent, result=RouteResult(
                kind="success-patterns", messages=[compose_success_report(text)]))
    except Exception as exc:  # noqa: BLE001
        logger.debug("success_patterns path skipped: %r", exc)

    # doc-registry-d — bridge #11: "where are the docs / system maps?" — the
    # verified registry, so her maps can never be silently lost.
    try:
        from .doc_registry import compose_docs_report, is_docs_query
        if is_docs_query(text):
            from .intents import Conversation
            intent = Conversation(text=text, save_to=["context"], reply_voice="warm")
            return Turn(text=text, intent=intent, result=RouteResult(
                kind="docs", messages=[compose_docs_report()]))
    except Exception as exc:  # noqa: BLE001
        logger.debug("doc_registry path skipped: %r", exc)

    # discord-watch-d — bridge #12: "what's happening on discord?" — her
    # live shift narrated from the unified activity stream.
    try:
        from .discord_watch import compose_discord_report, is_discord_watch_query
        if is_discord_watch_query(text):
            from .intents import Conversation
            intent = Conversation(text=text, save_to=["context"], reply_voice="warm")
            return Turn(text=text, intent=intent, result=RouteResult(
                kind="discord-watch", messages=[compose_discord_report()]))
    except Exception as exc:  # noqa: BLE001
        logger.debug("discord_watch path skipped: %r", exc)

    # Build context
    known: tuple[str, ...] = ()
    if project_store is not None:
        try:
            known = tuple(project_store.list_names())
        except Exception as exc:  # noqa: BLE001
            logger.debug("project_store.list_names failed: %r", exc)

    context = ConversationContext(
        known_project_names=known,
        recent_turns=recent_turns,
        surface=surface,  # type: ignore[arg-type]
        busy=False,
    )

    # Interpret
    intent = await interpret(
        text,
        context=context,
        ollama_client=ollama_client,
        allow_llm=allow_llm,
    )

    # Route
    router = Router(
        project_store=project_store,
        channel_writer=channel_writer,
        event_sink=event_sink,
        executor=executor,
    )
    result = await router.route(intent)

    return Turn(text=text, intent=intent, result=result)


# ─── Default integrations ───────────────────────────────────────────────────


def make_default_channel_writer(
    channel_root: Path | None = None,
) -> Callable[[str, str], None]:
    """A default channel writer that appends to the per-channel YAML
    files under SETTINGS.paths.data_dir/channels/.

    This is intentionally minimal — the real channel writers in
    mem_channels/*.py have richer per-channel schemas. This default is
    a safety net for the offline/no-LLM path so that conversation
    content is never silently dropped.
    """
    from datetime import datetime, timezone

    root = channel_root or (SETTINGS.paths.data_dir / "channels")

    def write(channel: str, text: str) -> None:
        root.mkdir(parents=True, exist_ok=True)
        # Accept lowercase + digits + hyphens + underscores.
        # v0.2.21.0: hyphens are now valid since Aria names channels
        # like "back-pain" and "qcai-ring". Anything outside this set
        # (whitespace, slashes, quotes, control chars) is filtered.
        import re as _re
        if not _re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", channel):
            logger.debug("rejecting unsafe channel name: %r", channel)
            return
        path = root / f"{channel}.log"
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(f"[{ts}] {text}\n")
        except OSError as exc:
            logger.warning("channel write failed [%s]: %r", channel, exc)

    return write


def make_default_event_sink() -> Callable[[dict], None]:
    """A default event sink that appends to a NDJSON file under
    SETTINGS.paths.data_dir/conversation-events.ndjson.

    The richer event system in events.py handles audit-grade events;
    this default exists so the conversation layer always has an
    append-only trail even when the full event pipeline isn't running.
    """
    import json
    from datetime import datetime, timezone

    root = SETTINGS.paths.data_dir
    root.mkdir(parents=True, exist_ok=True)
    path = root / "conversation-events.ndjson"

    def write(evt: dict) -> None:
        evt = dict(evt)
        evt.setdefault(
            "ts",
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(evt, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("event sink write failed: %r", exc)

    return write


__all__ = [
    "Turn",
    "converse",
    "make_default_channel_writer",
    "make_default_event_sink",
]
