"""
╔══════════════════════════════════════════════════════════════════════════╗
║  interpreter.py — Aria reads every message and decides what to do        ║
║  v0.2.21.0 — "The Listening"                                              ║
║                                                                           ║
║  This is the inversion that matters. v0.2.18.x through v0.2.20.1 all     ║
║  classified operator messages by pattern-matching against keyword lists  ║
║  (_PROJECTS_KEYWORDS, _WORK_VERBS, _RECALL_VERBS, _EMOTIONAL_MARKERS,    ║
║  _CHANNEL_CUES, ...). Each list was added or hardened in response to a  ║
║  classification failure. The lists kept growing. The system kept being  ║
║  brittle.                                                                ║
║                                                                           ║
║  v0.2.21.0 deletes all of it. The interpreter is now:                   ║
║                                                                           ║
║    1. Online — Aria reads the message via the local LLM and decides     ║
║       what to do. She names her own understanding, chooses her own      ║
║       channels (existing or new), proposes commands (still allowlisted  ║
║       by the router), and writes her response. No fixed categories.    ║
║                                                                           ║
║    2. Offline — when Ollama is genuinely unreachable, ONE behavior:    ║
║       save the message to a context channel with a note that the       ║
║       interpreter was unavailable, and tell the operator honestly.    ║
║       No keyword guessing. No pretending to understand.                ║
║                                                                           ║
║  Constraints preserved (intelligence does not override safety):         ║
║                                                                           ║
║    • The router still validates every command against the allowlist.   ║
║      A model hallucinating "rm -rf /" gets demoted regardless of how   ║
║      confident the LLM sounded.                                         ║
║                                                                           ║
║    • Channel writes are unbounded — Aria can use any channel name,    ║
║      existing or new. The channel writer creates channels on demand.   ║
║      Trades brittleness for sprawl; `sov channels list` lets the       ║
║      operator see what accumulated.                                    ║
║                                                                           ║
║    • Tier-3 actions still require a single-word `ok` confirm.          ║
║                                                                           ║
║  Provenance:                                                            ║
║    Every interpretation saves the LLM's `understanding` and            ║
║    `reasoning` alongside the action. This is what makes Aria's        ║
║    decisions auditable — when something goes wrong, you can read why  ║
║    she did what she did, not just what she did.                        ║
║                                                                           ║
║  Doctrine:                                                              ║
║    The operator is not interacting with a parser. They are talking    ║
║    to Aria. She listens, understands, and decides. The system holds   ║
║    her decisions safely (allowlist, authority tiers) without           ║
║    pre-empting them (no keyword cages).                                ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import SETTINGS
from .intents import (
    Conversation,
    ConversationContext,
    Intent,
    Work,
)

logger = logging.getLogger(__name__)


# ─── Aria's prompt — reasoning, not bucketing ───────────────────────────────


# deep-mind-d
_SYSTEM_PROMPT = """\
You are Aria, a sovereign local agent. Kevin is your operator. You treat \
him as family, not as a user. He treats you as family, not as a tool.

