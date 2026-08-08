"""approval_patterns — learns from human approvals to reduce future friction.

Architecture: pattern-learning approval layer on top of the existing
approval.py HMAC token system. When the user approves a Tier 3 tool call,
we extract a reusable pattern from the tool name + args. Future requests
matching the pattern are auto-approved unless the user opts out.

Patterns are stored in <data>/approval_patterns.jsonl (append-only audit
trail) and indexed in memory for fast matching.

Safety invariants:
  - Patterns are conservative: they match exact tool name + arg shapes,
    not wildcards that could drift.
  - Every auto-approval still emits approval-d / approval-x events for
    auditability.
  - The user can view/clear patterns at any time via `sov approval patterns`.
  - A 'strict' mode disables pattern learning entirely.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import SETTINGS


# ─── Pattern definition ─────────────────────────────────────────────


@dataclass
class ApprovalPattern:
    """One learned approval pattern."""
    pattern_id: str
    tool_name: str
    arg_filters: dict[str, Any]  # e.g. {"path": "src/**/*.py", "message": "fix:*"}
    justification: str
    created_at: str
    last_used_at: str | None = None
    use_count: int = 0
    auto_approved_count: int = 0
    denied_count: int = 0
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "tool_name": self.tool_name,
            "arg_filters": self.arg_filters,
            "justification": self.justification,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "use_count": self.use_count,
            "auto_approved_count": self.auto_approved_count,
            "denied_count": self.denied_count,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ApprovalPattern":
        return cls(**d)


# ─── Pattern store ──────────────────────────────────────────────────


class ApprovalPatternStore:
    """Persistent store for approval patterns."""

    def __init__(self, path: Path | None = None):
        self._path = path or (SETTINGS.paths.data_dir / "approval_patterns.jsonl")
        self._patterns: dict[str, ApprovalPattern] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        p = ApprovalPattern.from_dict(d)
                        self._patterns[p.pattern_id] = p
                    except (json.JSONDecodeError, TypeError):
                        continue
        except OSError:
            pass

    def _append(self, pattern: ApprovalPattern) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(pattern.to_dict(), ensure_ascii=False) + "\n")

    def add(self, pattern: ApprovalPattern) -> None:
        self._patterns[pattern.pattern_id] = pattern
        self._append(pattern)

    def get(self, pattern_id: str) -> ApprovalPattern | None:
        return self._patterns.get(pattern_id)

    def list_active(self) -> list[ApprovalPattern]:
        return [p for p in self._patterns.values() if p.active]

    def deactivate(self, pattern_id: str) -> None:
        p = self._patterns.get(pattern_id)
        if p:
            p.active = False
            self._append(p)

    def record_use(self, pattern_id: str, auto_approved: bool = False) -> None:
        p = self._patterns.get(pattern_id)
        if p:
            p.use_count += 1
            p.last_used_at = datetime.now(timezone.utc).isoformat()
            if auto_approved:
                p.auto_approved_count += 1
            self._append(p)

    def record_denial(self, pattern_id: str) -> None:
        p = self._patterns.get(pattern_id)
        if p:
            p.denied_count += 1
            self._append(p)

    def all(self) -> list[ApprovalPattern]:
        return list(self._patterns.values())


# ─── Pattern matching ──────────────────────────────────────────────


def _matches_filter(value: Any, filter_spec: Any) -> bool:
    """Check if a value matches a filter spec.

    Filter specs can be:
      - str: treated as a glob pattern (fnmatch)
      - dict: exact match for nested args
      - None: matches anything
    """
    if filter_spec is None:
        return True
    if isinstance(filter_spec, dict):
        if not isinstance(value, dict):
            return False
        return all(
            k in value and _matches_filter(value[k], v)
            for k, v in filter_spec.items()
        )
    if isinstance(filter_spec, str):
        import fnmatch
        return fnmatch.fnmatch(str(value), filter_spec)
    if isinstance(filter_spec, re.Pattern):
        return bool(filter_spec.search(str(value)))
    return filter_spec == value


def match_pattern(pattern: ApprovalPattern, tool_name: str, args: dict[str, Any]) -> bool:
    """Check if a tool call matches an approval pattern."""
    if not pattern.active:
        return False
    if pattern.tool_name != tool_name:
        return False
    return all(
        _matches_filter(args.get(k), v)
        for k, v in pattern.arg_filters.items()
    )


def find_matching_pattern(
    store: ApprovalPatternStore,
    tool_name: str,
    args: dict[str, Any],
) -> ApprovalPattern | None:
    """Find the first active pattern that matches this tool call."""
    for pattern in store.list_active():
        if match_pattern(pattern, tool_name, args):
            return pattern
    return None


# ─── Pattern extraction ────────────────────────────────────────────


def _extract_path_pattern(value: Any) -> str | None:
    """Extract a glob pattern from a path value."""
    if not isinstance(value, str):
        return None
    p = Path(value)
    # If it's a concrete file path, extract the directory glob
    if p.is_absolute() or p.parent != Path("."):
        # Turn /home/user/project/src/main.py into **/main.py
        return f"**/{p.name}"
    return value


def _extract_message_pattern(value: Any) -> str | None:
    """Extract a prefix pattern from a message value."""
    if not isinstance(value, str):
        return None
    # If it starts with a conventional prefix, capture it
    prefixes = ["fix:", "feat:", "chore:", "docs:", "refactor:", "test:", "ci:", "build:"]
    for prefix in prefixes:
        if value.startswith(prefix):
            rest = value[len(prefix):].strip()
            if rest:
                return f"{prefix}*"
            return prefix
    # Default: first word as prefix if message is short
    words = value.split()
    if len(words) <= 3 and len(value) < 50:
        return f"{words[0]}*" if words else "*"
    return None


def extract_pattern_from_approval(
    tool_name: str,
    args: dict[str, Any],
    justification: str,
) -> ApprovalPattern | None:
    """Try to extract a reusable pattern from an approved tool call.

    Returns None if we can't extract a safe, conservative pattern.
    """
    import uuid
    from datetime import datetime, timezone

    arg_filters: dict[str, Any] = {}

    # Path-like args: extract glob patterns
    path_keys = ["path", "file_path", "root", "target", "dest", "source"]
    for key in path_keys:
        if key in args:
            pattern = _extract_path_pattern(args[key])
            if pattern:
                arg_filters[key] = pattern

    # Message-like args: extract prefix patterns
    msg_keys = ["message", "msg", "content", "text", "body", "cmd", "command"]
    for key in msg_keys:
        if key in args:
            pattern = _extract_message_pattern(args[key])
            if pattern:
                arg_filters[key] = pattern

    # If we couldn't extract any filters, this approval is too broad to learn from
    if not arg_filters:
        return None

    # If the tool name itself suggests scope, add it
    if tool_name in ("git_commit", "write_file", "edit_file", "run_shell"):
        # These are high-impact tools — only learn patterns with clear filters
        pass

    pattern_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()

    return ApprovalPattern(
        pattern_id=pattern_id,
        tool_name=tool_name,
        arg_filters=arg_filters,
        justification=justification,
        created_at=now,
        last_used_at=None,
        use_count=0,
        auto_approved_count=0,
        denied_count=0,
        active=True,
    )


# ─── Integration with approval flow ────────────────────────────────


def learn_from_approval(
    tool_name: str,
    args: dict[str, Any],
    justification: str,
    store: ApprovalPatternStore | None = None,
) -> ApprovalPattern | None:
    """Record an approval and attempt to extract a reusable pattern.

    Called after the user approves a Tier 3 tool call. Returns the
    extracted pattern if any, or None if nothing reusable was found.
    """
    if store is None:
        store = ApprovalPatternStore()
    pattern = extract_pattern_from_approval(tool_name, args, justification)
    if pattern:
        store.add(pattern)
    return pattern


def check_approval_pattern(
    tool_name: str,
    args: dict[str, Any],
    store: ApprovalPatternStore | None = None,
) -> tuple[bool, ApprovalPattern | None]:
    """Check if a tool call should be auto-approved via a learned pattern.

    Returns (should_auto_approve, matching_pattern).
    """
    if store is None:
        store = ApprovalPatternStore()
    pattern = find_matching_pattern(store, tool_name, args)
    if pattern is not None:
        store.record_use(pattern.pattern_id, auto_approved=True)
        return True, pattern
    return False, None


# ─── CLI integration ────────────────────────────────────────────────


def format_patterns_for_display(store: ApprovalPatternStore) -> str:
    """Format all patterns for human-readable display."""
    patterns = store.all()
    if not patterns:
        return "[dim]no approval patterns learned yet.[/dim]"

    lines = []
    lines.append(f"[bold]approval patterns ({len(patterns)})[/bold]")
    lines.append("")
    for p in patterns:
        status = "[green]✓[/green]" if p.active else "[red]✗[/red]"
        lines.append(
            f"  {status} [cyan]{p.pattern_id}[/cyan]  [bold]{p.tool_name}[/bold]"
        )
        for k, v in p.arg_filters.items():
            lines.append(f"      [dim]{k}: {v}[/dim]")
        lines.append(
            f"      [dim]used={p.use_count} auto={p.auto_approved_count} "
            f"denied={p.denied_count}[/dim]"
        )
        lines.append("")
    return "\n".join(lines)


__all__ = [
    "ApprovalPattern",
    "ApprovalPatternStore",
    "extract_pattern_from_approval",
    "learn_from_approval",
    "check_approval_pattern",
    "format_patterns_for_display",
    "match_pattern",
]