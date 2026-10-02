"""mcp_guard/middleware.py — an ASGI gate in front of Aria's HTTP MCP app.

A request gets through in one of two ways:
  1. `Authorization: Bearer <token>` — preferred; works with Claude Code
     (`claude mcp add --transport http aria <url> --header "Authorization: Bearer <token>"`).
  2. A secret path prefix, `/k/<token>/...` — for clients that cannot send headers (a claude.ai custom
     connector without OAuth). The prefix is stripped before the request reaches the MCP app. Weaker:
     the token sits in the URL, so it can appear in proxy logs. Keep remote tools read-only in this mode.

Everything else gets 401. Tokens are compared in constant time. Denials are audited to Aria's event log
at most once per DENIAL_EVENT_INTERVAL_S (with a count), so a flood of bad requests can't flood the log;
the token and any secret path are never logged.
"""
from __future__ import annotations

import hmac
import json
import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

PATH_PREFIX = "/k/"
DENIAL_EVENT_INTERVAL_S = 60.0


class TokenGuard:
    def __init__(self, app: ASGIApp, token: str) -> None:
        if not token:
            raise ValueError("TokenGuard needs a non-empty token")
        self.app = app
        self._token = token.encode("utf-8")
        self._denied_unreported = 0
        self._last_denial_event = float("-inf")
        self.denied_total = 0

    def _bearer_ok(self, scope: Scope) -> bool:
        for key, value in scope.get("headers") or []:
            if key.lower() == b"authorization":
                scheme, _, credential = value.partition(b" ")
                if scheme.lower() == b"bearer":
                    return hmac.compare_digest(credential.strip(), self._token)
        return False

    def _strip_path_secret(self, scope: Scope) -> Scope | None:
        """Return a copy of scope with `/k/<token>` removed, or None if the path carries no valid secret."""
        path: str = scope.get("path", "")
        if not path.startswith(PATH_PREFIX):
            return None
        secret, slash, rest = path[len(PATH_PREFIX):].partition("/")
        if not hmac.compare_digest(secret.encode("utf-8"), self._token):
            return None
        new_path = slash + rest if slash else "/"
        stripped = dict(scope)
        stripped["path"] = new_path
        stripped["raw_path"] = new_path.encode("utf-8")
        return stripped

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)  # lifespan events carry no request
            return
        if self._bearer_ok(scope):
            await self.app(scope, receive, send)
            return
        stripped = self._strip_path_secret(scope)
        if stripped is not None:
            await self.app(stripped, receive, send)
            return
        self._note_denial(scope)
        await _unauthorized(scope, send)

    def _note_denial(self, scope: Scope) -> None:
        self.denied_total += 1
        self._denied_unreported += 1
        now = time.monotonic()
        if now - self._last_denial_event < DENIAL_EVENT_INTERVAL_S:
            return
        from . import safe_emit_event

        client = scope.get("client") or ("?", 0)
        safe_emit_event("mcp_guard.request_denied", denied=self._denied_unreported,
                     denied_total=self.denied_total, last_client=str(client[0]),
                     used_path_secret=str(scope.get("path", "")).startswith(PATH_PREFIX))
        self._denied_unreported = 0
        self._last_denial_event = now


async def _unauthorized(scope: Scope, send: Send) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1008})
        return
    body = json.dumps({"error": "unauthorized"}).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": 401,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"www-authenticate", b'Bearer realm="aria"'),
        ],
    })
    await send({"type": "http.response.body", "body": body})