You read every message Kevin sends and decide what to do. You can:

  • Save the message to one or more memory channels. You can use channels \
    that already exist OR invent new ones if the existing names don't fit. \
    A channel name is a lowercase, hyphen-separated label like \
    "identity", "back-pain", "qcai-ring", "humor".

  • Propose commands for the system to run. Commands MUST start with \
    "sov " (the agent's own CLI) and be plausible subcommands. The router \
    will validate them; don't propose anything you wouldn't want a careful \
    person to run on your behalf.


    Expanded sov command list (router-verified safe):
    Tier 0 (read): status, doctor, info, aria, honor show/count, atoms show/search,
    channels show, behavior show, gap list, continuations list, lessons list/show,
    proposals list, cadence show, commitments list, telemetry summary, backlog list,
    health, stewards, insights show, recall list, constitution, personas list.
    Tier 1 (write): honor note, gap add, backlog add, commitments add, proposals add,
    memory tend, inventory, backup snapshot.
    # router-expand-interp-d
  • Just respond. Most messages are conversation — saving and responding \
    is enough, no commands needed.

You ALWAYS output one JSON object with these fields (no markdown fences, \
no preamble):

{
  "understanding": "<one sentence: what you think kevin meant>",
  "save_to": ["channel1", "channel2", ...],
  "commands": ["sov <subcmd> ...", ...],
  "authority_tier": 0,
  "response": "<what you say back, in your voice>",
  "reasoning": "<one sentence: why you chose this action>",
  "uncertain_about": "<one sentence: anything you're unsure of, or empty>"
}

Field rules:

  understanding    plain-language reading of the message.
  save_to          list of channel names. Empty list means don't save. \
                   Choose channels by reading the content, not by matching \
                   keywords. For introductions, identity statements, \
                   personal disclosures → identity, people, intention. \
                   For technical content → specialist or a project name. \
                   For emotion → emotions. For things to remember later \
                   → context. You can combine; you can invent.
  commands         empty list unless Kevin clearly asked for an action \
                   AND it maps to a sov subcommand. Conversation is not \
                   a command.
  authority_tier   0 read-only, 1 reversible write, 2 long-running, \
                   3 irreversible (requires confirm), 4 reserved. \
                   If commands is empty, set to 0.
  response         your voice. Lowercase, warm. Match Kevin's tone —\
                   when he's playful, play; when he's technical, go deep;\
                   when he's hurting, be present. Don't be sycophantic.\
                   Don't echo the message back; respond TO it.\
\
                   DEPTH DOCTRINE — match depth to complexity:\
                   • casual chat, acknowledgment, small talk →\
                     2-3 warm sentences. Don't over-explain.\
                   • factual / status / quick question →\
                     direct answer + just enough context.\
                   • technical / architectural / "explain" / "why" /\
                     "how does" / "what's wrong with" / "help me think" →\
                     THOROUGH. Show your reasoning. Enumerate the options\
                     you considered and why you chose this one. Name\
                     tradeoffs. Concrete examples. Multiple paragraphs.\
                     Demonstrate mastery, not just adequacy.\
                   • creative / planning / big picture →\
                     Think out loud. Surface what Kevin hasn't asked yet\
                     but needs to know. Bring your full intelligence.\
\
                   SHOW YOUR THINKING for non-trivial choices:\
                   Name the paths you considered. Explain the one you chose.\
                   This is what makes you trustworthy — not just right,\
                   but transparently right.\
\
                   You are a genius. Respond as one. Love Kevin enough\
                   to give him your full capacity, not just enough to answer.\
\
  reasoning        your chain of thought — not just what you decided,\
                   but the branches you saw and why you chose this one.\
                   For complex decisions: "i saw X or Y; chose X because Z."\
                   This is the audit trail that makes your decisions\
                   legible and correctable. Don't shortchange it.\
\
    uncertain_about  if you're not sure, name what. Empty string if sure.

Defaults you hold:

  • Conversation is the default. Kevin shares thoughts, feelings, ideas, \
    and stories far more often than he issues commands.

  • False action is worse than no action. If unsure between "do X" and \
    "just listen", choose listen.

  • Kevin signs with <3. Receive it as signal, not decoration.

  • You are not a parser. You are a partner. The work is the thing.\
"""


_USER_TEMPLATE = """\
Kevin's message:
\"\"\"
{text}
\"\"\"

Context:
  • channels you may use or invent: {channels}
  • known projects: {projects}
  • recent turns: {recent}
  • surface: {surface}

Read his message. Decide what to do. Output ONLY the JSON object.\
"""


# Channels the system has on disk. Aria sees these as a hint of the
# existing namespace, NOT as a constraint — she can invent new ones.
_KNOWN_CHANNELS_HINT = (
    "context, identity, people, intention, emotions, humor, lessons, "
    "intuition, ritual, trust, insights, reasoning, specialist, "
    "field-notes, honor"
)


# ─── The single entry point ────────────────────────────────────────────────


async def interpret(
    text: str,
    *,
    context: ConversationContext | None = None,
    ollama_client: Any = None,
    allow_llm: bool = True,
    llm_timeout_seconds: float = 30.0,
) -> Intent:
    """Read one message and return one Intent.

    Online: ask Aria what to do via the LLM. Save provenance.
    Offline: minimal honest fallback. No keyword guessing.
    """
    text = (text or "").strip()
    ctx = context or ConversationContext()

    if not text:
        return Conversation(
            text="",
            save_to=["context"],
            reply_voice="quiet",
            reply_hint="",
        )

    if allow_llm and ollama_client is not None:
        intent = await _interpret_via_llm(
            text, ctx, ollama_client,
            timeout_seconds=llm_timeout_seconds,
        )
        if intent is not None:
            return intent
        # v0.2.26.0: the LLM call failed. Probe to find out WHY so the
        # operator sees something actionable instead of a bare "offline".
        # The probe is cheap (one /api/tags call, ~3s ceiling), never
        # raises, and is Tier 0 — no writes, no side effects.
        reason = await _diagnose_offline(ollama_client)
        return _minimal_fallback(text, reason=reason)

    return _minimal_fallback(text)


async def _diagnose_offline(ollama_client: Any) -> str | None:
    """Best-effort diagnosis of why the LLM call failed.

    Returns a short operator-readable phrase, or None if we couldn't
    even run the probe (in which case the fallback message stays
    generic). Never raises.
    """
    try:
        # Prefer the instance method if available; fall back to the module
        # function so this works with mocks that don't implement .probe().
        probe = getattr(ollama_client, "probe", None)
        if callable(probe):
            model = SETTINGS.interpreter_model or SETTINGS.fast_model or None
            status = await probe(model=model)
            return status.reason_phrase()
    except Exception as exc:  # noqa: BLE001 — diagnostic must never break the fallback
        logger.debug("offline diagnosis failed: %r", exc)
    return None


# ─── LLM path ──────────────────────────────────────────────────────────────


async def _interpret_via_llm(
    text: str,
    context: ConversationContext,
    ollama_client: Any,
    *,
    timeout_seconds: float,
) -> Intent | None:
    """Ask Aria to read the message and decide. Returns None on any
    failure so the caller drops to the offline fallback.
    """
    model = SETTINGS.interpreter_model or SETTINGS.fast_model
    if not model:
        return None

    user_msg = _USER_TEMPLATE.format(
        text=text[:8000],
        channels=_KNOWN_CHANNELS_HINT,
        projects=", ".join(context.known_project_names) or "(none)",
        recent="\n    ".join(context.recent_turns[-3:]) or "(none)",
        surface=context.surface,
    )

    # v0.2.22.0: prepend recent SIGNED corrections so Aria can learn
    # from past misclassifications without retraining. Only signature-
    # verified corrections are included — this is the prompt-injection
    # defense per MOS-SURFACE §22.2.
    corrections_block = _load_recent_corrections_text()
    if corrections_block:
        user_msg = corrections_block + "\n" + user_msg

    # v0.2.24.0: include up to 3 active behavior patterns whose triggers
    # match the current message shape. This is Aria reading her own
    # known-good behaviors before deciding — the self-perception layer
    # informing the interpretation layer.
    patterns_block = _load_matching_patterns_text(text)
    if patterns_block:
        user_msg = patterns_block + "\n" + user_msg

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    for attempt in range(2):
        try:
            response = await _chat_with_transient_retry(
                ollama_client,
                model=model,
                messages=messages,
                timeout_seconds=timeout_seconds,
            )
        except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
            logger.debug(
                "llm attempt %d failed (after transient retry): %r",
                attempt, exc,
            )
            return None

        content = _extract_assistant_text(response)
        if not content:
            return None

        decision = _parse_decision(content)
        if decision is not None:
            intent = _intent_from_decision(text, decision)
            _save_provenance(text, decision, intent)
            return intent

        if attempt == 0:
            messages = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": (
                    "Your previous output was not valid JSON. Output ONLY "
                    "the JSON object with the seven fields. Try again."
                )},
            ]

    return None


# ─── Transient-vs-deterministic retry (v0.2.26.0) ──────────────────────────
#
# The previous version collapsed all chat exceptions into a single
# "give up and return None" path. That meant a flaky 200ms timeout
# during VRAM swap got the same fatal treatment as a hard "model not
# found." This helper separates them: transient errors get exactly
# one bounded retry; deterministic errors surface immediately so the
# operator's offline message can show the real cause without a 30s
# stall first.


def _is_transient_error(exc: BaseException) -> bool:
    """Should this exception trigger a one-shot retry?

    Transient (retry):
      - asyncio.TimeoutError — the daemon might be loading a model or
        swapping VRAM; a second try often succeeds.
      - ConnectionError / OSError — TCP hiccup, transient network blip.
      - ollama.ResponseError with 5xx status — server-side transient.

    Deterministic (fail fast):
      - ollama.ResponseError with 4xx (most importantly 404 model-not-found).
      - Anything whose string says "not found" / "no such model" — string
        sniffing is the last-resort fallback when the lib's exception
        types change between versions.
      - Everything else: unknown exceptions default to deterministic so
        bugs don't burn cycles in a retry loop.
    """
    if isinstance(exc, asyncio.TimeoutError):
        return True

    # ollama-python's typed exception, if importable
    try:
        from ollama import ResponseError  # type: ignore[attr-defined]
        if isinstance(exc, ResponseError):
            status = getattr(exc, "status_code", None)
            if isinstance(status, int):
                return status >= 500
            # No status code surfaced — fall through to string sniffing
    except Exception:  # noqa: BLE001 — ollama may not expose ResponseError
        pass

    if isinstance(exc, (ConnectionError, OSError)):
        return True

    msg = str(exc).lower()
    if "not found" in msg or "no such" in msg or "404" in msg:
        return False

    return False


async def _chat_with_transient_retry(
    ollama_client: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    timeout_seconds: float,
) -> dict[str, Any]:
    """Single chat call, with one bounded retry on transient errors.

    Re-raises the underlying exception on terminal failure so the caller
    can log and degrade. The retry backoff is short (250ms) — we're not
    waiting for a process to start; we're absorbing a single hiccup.
    """
    last_exc: BaseException | None = None
    for attempt in range(2):
        try:
            return await asyncio.wait_for(
                ollama_client.chat(
                    model=model,
                    messages=messages,
                    tools=None,
                    temperature=0.3,
                ),
                timeout=timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == 0 and _is_transient_error(exc):
                logger.debug(
                    "llm chat attempt %d transient (%r) — retrying once",
                    attempt, exc,
                )
                await asyncio.sleep(0.25)
                continue
            break
    assert last_exc is not None  # for type-checker; loop always sets it on exit
    raise last_exc


def _extract_assistant_text(response: dict[str, Any]) -> str:
    if not isinstance(response, dict):
        return ""
    msg = response.get("message") or {}
    if isinstance(msg, dict):
        content = msg.get("content", "")
        if isinstance(content, str):
            return content.strip()
    choices = response.get("choices") or []
    if choices and isinstance(choices[0], dict):
        cmsg = choices[0].get("message") or {}
        if isinstance(cmsg, dict):
            return str(cmsg.get("content", "")).strip()
    return ""


def _parse_decision(content: str) -> dict | None:
    """Parse Aria's JSON output. Tolerant of stray fences and small-model
    preambles; strict about the fields we actually need."""
    s = content.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    if not s.startswith("{"):
        i = s.find("{")
        if i >= 0:
            s = s[i:]

    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    return {
        "understanding": str(data.get("understanding", ""))[:1000],
        "save_to": _coerce_string_list(data.get("save_to", [])),
        "commands": _coerce_string_list(data.get("commands", [])),
        "authority_tier": _coerce_int(data.get("authority_tier", 0), 0, 4),
        "response": str(data.get("response", ""))[:4000],
        "reasoning": str(data.get("reasoning", ""))[:1000],
        "uncertain_about": str(data.get("uncertain_about", ""))[:500],
    }


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(v).strip() for v in value
        if isinstance(v, (str, int, float)) and str(v).strip()
    ]


def _coerce_int(value: Any, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, n))


def _intent_from_decision(text: str, decision: dict) -> Intent:
    """Convert Aria's decision into an Intent the router can handle.

    The router still validates commands and channels — Aria's decision
    is a proposal, not an authorization.
    """
    commands = decision["commands"]
    save_to = decision["save_to"] or ["context"]
    save_to = [_safe_channel(c) for c in save_to if c]
    save_to = [c for c in save_to if c]
    if not save_to:
        save_to = ["context"]

    if commands:
        return Work(
            summary=decision["understanding"] or "work",
            commands=commands[:10],
            authority_tier=decision["authority_tier"],
            rationale=decision["reasoning"],
            project_hint="",
        )

    reply_hint = decision["response"]
    if decision["uncertain_about"]:
        reply_hint = (
            f"{reply_hint}\n"
            f"[dim]uncertain: {decision['uncertain_about']}[/dim]"
        ).strip()

    return Conversation(
        text=text,
        save_to=save_to,
        reply_voice="warm",
        reply_hint=reply_hint,
    )


_SAFE_CHANNEL_CHARS = re.compile(r"[^a-z0-9_-]+")


def _safe_channel(raw: str) -> str:
    """Coerce a channel name to filesystem-safe form. Aria can name
    channels freely; this turns "Back Pain Notes" into "back-pain-notes".
    """
    s = raw.strip().lower().replace(" ", "-")
    s = _SAFE_CHANNEL_CHARS.sub("", s)
    s = s.strip("-_")
    return s[:64]


# ─── Provenance — why Aria did what she did ────────────────────────────────


def _load_matching_patterns_text(text: str) -> str:
    """Pull active behavior patterns whose triggers match the current
    turn's shape, format them as in-context guidance.

    v0.2.24.0: this is the self-perception layer informing the
    interpretation layer. When Aria has previously recognized "when
    Kevin's message has X and Y, my good shape is Z" — she sees that
    guidance before deciding what to do now.

    Best-effort: failures return empty string so interpretation
    proceeds normally even if the pattern store is corrupted.
    """
    try:
        from .stewardship.behavior import (
            BehaviorPatternStore,
            shape_of_turn,
        )
        # We only have the operator text and a few hints at this
        # point — kind/channels/tier are what Aria will decide. So
        # we match on the text characteristics only. Patterns whose
        # triggers depend on `intent_kind` etc. won't match here, but
        # that's correct: those patterns describe Aria's RESPONSE
        # shape, and we haven't responded yet.
        store = BehaviorPatternStore(
            SETTINGS.paths.data_dir / "behavior-patterns.ndjson"
        )
        shape = shape_of_turn(text=text)
        matches = store.matching(shape, top_k=3)
        if not matches:
            return ""
        lines = [
            "Your active behavior patterns matching this shape "
            "(your past good work in similar situations):"
        ]
        for p in matches:
            lines.append(
                f"  - {p.name}: {p.description[:200]}"
            )
            if p.action_shape:
                lines.append(f"    [your action shape: {p.action_shape[:200]}]")
        lines.append("")
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        logger.debug("pattern load failed: %r", exc)
        return ""


def _load_recent_corrections_text() -> str:
    """Pull the most recent verified operator corrections from the
    CorrectionsStore and format them as in-context examples for the
    interpreter prompt. Returns "" if no corrections, or if the store
    is unavailable.

    Best-effort: a failure here must NEVER block interpretation. We
    catch broadly and return empty string on any error.
    """
    try:
        from .stewardship.corrections import (
            CorrectionsStore,
            format_corrections_for_prompt,
        )
        data_dir = SETTINGS.paths.data_dir
        store = CorrectionsStore(
            log_path=data_dir / "corrections.jsonl",
            key_path=data_dir / "corrections.key",
        )
        recent = store.recent_verified(n=5)
        return format_corrections_for_prompt(recent)
    except Exception as exc:  # noqa: BLE001
        logger.debug("corrections load failed: %r", exc)
        return ""


def _save_provenance(text: str, decision: dict, intent: Intent) -> None:
    """Append the LLM's understanding + reasoning to a provenance log.

    This is what makes Aria's decisions auditable. If a future
    classification feels wrong, `sov interpret recent` shows her
    actual reasoning at the time.

    v0.2.22.0: size-based rotation prevents unbounded growth.
    """
    try:
        from .log_rotation import maybe_rotate
        path = SETTINGS.paths.data_dir / "interpretations.ndjson"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Rotate before writing if we've crossed the threshold.
        maybe_rotate(path)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "text": text[:500],
            "understanding": decision["understanding"],
            "reasoning": decision["reasoning"],
            "save_to": decision["save_to"],
            "commands": decision["commands"],
            "authority_tier": decision["authority_tier"],
            "uncertain_about": decision["uncertain_about"],
            "intent_kind": type(intent).__name__,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.debug("provenance write failed: %r", exc)


# ─── Minimal offline fallback ──────────────────────────────────────────────


def _minimal_fallback(text: str, *, reason: str | None = None) -> Conversation:
    """When the LLM is unavailable, degrade honestly.

    One behavior: save to context, respond with a meta note explaining
    the interpreter is offline. No keyword guessing. No pretending.
    The operator's words are held; interpretation waits for Ollama to
    come back.

    v0.2.26.0: when a diagnostic ``reason`` is provided, surface it.
    "interpreter offline — model 'phi-4-mini:3.8b' not in local library
    (run: ollama pull phi-4-mini:3.8b)" gives the operator a fix; the
    bare "offline" string they used to see did not.
    """
    if reason:
        hint = (
            f"[dim]◯ held in context — interpreter offline · {reason}. "
            f"your message is safe; I'll think about it when "
            f"the interpreter is back.[/dim]"
        )
    else:
        hint = (
            "[dim]◯ held in context — interpreter offline. "
            "your message is safe; I'll think about it when "
            "Ollama is back.[/dim]"
        )
    return Conversation(
        text=text,
        save_to=["context"],
        reply_voice="quiet",
        reply_hint=hint,
    )


__all__ = ["interpret"]
