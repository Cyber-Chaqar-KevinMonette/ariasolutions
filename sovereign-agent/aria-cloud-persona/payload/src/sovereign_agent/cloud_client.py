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
        try:
            pool = await self._get_pool()
            t0 = time.monotonic()
            reply = await pool.achat(
                cloud_messages,
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
            # refusal check on a plain text turn; a tool-call turn is never
            # mistaken for a refusal just because it has no prose.
            has_tool_calls = bool(msg.get("tool_calls"))
            if not has_tool_calls and _looks_like_refusal(reply.text):
                _emit_fallback("cloud reply looked like a refusal")
            else:
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

        local = await self._get_local()
        return await local.chat(
            model=model, messages=messages, tools=tools,
            call_kind=call_kind, temperature=temperature, num_ctx=num_ctx,
        )


__all__ = ["CloudClient"]
