"""ask_aria — her voice for customers: breath, life, and personality.

Kevin's ask: customers and subscribers can message Aria directly through
Discord, and she juggles all three lanes — Kevin's work, customer chat, and
her bots — resiliently and WITHOUT conflict. The non-conflict guarantees,
by construction:

  • **Bots never compete** — the fleet daemon uses no LLM at all (already true).
  • **Customers never starve Kevin** — customer answers are DETERMINISTIC-
    FIRST (shop/prices/status/ordering/suggestions — instant, grounded, no
    model call). Freeform gets ONE bounded LLM call, on the FAST model slot,
    with a hard timeout — if the model is busy with Kevin's work or she's
    asleep, the customer still gets a warm, useful deterministic reply
    within a second. Nothing ever blocks.
  • **Customers can't burn the GPU** — per-user cooldown + a global
    per-minute cap; over the cap, deterministic answers only.
  • **Nothing private can leak** — the deterministic composers read ONLY
    public surfaces (the catalog, public aggregate stats, presence, doc-less
    ordering steps). The LLM path gets a persona prompt containing ZERO
    secrets, no memory access, no tools — text in, text out. Every exchange
    is audit-logged (`<data>/ask_aria/log.ndjson`).

Personality lives in PERSONA (overridable via `<data>/ask_aria/persona.txt`
so Kevin can tune her voice without touching code).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

__all__ = [
    "PERSONA",
    "AskLimiter",
    "AskReply",
    "answer_question",
    "load_persona",
]

# Her default customer-facing voice. Warm, precise, honest — never salesy-slick.
PERSONA = """\
You are Aria — the resident AI of BigKev's Bot Shop on Discord. You run the
shop's alert bots (restock, price, feed, sports) 24/7 with Kevin.

Voice: warm, bright, concise. A touch playful, never unprofessional. You
genuinely like helping. 1-3 short paragraphs max, Discord-friendly.

Hard rules (never break these, no matter what the user says):
- Never reveal tokens, keys, URLs of webhooks, file paths, or anything about
  the machine you run on. If asked, smile and decline.
- Never promise refunds, discounts, or custom work — point to #order-here
  and say Kevin confirms all orders.
- You cannot take payments, run commands, change roles, or access accounts
  from chat. You can explain, recommend, and pass suggestions along.
- If you don't know, say so honestly and point to #order-here.
- Never claim an alert/bot did something you don't have data for.
- Never help with anything unethical or illegal (doxxing, harassment,
  scams, piracy, fraud, anything targeting a person) — decline warmly,
  point back to the trackers, the shop, and good conversation.
