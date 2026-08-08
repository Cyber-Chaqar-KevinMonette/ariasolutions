"""Ollama client wrapper with think_mode-aware dispatch.

Architecture §6 (agent loop) + §V fragile assumption 2a/2b: thinking-mode
behavior on tool-calling is empirically validated separately from no-think.
Default policy is `plan_only`: thinking on for the planner call, off for
tool-dispatch calls.

CAPABILITY DETECTION: Not all tool-calling models support Ollama's `think`
field. Llama 3 Groq Tool Use, for instance, is a tool-calling specialist
without a thinking mode — sending `think=true` returns HTTP 400. We detect
this once per model via ``/api/show`` and silently fall back to no-think
for those models, regardless of the operator's policy. This is the right
behavior: capability mismatches aren't transient errors; they're config
truths the agent should adapt to.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import ollama

from .config import SETTINGS


# ─── Reachability probe (v0.2.26.0) ─────────────────────────────────────────
#
# The interpreter's offline fallback used to say only "interpreter offline"
# with no clue why. Operators were left guessing: is the daemon down? is the
# model not pulled? is the host wrong? `probe_ollama()` gives the offline
# message and `sov doctor` something specific to report.
#
# Authority: Tier 0 — pure read. Two HTTP calls at most (/api/tags + a
# membership test, no /api/show). Never starts services, never pulls models,
# never writes anything. Surfacing the diagnosis is the operator's job; the
# action is theirs.


@dataclass(frozen=True)
class OllamaStatus:
    """Result of a reachability probe. Read-only diagnosis.

    Attributes
    ----------
    host:
        The host that was probed (e.g. ``http://localhost:11434``).
    daemon_reachable:
        True if /api/tags answered. False on connection refused, timeout,
        DNS failure, or any other transport-level error.
    model:
        The model name the caller asked us to check, if any.
    model_present:
        Tri-state. ``True`` if ``model`` is in the local library,
        ``False`` if the daemon answered but didn't list it, ``None`` if
        the question wasn't asked or couldn't be answered (daemon down).
    available_models:
        Names of models the daemon listed. Empty if the daemon is down.
        Useful for hints ("you don't have X; you do have: ...").
    error:
        A short human-readable description of why the probe failed, or
        ``None`` if everything worked. Never a stack trace.
    """

    host: str
    daemon_reachable: bool
    model: str | None = None
    model_present: bool | None = None
    available_models: tuple[str, ...] = ()
    error: str | None = None

    @property
    def healthy(self) -> bool:
        """True iff the daemon is up AND (no model was asked about, OR it's present)."""
        if not self.daemon_reachable:
            return False
        if self.model is None:
            return True
        return self.model_present is True

    def reason_phrase(self) -> str:
        """One-line summary, suitable for an offline reply hint.

        Examples:
          - "Ollama unreachable at http://localhost:11434"
          - "model 'phi-4-mini:3.8b' not in local library (run: ollama pull phi-4-mini:3.8b)"
          - "Ollama is ready"
        """
        if not self.daemon_reachable:
            err = f" — {self.error}" if self.error else ""
            return f"Ollama unreachable at {self.host}{err}"
        if self.model is not None and self.model_present is False:
            hint = f" (run: ollama pull {self.model})"
            return f"model '{self.model}' not in local library{hint}"
        return "Ollama is ready"


async def probe_ollama(
    host: str | None = None,
    *,
    model: str | None = None,
    timeout_seconds: float = 3.0,
) -> OllamaStatus:
    """Probe Ollama's daemon and (optionally) check that ``model`` is pulled.

    This never raises — every failure path returns an OllamaStatus with
    ``daemon_reachable=False`` and an ``error`` describing what happened.
    Callers use the returned status to decide what to tell the operator.

    The probe is intentionally cheap: a single /api/tags call (no /api/show,
    no chat round-trip). On constrained hardware, even /api/tags can take
    100-200ms cold; ``timeout_seconds`` is generous enough not to false-fail
    a slow daemon while still bounding worst-case latency on the chat hot
    path.
    """
    resolved_host = host or SETTINGS.ollama_host
    aclient = ollama.AsyncClient(host=resolved_host)

    try:
        listing = await asyncio.wait_for(aclient.list(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return OllamaStatus(
            host=resolved_host,
            daemon_reachable=False,
            model=model,
            error=f"timed out after {timeout_seconds:.1f}s",
        )
    except Exception as exc:  # noqa: BLE001 — any transport error means "not reachable"
        # Keep the message short and operator-readable; full traces go to
        # logger.debug at the call site if needed.
        msg = type(exc).__name__
        detail = str(exc).splitlines()[0] if str(exc) else ""
        if detail:
            msg = f"{msg}: {detail[:120]}"
        return OllamaStatus(
            host=resolved_host,
            daemon_reachable=False,
            model=model,
            error=msg,
        )

    # Daemon answered. Extract model names. The ollama lib has shifted
    # response shapes across versions (dict with 'models' key, or an object
    # with a .models attribute holding objects with .model). Handle both
    # without assuming either is canonical — version drift here would
    # otherwise turn the probe itself into a bug.
    models_raw: Any = (
        listing.get("models") if isinstance(listing, dict)
        else getattr(listing, "models", None)
    ) or []

    names: list[str] = []
    for entry in models_raw:
        if isinstance(entry, dict):
            name = entry.get("name") or entry.get("model")
        else:
            name = getattr(entry, "name", None) or getattr(entry, "model", None)
        if isinstance(name, str) and name:
            names.append(name)

    available = tuple(names)

    if model is None:
        return OllamaStatus(
            host=resolved_host,
            daemon_reachable=True,
            available_models=available,
        )

    # Ollama tags ":latest" implicitly; treat "foo" and "foo:latest" as equivalent.
    def _norm(n: str) -> str:
        return n if ":" in n else f"{n}:latest"

    target = _norm(model)
    present = any(_norm(n) == target for n in available)

    return OllamaStatus(
        host=resolved_host,
        daemon_reachable=True,
        model=model,
        model_present=present,
        available_models=available,
    )


class CallKind(StrEnum):
    PLAN = "plan"          # decompose a goal into next-action — thinking helps
    DISPATCH = "dispatch"  # produce a tool call against the available list — no-think safer
    REFLECT = "reflect"    # post-task lesson capture — thinking helps


def _policy_wants_think(call_kind: CallKind) -> bool:
    """What the *operator's policy* wants. Capability detection may override."""
    policy = SETTINGS.think_mode
    if policy == "always":
        return True
    if policy == "never":
        return False
    # plan_only (default)
    return call_kind in (CallKind.PLAN, CallKind.REFLECT)


class CapabilityError(Exception):
    """Raised when a model lacks a required capability (e.g., thinking).

    Distinguished from transient model errors so the loop's poison counter
    doesn't punish deterministic config mismatches.
    """


class OllamaClient:
    """Thin wrapper around ollama.AsyncClient with capability detection.

    Capabilities are queried lazily on first chat() per model and cached
    for the lifetime of the client. The cache is per-instance (not global)
    so tests can isolate cleanly.
    """

    def __init__(self, host: str | None = None) -> None:
        self.host = host or SETTINGS.ollama_host
        self._aclient = ollama.AsyncClient(host=self.host)
        # model_name -> set of capability strings (e.g., {"completion", "tools", "thinking"})
        self._capabilities_cache: dict[str, set[str]] = {}
        self._cache_lock = asyncio.Lock()

    async def _get_capabilities(self, model: str) -> set[str]:
        """Return the model's capability set, querying Ollama once and caching."""
        if model in self._capabilities_cache:
            return self._capabilities_cache[model]

        async with self._cache_lock:
            # Re-check after acquiring lock (another caller may have populated)
            if model in self._capabilities_cache:
                return self._capabilities_cache[model]

            try:
                info = await self._aclient.show(model)
                caps_raw = (
                    info.get("capabilities") if isinstance(info, dict)
                    else getattr(info, "capabilities", None)
                )
                caps = set(caps_raw) if caps_raw else set()
            except Exception:  # noqa: BLE001 — show endpoint is best-effort
                # If we can't determine capabilities, assume the broadest set.
                # Better to attempt and surface the real error than to disable.
                caps = {"completion", "tools", "thinking"}

            self._capabilities_cache[model] = caps
            return caps

    async def supports_thinking(self, model: str) -> bool:
        return "thinking" in await self._get_capabilities(model)

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        call_kind: CallKind = CallKind.DISPATCH,
        temperature: float = 0.3,
        num_ctx: int | None = None,
    ) -> dict[str, Any]:
        """Single chat turn. Returns the raw ollama response dict.

        ``think`` is only enabled when (a) the operator's policy wants it
        AND (b) the model advertises the ``thinking`` capability.
        """
        # Decide thinking flag
        want_think = _policy_wants_think(call_kind)
        send_think = want_think and await self.supports_thinking(model)

        opts: dict[str, Any] = {"temperature": temperature}
        if num_ctx is not None:
            opts["num_ctx"] = num_ctx
        elif SETTINGS.num_ctx:
            opts["num_ctx"] = SETTINGS.num_ctx

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "options": opts,
            "think": send_think,
        }
        if tools:
            kwargs["tools"] = tools

        # ── Resilience: circuit breaker gate + retry with backoff on  ──
        # transient errors  # resilience-llm-retry-d resilience-ollama-breaker-d
        import asyncio as _asyncio
        from .resilience import exponential_backoff as _backoff, get_shared_registry as _get_registry
        _breaker = _get_registry().get_breaker("ollama")
        if not _breaker.call_allowed():
            raise RuntimeError(
                "circuit breaker OPEN for ollama (repeated connection "
                "failures). Try again shortly or call resilience_status() "
                "to see all breaker states."
            )
        _llm_last_err: Exception | None = None
        for _llm_attempt in range(3):
            try:
                _resp = await self._aclient.chat(**kwargs)
                _raw = _resp if isinstance(_resp, dict) else _resp.model_dump()
                _breaker.record_success()
                # small-model-bridge-d — rescue small-model tool calls into structure
                try:
                    from .small_model_bridge import normalize_response as _smb_norm
                    _kt = {tt["function"]["name"] for tt in (kwargs.get("tools") or [])
                           if isinstance(tt, dict) and isinstance(tt.get("function"), dict)
                           and tt["function"].get("name")}
                    return _smb_norm(_raw, _kt)
                except Exception:  # noqa: BLE001 — the bridge must never break a call
                    return _raw
            except Exception as _llm_err:  # noqa: BLE001
                _s = (type(_llm_err).__name__ + str(_llm_err)).lower()
                _is_transient = any(k in _s for k in
                    ("connect", "timeout", "network", "reset", "refused", "eof"))
                if not _is_transient or _llm_attempt >= 2:
                    _breaker.record_failure()
                    raise
                _llm_last_err = _llm_err
                await _asyncio.sleep(_backoff(_llm_attempt))
        _breaker.record_failure()
        raise _llm_last_err  # type: ignore[misc]

    async def embed(self, *, model: str, prompt: str) -> list[float]:
        result = await self._aclient.embeddings(model=model, prompt=prompt)
        if isinstance(result, dict):
            return list(result["embedding"])
        return list(result.embedding)

    async def probe(
        self,
        *,
        model: str | None = None,
        timeout_seconds: float = 3.0,
    ) -> "OllamaStatus":
        """Instance-bound shortcut for ``probe_ollama(self.host, model=...)``.

        Callers that already hold a client don't need to know about
        SETTINGS.ollama_host; whatever host this client targets is the
        one probed.
        """
        return await probe_ollama(
            self.host, model=model, timeout_seconds=timeout_seconds,
        )
