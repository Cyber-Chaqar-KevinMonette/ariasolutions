"""delivery — how an alert reaches Discord, safe by default.

Two implementations behind one `send(content) -> DeliveryResult` seam:

  • `DryRunDelivery` (THE DEFAULT) — sends nothing, records what it WOULD
    have sent. An unarmed runtime is completely inert.
  • `WebhookDelivery` — posts to a Discord webhook URL resolved from an
    environment variable NAME (never a stored secret). It only sends for
    real when BOTH `live=True` AND the env var resolves to a URL; otherwise
    it degrades to a dry-run automatically. Uses the stdlib (no dependency);
    the opener is injectable so the live path is testable without network.
    Every real send fires the `on_live_send` hook so a human is alerted.

Official webhook API only. No selfbots, no evasion. The runtime's RateGate
throttles calls to this layer; this layer just performs one send.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable, Protocol

__all__ = [
    "DeliveryResult",
    "Delivery",
    "DryRunDelivery",
    "WebhookDelivery",
    "build_delivery",
    "USER_AGENT",
]

# Discord's edge (Cloudflare) rejects the default `Python-urllib` agent with
# 403/error-1010, and the API asks bots to identify themselves. Send an
# honest, identifying User-Agent — legitimate by construction, never spoofed.
USER_AGENT = ("Aria-SovereignAgent "
              "(https://github.com/Cyber-Chaqar-KevinMonette/Erebo-Aria, 0.4.0)")


@dataclass(frozen=True)
class DeliveryResult:
    sent: bool           # did a real network send happen?
    dry_run: bool        # was this a dry-run (nothing sent)?
    detail: str          # human-readable outcome
    target: str = ""     # redacted target descriptor (never the secret)


class Delivery(Protocol):
    def send(self, content: str) -> DeliveryResult:  # pragma: no cover - protocol
        ...

    def describe(self) -> str:  # pragma: no cover - protocol
        ...


class DryRunDelivery:
    """Sends nothing. The safe default; records intent only."""

    def __init__(self, sink: Callable[[str], None] | None = None) -> None:
        self._sink = sink

    def send(self, content: str, *, embeds: list | None = None,
             username: str | None = None) -> DeliveryResult:
        if self._sink is not None:
            try:
                self._sink(content)
            except Exception:  # noqa: BLE001
                pass
        extra = f" +{len(embeds)} embed(s)" if embeds else ""
        preview = content if len(content) <= 80 else content[:77] + "..."
        return DeliveryResult(sent=False, dry_run=True,
                              detail=f"[dry-run] would send: {preview}{extra}",
                              target="dry-run")

    def describe(self) -> str:
        return "dry-run (sends nothing)"


class WebhookDelivery:
    """Real Discord webhook delivery — off unless explicitly armed.

    webhook_env — the NAME of an env var holding the webhook URL (never the
                  URL itself). Default: DISCORD_WEBHOOK_URL.
    live        — must be True to send for real; otherwise dry-run.
    opener      — injectable urlopen-compatible callable (testability).
    on_live_send— called with `content` on every real send (human alert).
    """

    def __init__(self, webhook_env: str = "DISCORD_WEBHOOK_URL", *,
                 live: bool = False, opener=None,
                 on_live_send: Callable[[str], None] | None = None,
                 timeout: float = 10.0) -> None:
        self._webhook_env = webhook_env
        self._live = live
        self._opener = opener
        self._on_live_send = on_live_send
        self._timeout = timeout

    def _url(self) -> str:
        return (os.environ.get(self._webhook_env) or "").strip()

    def describe(self) -> str:
        state = "LIVE" if (self._live and self._url()) else "dry-run"
        configured = "configured" if self._url() else f"unset (${self._webhook_env})"
        return f"webhook via ${self._webhook_env} [{configured}] — {state}"

    def send(self, content: str, *, embeds: list | None = None,
             username: str | None = None) -> DeliveryResult:
        url = self._url()
        # Safe by default: no real send unless armed AND a target resolves.
        if not self._live or not url:
            reason = "not armed (live=False)" if not self._live \
                else f"no URL in ${self._webhook_env}"
            extra = f" +{len(embeds)} embed(s)" if embeds else ""
            preview = content if len(content) <= 80 else content[:77] + "..."
            return DeliveryResult(sent=False, dry_run=True,
                                  detail=f"[dry-run: {reason}] would send: {preview}{extra}",
                                  target=f"${self._webhook_env}")
        opener = self._opener
        if opener is None:  # lazy: only import/network when truly sending
            from urllib.request import Request, urlopen

            def opener(u, data, timeout):  # type: ignore[misc]
                req = Request(u, data=data,
                              headers={"Content-Type": "application/json",
                                       "User-Agent": USER_AGENT},
                              method="POST")
                return urlopen(req, timeout=timeout)
        # limits-d (Kevin, 2026-07-17): the LAST door every message leaves
        # through enforces Discord's documented caps structurally — an
        # over-limit payload would be HTTP 400 and silently LOST, which is
        # worse than a visible clamp. Multi-message "be smart" splitting
        # happens in the callers (split_text/chunk_embeds); this is the
        # final never-lose-the-message guarantee.
        from sovereign_agent.discord_limits import (
            EMBEDS_PER_MESSAGE, MSG_CONTENT_CHARS, WEBHOOK_USERNAME_CHARS,
            clamp_embed, clamp_text)
        # stamp-d (Kevin): every post carries its date+time. Embeds get the
        # ISO `timestamp` field (Discord renders it localized in the footer);
        # plain content gets a `<t:unix:f>` mark (renders as full local
        # date-time for every viewer). Existing timestamps are respected.
        import time as _t
        now_unix = int(_t.time())
        text = clamp_text(content, MSG_CONTENT_CHARS)
        stamped: list[dict] = []
        if embeds:
            for e in list(embeds)[:EMBEDS_PER_MESSAGE]:
                e = dict(e)
                e.setdefault("timestamp", _t.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", _t.gmtime(now_unix)))
                stamped.append(clamp_embed(e))
        elif text and "<t:" not in text:
            text = clamp_text(f"{text}\n🕐 <t:{now_unix}:f>",
                              MSG_CONTENT_CHARS)
        body: dict = {"content": text}
        if stamped:
            body["embeds"] = stamped
        if username:
            body["username"] = clamp_text(username, WEBHOOK_USERNAME_CHARS)
        payload = json.dumps(body).encode("utf-8")
        try:
            with opener(url, payload, self._timeout):  # type: ignore[misc]
                pass
        except Exception as exc:  # noqa: BLE001
            return DeliveryResult(sent=False, dry_run=False,
                                  detail=f"send FAILED: {type(exc).__name__}",
                                  target=f"${self._webhook_env}")
        if self._on_live_send is not None:
            try:
                self._on_live_send(content)
            except Exception:  # noqa: BLE001
                pass
        return DeliveryResult(sent=True, dry_run=False, detail="sent via webhook",
                              target=f"${self._webhook_env}")


def build_delivery(*, live: bool = False, webhook_env: str = "DISCORD_WEBHOOK_URL",
                   on_live_send: Callable[[str], None] | None = None) -> Delivery:
    """Pick a delivery: dry-run unless `live` is explicitly requested."""
    if not live:
        return DryRunDelivery()
    return WebhookDelivery(webhook_env, live=True, on_live_send=on_live_send)
