"""cloud_client.py — CloudClient: a drop-in `chat()` swap for OllamaClient,
backed by pooled free-tier cloud providers instead of the local model.

Kevin, 2026-07-25: "let's add a fast free cloud mode?" ... "fall back can be
local when cloud mode is unavailable or refusing a task." Sourced from
`freellmpool` (MIT, 0xzr) found in the hardware-liberation zip corpus — it
pools 24 free-tier LLM providers (Groq, Cerebras, NVIDIA NIM, Gemini,
OpenRouter, ...) behind one async client with automatic provider failover
and per-day quota tracking, so this class only has to adapt shapes, not
implement pooling itself.

Contract: identical call signature and return shape to
`ollama_client.OllamaClient.chat()` (see that module) — same
`{"message": {...}, "prompt_eval_count", "eval_count", "eval_duration", ...}`
envelope, so `loop.py` and every other caller needs zero changes to accept
either client. Tool schemas are already OpenAI-shaped in this codebase
(`tools/base.py:schema()` — `{"type": "function", "function": {...}}`), and
`loop.py`'s own tool-call parsing already tolerates `arguments` arriving as
either a dict or a JSON string, so no tool-call translation is needed
either direction.

Falls back to a real local OllamaClient whenever the cloud path is
unavailable (package missing, no providers configured, all providers
exhausted/rate-limited, network failure) OR produces a refusal-shaped
reply — Kevin's explicit ask, not a nice-to-have: cloud mode must never
leave a task simply undone because a free provider said no.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from sovereign_agent.ollama_client import CallKind, OllamaClient

# A plain, conservative refusal heuristic -- not trying to catch every
# phrasing, just the common, unambiguous ones. False negatives (a refusal
# that slips through) just mean the caller gets a refusal string back, same
# as any other model answer; false positives (falling back when the answer
# was fine) cost a redundant local call, never correctness.
_REFUSAL_PATTERNS = [
    re.compile(p, re.I) for p in (
        r"\bI (?:can(?:'|no)?t|won'?t|am unable to) (?:help|assist|comply)\b",
        r"\bas an AI\b.{0,40}\bcannot\b",
        r"\bI'?m not able to (?:help|assist) with that\b",
        r"\bI must decline\b",
    )
]


def _looks_like_refusal(text: str) -> bool:
    if not text or not text.strip():
        return True  # an empty completion is as unusable as a refusal
    return any(p.search(text) for p in _REFUSAL_PATTERNS)


# 2026-09-19, found live: a keyless free provider (Pollinations) answered a perfectly good
# request with HTTP 200 and the chat content "The account behind this API key doesn't have enough
# credits. Please top up...". Nothing raised, so the pool never failed over, the refusal heuristic
# above didn't match, and that billing text was handed to the agent loop AS Aria's answer (and the
# reflector then "learned" a lesson from it). An error dressed as a completion is a provider failure:
# retry the pool (fair-share routing may pick another provider), then fall back to local.
_PROVIDER_ERROR_PATTERNS = [
    re.compile(p, re.I) for p in (
        r"doesn'?t have enough credits",
        r"\b(?:insufficient|not enough) (?:credits|quota|balance)\b",
        r"\btop[- ]?up\b.{0,80}\b(?:credits|balance|account)\b",
        r"\b(?:rate[- ]?limit(?:ed)?|quota (?:exceeded|exhausted)|too many requests)\b",
        r"\bapi key\b.{0,40}\b(?:invalid|missing|expired|revoked)\b",
    )
]
_CLOUD_ATTEMPTS = 3


# ---- message-shape translation (2026-09-19) ----------------------------------------------------------------
# The agent loop keeps history in OLLAMA's shape: an assistant turn's tool_calls carry `arguments` as a dict and have
# no id; a tool result is {"role": "tool", "name": <tool>, "content": ...} with no tool_call_id. OpenAI-compatible
# providers (every free-pool provider) require the opposite on the SECOND call of any tool loop: string `arguments`, an
# `id` on each call, and a `tool_call_id` on each result -- OVH answered HTTP 422 "messages[3]: missing field
# `tool_call_id`", so a cloud-driven tool loop only ever survived one step. And a cloud reply's string arguments make
# the local ollama client reject the history ("Input should be a valid dictionary"). Both directions are translated
# on the way out, on copies -- the loop's own history is never modified.
_OPENAI_KEYS = ("role", "content", "tool_calls", "tool_call_id", "name")


def _to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    pending: list[tuple[str, str | None]] = []          # (call id, tool name) of calls still awaiting a result
    for i, raw in enumerate(messages):
        m = {k: raw[k] for k in _OPENAI_KEYS if k in raw}
        if m.get("role") == "assistant" and m.get("tool_calls"):
            calls = []
            for j, tc in enumerate(m["tool_calls"]):
                fn = dict(tc.get("function") or {})
                args = fn.get("arguments", {})
                fn["arguments"] = args if isinstance(args, str) else json.dumps(args if args is not None else {})
                cid = tc.get("id") or f"call_{i}_{j}"
                calls.append({"id": cid, "type": "function", "function": fn})
                pending.append((cid, fn.get("name")))
            m["tool_calls"] = calls
            if m.get("content") is None:
                m["content"] = ""
        elif m.get("role") == "tool":
            name = m.get("name")
            pick = next((k for k, (_, n) in enumerate(pending) if name and n == name), 0 if pending else None)
            if not m.get("tool_call_id"):
                m["tool_call_id"] = pending.pop(pick)[0] if pick is not None else f"call_orphan_{i}"
            elif pick is not None:
                pending.pop(pick)
            if not isinstance(m.get("content"), str):
                m["content"] = json.dumps(m.get("content"), default=str)
        out.append(m)
    return out


def _to_ollama_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in messages:
        m = dict(raw)
        if m.get("role") == "assistant" and m.get("tool_calls"):
            calls = []
            for tc in m["tool_calls"]:
                tc = dict(tc)
                fn = dict(tc.get("function") or {})
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        parsed = json.loads(args) if args.strip() else {}
                    except ValueError:
                        parsed = {}
                    fn["arguments"] = parsed if isinstance(parsed, dict) else {}
                tc["function"] = fn
                calls.append(tc)
            m["tool_calls"] = calls
        out.append(m)
    return out


def _looks_like_provider_error(text: str) -> bool:
    return bool(text) and any(p.search(text) for p in _PROVIDER_ERROR_PATTERNS)


def _emit_fallback(reason: str) -> None:
    """Best-effort observability -- a fallback is a normal, designed path,
    not a crash, but Kevin should be able to see it happened."""
    try:
        from sovereign_agent.events import emit_event
        emit_event("cloud-fallback-x", plane="control", trace_id="cloud-mode",
                   payload={"reason": reason[:200]})
    except Exception:  # noqa: BLE001
        pass


class CloudClient:
    """Fast Free Cloud mode's client. Same `chat()` contract as
    OllamaClient; falls back to a real local OllamaClient transparently."""

    def __init__(self, *, local: OllamaClient | None = None) -> None:
        self._local = local  # constructed lazily on first fallback if None
        self._pool = None  # lazy freellmpool.AsyncPool

    async def _get_local(self) -> OllamaClient:
        if self._local is None:
            self._local = OllamaClient()
        return self._local

    async def _get_pool(self):
        if self._pool is None:
            from freellmpool import AsyncPool  # optional dep -- ImportError → fallback
            self._pool = AsyncPool.from_default_config()
        return self._pool

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        call_kind: CallKind = CallKind.DISPATCH,
        temperature: float = 0.3,
        num_ctx: int | None = None,
        routing_mode: str | None = None,
        pool_models: list[str | None] | None = None,
    ) -> dict[str, Any]:
        """Try the cloud pool first; any failure or refusal falls back to a
        real local OllamaClient.chat() call with the SAME arguments, so the
        caller always gets a real answer either way.

        ``routing_mode`` — external-reasoning-escalation-d: freellmpool
        already ships a difficulty-aware "quality" routing mode (matches
        prompt difficulty to model capability, routing hard prompts to the
        strongest available free-tier model — see freellmpool/capability.py)
        that this class never used to request. Pass ``routing_mode="quality"``
        for a step that's genuinely hard or high-stakes; leave it None for
        the pool's own default (fair-share) routing.
        """
        # ``pool_models`` (2026-09-19): pin which free-pool models to try, in order -- attempt N uses the Nth. A
        # measured benchmark showed the pool's own routing was a poor fit for tool-heavy work (a reasoning model
        # took 75-83 s per call; another provider ignored the tools). A failure or provider-error text moves on to
        # the NEXT pinned model instead of retrying the same one, then local.
        # cloud-persona-d: local models carry Aria's persona in their Modelfile SYSTEM block; cloud
        # models don't, so give them the same identity (plus her voice and current inner state).
        # Never fatal: on any failure the call proceeds with the original messages.
        try:
            from sovereign_agent.cloud_persona import condition_messages

            cloud_messages = condition_messages(messages, model=model)
        except Exception as exc:  # noqa: BLE001
            cloud_messages = messages
            try:
                from sovereign_agent.events import emit_event
                emit_event("cloud-persona-x", plane="agent", trace_id="cloud-mode",
                           payload={"reason": f"{type(exc).__name__}: {exc}"[:200]})
            except Exception:  # noqa: BLE001
                pass
        attempts = max(_CLOUD_ATTEMPTS, len(pool_models or ()))
        for attempt in range(attempts):
            pinned = pool_models[attempt] if pool_models and attempt < len(pool_models) else None
            extra = {"model": pinned} if pinned else {}
            try:
                pool = await self._get_pool()
                t0 = time.monotonic()
                reply = await pool.achat(
                    _to_openai_messages(cloud_messages),
                    **extra,
                    # model=None (the achat default) — "auto" is only a valid
                    # value in freellmpool's OpenCode-integration model picker,
                    # NOT the Python achat() API; passing it here as a literal
                    # model id matched zero candidates and always fell back
                    # (NoProvidersConfigured). Omitting model lets the router
                    # pick freely from whatever free tier is actually up, same
                    # as the plain `pool.aask(...)` path.
                    tools=tools,
                    temperature=temperature,
                    routing=routing_mode,
                )
                elapsed_s = max(time.monotonic() - t0, 1e-6)
                msg = reply.message or {"role": "assistant", "content": reply.text}
                # A tool call legitimately has empty/None text content -- the
                # "answer" IS the tool call, not a written reply. Only run the
                # text checks on a plain text turn; a tool-call turn is never
                # mistaken for a refusal or an error just because it has no prose.
                has_tool_calls = bool(msg.get("tool_calls"))
                if not has_tool_calls and _looks_like_provider_error(reply.text):
                    _emit_fallback(f"cloud provider returned an error as text (attempt {attempt + 1})")
                    continue
                if not has_tool_calls and _looks_like_refusal(reply.text):
                    _emit_fallback("cloud reply looked like a refusal")
                    break
                return {
                    "message": msg,
                    "model": reply.model,
                    "done": True,
                    "prompt_eval_count": reply.prompt_tokens or 0,
                    "eval_count": reply.completion_tokens or 0,
                    # Wall-clock, not pure generation time -- includes network
                    # latency, since freellmpool's Reply carries no per-call
                    # timing of its own. An honest approximation, not a
                    # fabricated number; the token-speed strip will read a
                    # little conservative for cloud calls, never inflated.
                    "eval_duration": int(elapsed_s * 1e9),
                }
            except Exception as exc:  # noqa: BLE001 — any cloud failure falls back
                _emit_fallback(f"{type(exc).__name__}: {exc}"[:200])
                if pool_models and attempt + 1 < len(pool_models):
                    continue          # try the next pinned model before giving up to local
                break

        local = await self._get_local()
        return await local.chat(
            model=model, messages=_to_ollama_messages(messages), tools=tools,
            call_kind=call_kind, temperature=temperature, num_ctx=num_ctx,
        )


__all__ = ["CloudClient"]