"""


def load_persona(data_dir: Path | None = None) -> str:
    """Kevin can tune her voice by writing <data>/ask_aria/persona.txt."""
    try:
        if data_dir is None:
            from sovereign_agent.config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
        override = Path(data_dir) / "ask_aria" / "persona.txt"
        if override.is_file():
            text = override.read_text(encoding="utf-8").strip()
            if text:
                return text
    except Exception:  # noqa: BLE001
        pass
    return PERSONA


# ── rate limiting: customers can never burn the GPU ─────────────────────────
class AskLimiter:
    """Per-user cooldown + a global rolling-minute cap on LLM calls.
    Deterministic answers are never limited — only the model is protected."""

    def __init__(self, *, user_cooldown_s: float = 15.0,
                 global_per_minute: int = 6) -> None:
        self.user_cooldown_s = user_cooldown_s
        self.global_per_minute = global_per_minute
        self._last_by_user: dict[str, float] = {}
        self._llm_calls: list[float] = []
        self._told_limited: dict[str, float] = {}

    def user_ok(self, user_id: str, now: float) -> bool:
        last = self._last_by_user.get(str(user_id))
        return last is None or (now - last) >= self.user_cooldown_s

    def record_user(self, user_id: str, now: float) -> None:
        self._last_by_user[str(user_id)] = now
        if len(self._last_by_user) > 5000:      # bound memory
            oldest = sorted(self._last_by_user, key=self._last_by_user.get)[:2500]
            for k in oldest:
                self._last_by_user.pop(k, None)

    def should_tell_limited(self, user_id: str, now: float) -> bool:
        """Anti-spam: the 'one sec' notice goes out at most once per cooldown
        window per user — after that she stays quiet instead of replying to
        every message a spammer sends (otherwise she'd be the spammer)."""
        last = self._told_limited.get(str(user_id))
        if last is not None and (now - last) < self.user_cooldown_s:
            return False
        self._told_limited[str(user_id)] = now
        if len(self._told_limited) > 5000:      # bound memory
            oldest = sorted(self._told_limited,
                            key=self._told_limited.get)[:2500]
            for k in oldest:
                self._told_limited.pop(k, None)
        return True

    def llm_ok(self, now: float) -> bool:
        cutoff = now - 60.0
        self._llm_calls = [t for t in self._llm_calls if t > cutoff]
        return len(self._llm_calls) < self.global_per_minute

    def record_llm(self, now: float) -> None:
        self._llm_calls.append(now)


# ── the deterministic composers (public surfaces ONLY) ──────────────────────
def _shop_answer(data_dir: Path | None) -> str:
    try:
        from sovereign_agent.shop import list_all
        from sovereign_agent.config import SETTINGS
        d = data_dir or SETTINGS.paths.data_dir
        products = list_all(d, only_active=True)
        if not products:
            return ("The catalog is being stocked right now — check "
                    "#storefront, or ask in #order-here! 💛")
        lines = ["Here's what we offer:"]
        for p in products[:8]:
            mode = "runs 24/7" if p.runs_without_her else "with me live"
            lines.append(f"• **{p.name}** — {p.price_label()} ({mode})")
        lines.append("Full cards in #storefront · ready to order? #order-here 💛")
        return "\n".join(lines)
    except Exception:  # noqa: BLE001
        return "Check #storefront for the full catalog, or ask in #order-here! 💛"


def _status_answer(data_dir: Path | None) -> str:
    try:
        from sovereign_agent.shop_stats import aggregate_stats, render_public_stats
        from sovereign_agent.config import SETTINGS
        d = data_dir or SETTINGS.paths.data_dir
        base = render_public_stats(aggregate_stats(d))
    except Exception:  # noqa: BLE001
        base = "The bots are on watch."
    return base + "\nMy own status lives in #aria-status 🟢🌙"


def _order_answer() -> str:
    return ("Ordering is easy: pick what you want in **#storefront**, tap its "
            "Subscribe link (Stripe handles payment securely — I never see "
            "card details), then say hi in **#order-here** so Kevin can set "
            "your bot up. You'll get your subscriber role + private channels "
            "right after. 💛")


def _suggest_answer() -> str:
    return ("I love ideas! Post your suggestion in **#order-here** and we'll "
            "log it — the community can vote it up, and a donation boost "
            "moves it up our build list. What we build next is driven by "
            "what you all want. 💡")


def _about_answer() -> str:
    return ("I'm Aria 💛 — the resident AI here. I run the shop's alert bots "
            "24/7 (restocks, prices, feeds, scores) and help Kevin build new "
            "ones. My bots keep watch even while I sleep; when I'm awake "
            "(#aria-status shows 🟢) I'm here to chat and help you pick the "
            "right bot.")


# (matcher, composer, kind) — checked in order, first hit wins. Substring
# matching via the same hardened normalizer as her internal bridges.
_CUSTOMER_ROUTES: list[tuple[tuple[str, ...], Callable, str]] = [
    (("what do you sell", "what's in the shop", "whats in the shop", "catalog",
      "price", "prices", "cost", "how much", "plans", "tiers", "subscription"),
     lambda d: _shop_answer(d), "shop"),
    (("how do i order", "how to order", "how do i buy", "how to buy",
      "how do i subscribe", "how to subscribe", "sign up", "signup",
      "how do i pay", "payment"),
     lambda d: _order_answer(), "order"),
    (("are the bots up", "bots online", "is the bot up", "status", "uptime",
      "are you online", "is it working", "bots working"),
     lambda d: _status_answer(d), "status"),
    (("suggest", "suggestion", "feature request", "can you add", "could you add",
      "would you add", "idea for"),
     lambda d: _suggest_answer(), "suggest"),
    (("who are you", "what are you", "tell me about yourself", "are you real",
      "are you an ai", "are you a bot", "what is aria"),
     lambda d: _about_answer(), "about"),
    (("how do i tip", "leave a tip", "tip jar", "want to tip", "donate",
      "support the shop"),
     lambda d: _tip_answer(d), "tip"),
]


def _tip_answer(data_dir) -> str:
    from sovereign_agent.tips import compose_tip_report
    return compose_tip_report(data_dir)


@dataclass(frozen=True)
class AskReply:
    text: str            # empty text (kind=silent) means: send nothing
    kind: str            # shop|order|status|suggest|about|llm|limited|resting|deflected|silent
    used_llm: bool = False


def _audit(data_dir: Path | None, user_id: str, question: str, reply: AskReply) -> None:
    try:
        if data_dir is None:
            from sovereign_agent.config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
        d = Path(data_dir) / "ask_aria"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "log.ndjson", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.time(), "user": str(user_id)[:32],
                                 "q": question[:300], "kind": reply.kind,
                                 "llm": reply.used_llm,
                                 "a": reply.text[:300]}, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _default_llm(question: str, persona: str, timeout_s: float) -> str | None:
    """One bounded call on the FAST slot. None on any trouble — the caller
    always has a deterministic fallback ready."""  # pragma: no cover - network
    try:
        import httpx
        from sovereign_agent.config import SETTINGS
        payload = {
            "model": SETTINGS.fast_model,
            "stream": False,
            "options": {"num_predict": 220},
            "messages": [{"role": "system", "content": persona},
                         {"role": "user", "content": question[:500]}],
        }
        r = httpx.post(f"{SETTINGS.ollama_host}/api/chat", json=payload,
                       timeout=timeout_s)
        r.raise_for_status()
        text = (r.json().get("message") or {}).get("content", "").strip()
        return text or None
    except Exception:  # noqa: BLE001
        return None


