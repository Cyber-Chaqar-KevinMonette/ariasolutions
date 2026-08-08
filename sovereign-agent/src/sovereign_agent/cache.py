"""
cache.py — Session-scoped T0 response cache (M33).

LRU + TTL cache for read-only (Tier 0) tool results. Eliminates redundant
DB hits and repeated file reads within a single session.

  ResponseCache.get(tool_name, args) -> str | None
    Returns the cached content string (already JSON-serialized for the model),
    or None on miss / TTL expiry.

  ResponseCache.put(tool_name, args, content, ttl=300)
    Stores a serialized result string. Evicts the LRU entry when full.

  ResponseCache.flush(tool_name=None) -> int
    Clears all entries (tool_name=None) or just one tool's entries.

  ResponseCache.stats() -> dict
    Returns hit_rate, size, total_requests, entries_by_tool.

Only Tier 0 tools are cached — they are read-only and have no side effects.
T1+ tools always execute regardless.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _CacheEntry:
    content: str       # the serialized content string passed to the model
    expires_at: float
    hit_count: int = 0
    tool_name: str = ""


class ResponseCache:
    """LRU + TTL cache for T0 tool results. Session-scoped singleton."""

    def __init__(self, maxsize: int = 200, default_ttl: int = 300) -> None:
        self._maxsize = maxsize
        self._default_ttl = default_ttl
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._total_requests = 0
        self._total_hits = 0

    # ── Public API ────────────────────────────────────────────────────────

    def get(self, tool_name: str, args: dict[str, Any]) -> str | None:
        self._total_requests += 1
        key = self._key(tool_name, args)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._entries[key]
            return None
        entry.hit_count += 1
        self._total_hits += 1
        self._entries.move_to_end(key)
        return entry.content

    def put(self, tool_name: str, args: dict[str, Any],
            content: str, ttl: int | None = None) -> None:
        key = self._key(tool_name, args)
        if key in self._entries:
            del self._entries[key]
        elif len(self._entries) >= self._maxsize:
            self._entries.popitem(last=False)  # evict LRU
        self._entries[key] = _CacheEntry(
            content=content,
            expires_at=time.monotonic() + (ttl if ttl is not None else self._default_ttl),
            tool_name=tool_name,
        )

    def flush(self, tool_name: str | None = None) -> int:
        if tool_name is None:
            count = len(self._entries)
            self._entries.clear()
            return count
        keys_to_del = [k for k, e in self._entries.items() if e.tool_name == tool_name]
        for k in keys_to_del:
            del self._entries[k]
        return len(keys_to_del)

    def stats(self) -> dict[str, Any]:
        now = time.monotonic()
        live = {k: e for k, e in self._entries.items() if e.expires_at > now}
        by_tool: dict[str, int] = {}
        for e in live.values():
            by_tool[e.tool_name] = by_tool.get(e.tool_name, 0) + 1
        return {
            "size": len(live),
            "maxsize": self._maxsize,
            "total_requests": self._total_requests,
            "total_hits": self._total_hits,
            "hit_rate": round(self._total_hits / max(self._total_requests, 1), 3),
            "entries_by_tool": by_tool,
            "session_tokens_saved_estimate": self._total_hits * 150,
        }

    # ── Internal ──────────────────────────────────────────────────────────

    @staticmethod
    def _key(tool_name: str, args: dict[str, Any]) -> str:
        try:
            serialized = json.dumps(args, sort_keys=True, default=str)
        except Exception:
            serialized = str(sorted(args.items()))
        digest = hashlib.md5(serialized.encode(), usedforsecurity=False).hexdigest()
        return f"{tool_name}:{digest}"


__all__ = ["ResponseCache"]