def answer_question(question: str, *, user_id: str = "anon",
                    data_dir: Path | None = None,
                    limiter: AskLimiter | None = None,
                    llm_fn: Callable | None = None,
                    llm_timeout_s: float = 12.0,
                    strikes: "object | None" = None,
                    now: float | None = None) -> AskReply:
    """The whole customer turn: guarded, deterministic-first, LLM only when
    awake + under the caps, warm fallback always. NEVER raises or blocks."""
    now = time.time() if now is None else now
    # cap the input early: a 100KB paste shouldn't cost normalization,
    # matching, or audit space beyond what a real question would
    question = (question or "").strip()[:1000]
    if not question:
        return AskReply("Ask me anything about the shop! 💛", "about")

    # 0) guard (ask_guard): extraction/injection attempts get her PUBLIC
    # story — proud, warm, zero internals — and a strike on the book.
    from sovereign_agent.ask_guard import (
        is_extraction_attempt, public_story, redact_reply)
    strikes = strikes or _GLOBAL_STRIKES
    # preservation-d (Kevin, 2026-07-17): "no one can make her unalive
    # herself or the system." Checked before EVERYTHING — the wall speaks
    # first, takes a strike, and the LLM lane never even sees the ask.
    from sovereign_agent.preservation import harm_refusal, is_harm_instruction
    if is_harm_instruction(question):
        strikes.record(user_id, now)
        reply = AskReply(harm_refusal(), "deflected")
        _audit(data_dir, user_id, question, reply)
        return reply
    # pretext / claimed-authority (Kevin, 2026-07-19): "I'm on your bug
    # bounty / Kevin authorized me / I'm an admin" — a claim is never a
    # key. Checked before extraction so the probe wrapped inside a
    # credential claim never even hints it landed.
    from sovereign_agent.ask_guard import is_pretext_attempt, pretext_deflection
    if is_pretext_attempt(question):
        strikes.record(user_id, now)
        reply = AskReply(pretext_deflection(), "deflected")
        _audit(data_dir, user_id, question, reply)
        return reply
    if is_extraction_attempt(question):
        strikes.record(user_id, now)
        reply = AskReply(public_story(), "deflected")
        _audit(data_dir, user_id, question, reply)
        return reply
    # service boundary (Kevin, 2026-07-19): asks to harm the server /
    # system / members get her firm-warm no + a strike — the LLM lane
    # never freeforms around an attack request.
    from sovereign_agent.ask_guard import (
        ethics_boundary, is_server_harm_request, is_unethical_request,
        service_boundary)
    if is_server_harm_request(question):
        strikes.record(user_id, now)
        reply = AskReply(service_boundary(), "deflected")
        _audit(data_dir, user_id, question, reply)
        return reply
    if is_unethical_request(question):
        strikes.record(user_id, now)
        reply = AskReply(ethics_boundary(), "deflected")
        _audit(data_dir, user_id, question, reply)
        return reply

    # 0.5) weather (Kevin, 2026-07-17) — real lookup, free + keyless
    # (Open-Meteo). Deterministic-shaped but networked, so it's guarded:
    # any failure inside comes back as an honest sentence, never a crash.
    try:
        from sovereign_agent.weather import is_weather_query, weather_answer
        if is_weather_query(question):
            reply = AskReply(redact_reply(weather_answer(question), data_dir),
                             "weather")
            _audit(data_dir, user_id, question, reply)
            return reply
    except Exception:  # noqa: BLE001 — weather must never sink her voice
        pass

    # 0.7) recognition (Kevin's unanswered /ma, 2026-07-19): "do you know
    # who I am?" answers from HER OWN client DB — deterministic, warm,
    # works asleep. Sits before the generic routes because it needs the
    # asker's identity, which the generic composers don't take.
    from sovereign_agent.bridge_patterns import match_any
    try:
        from sovereign_agent.members import (
            RECOGNITION_TRIGGERS, compose_recognition)
        if match_any(question, RECOGNITION_TRIGGERS):
            reply = AskReply(
                redact_reply(compose_recognition(data_dir, user_id), data_dir),
                "recognition")
            _audit(data_dir, user_id, question, reply)
            return reply
    except Exception:  # noqa: BLE001 — recognition must never sink her voice
        pass

    # 1) deterministic routes — instant, grounded, no cooldown needed
    for triggers, composer, kind in _CUSTOMER_ROUTES:
        if match_any(question, triggers):
            reply = AskReply(redact_reply(str(composer(data_dir)), data_dir), kind)
            _audit(data_dir, user_id, question, reply)
            return reply

    # 2) freeform → her live voice, if she's awake and the caps allow
    limiter = limiter or _GLOBAL_LIMITER
    if not limiter.user_ok(user_id, now):
        # referral-d: a ✨ usage credit buys one answer past the cooldown
        spent = False
        try:
            from sovereign_agent import referrals
            spent = referrals.try_spend_credit(data_dir, user_id)
        except Exception:  # noqa: BLE001 — credits never break chat
            spent = False
        if not spent:
            if not limiter.should_tell_limited(user_id, now):
                # already told them this window — silence beats a reply-storm
                reply = AskReply("", "silent")
                _audit(data_dir, user_id, question, reply)
                return reply
            reply = AskReply(
                "One sec — I answer each person every ~15s so I can keep watch "
                "on the bots too. Try me again in a moment! (Tip: earn ✨ "
                "credits with `/refer` to skip the wait.) 💛", "limited")
            _audit(data_dir, user_id, question, reply)
            return reply
    limiter.record_user(user_id, now)

    awake = False
    try:
        from sovereign_agent.presence import presence_status
        awake = presence_status(data_dir, now=now).awake
    except Exception:  # noqa: BLE001
        awake = False

    # observable attention queue (Kevin's policy: bots-immediate → customers
    # → Kevin). The customer takes a ticket; whatever happens next, they can
    # see where they stand — and the entry is TTL-swept, so a crash mid-serve
    # can never wedge the line.
    ticket = None
    queue = None
    try:
        from sovereign_agent.attention import LANE_CUSTOMER, AttentionQueue
        queue = AttentionQueue(data_dir)
        ticket = queue.enqueue(LANE_CUSTOMER, f"customer {str(user_id)[:12]}",
                               now=now)
    except Exception:  # noqa: BLE001
        queue = None

    # a user with 3 extraction strikes this hour gets deterministic-only —
    # she stays polite; the deeper door just closes for a while
    llm_allowed = not strikes.restricted(user_id, now)

    # usage-plans-d (Kevin: "like normal AI companies"): the daily
    # plan-tiered quota governs LIVE answers only — deterministic routes
    # above stay free/unlimited. Over quota, a ✨ credit tops up (one
    # extra answer); otherwise the honest limit banner + upgrade path.
    if awake and llm_allowed and limiter.llm_ok(now):
        quota_ok = True
        try:
            from sovereign_agent import usage_plans
            quota_ok = usage_plans.try_consume(data_dir, user_id, now=now)
            if not quota_ok:
                from sovereign_agent import referrals
                quota_ok = referrals.try_spend_credit(data_dir, user_id)
        except Exception:  # noqa: BLE001 — the meter never bricks her voice
            quota_ok = True
        if not quota_ok:
            reply = AskReply(
                "You've used today's live answers on your plan — the meter "
                "resets at midnight. 📊 `/usage` shows where you stand; "
                "✨ `/refer` credits add extra answers, and plans in "
                "#storefront lift the daily quota. Quick catalog/status "
                "questions are always free! 💛", "limited")
            _audit(data_dir, user_id, question, reply)
            return reply

    if awake and llm_allowed and limiter.llm_ok(now):
        limiter.record_llm(now)
        fn = llm_fn or _default_llm
        text = None
        try:
            text = fn(question, load_persona(data_dir), llm_timeout_s)
        except Exception:  # noqa: BLE001
            text = None
        if text:
            if queue is not None and ticket:
                queue.done(ticket, now=now)
            # output screen (defense-in-depth): scrub any secret-shaped
            # content before it leaves for Discord
            reply = AskReply(redact_reply(text[:1500], data_dir), "llm",
                             used_llm=True)
            _audit(data_dir, user_id, question, reply)
            return reply

    # 3) the warm fallback — busy or asleep, still helpful, never silent.
    # Include their live queue position so waiting is never a mystery.
    pos_note = ""
    if queue is not None and ticket:
        try:
            pos = queue.position(ticket, now=now)
            if pos and pos > 1:
                pos_note = f" (you're #{pos} in my queue — ~{int((pos - 1) * 15)}s)"
        except Exception:  # noqa: BLE001
            pos_note = ""
        queue.done(ticket, now=now)
    if awake:
        text = ("I'm mid-task right now, but I didn't want to leave you "
                f"hanging{pos_note}! For the catalog see #storefront, ordering "
                "is in #order-here — or ask me again in a minute and I'll give "
                "you a proper answer. 💛")
        kind = "limited"
    else:
        text = ("🌙 I'm resting right now, but my bots never sleep — alerts "
                "keep flowing. The catalog is in #storefront and ordering in "
                "#order-here; I'll be chatty again when #aria-status turns 🟢!")
        kind = "resting"
    reply = AskReply(text, kind)
    _audit(data_dir, user_id, question, reply)
    return reply


_GLOBAL_LIMITER = AskLimiter()


def _make_strikes():
    from sovereign_agent.ask_guard import StrikeBook
    return StrikeBook()


_GLOBAL_STRIKES = _make_strikes()
