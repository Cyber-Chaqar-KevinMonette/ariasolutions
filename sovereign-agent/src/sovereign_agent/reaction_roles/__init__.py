"""reaction_roles — react to an emoji on a message, get (or lose) a role.

Kevin's ask (2026-08-03): a sellable, standing Discord bot feature — starting
with reaction-roles because it needs zero privileged Discord intents
(`guild_reactions` is already in `discord.Intents.default()`, confirmed
against `discord_admin/bot.py`), so there's no verification bottleneck
between building it and eventually listing the bot publicly.

v1 scope: prove it on Kevin's own server first. Storage is genuinely
per-guild-scoped from day one (directory-keyed by `guild_id`, not a single
scalar restriction like `AdminContext.guild_id`) so a later multi-server
phase is a distribution problem, not a rewrite.

  • **Pure logic, no discord.py** — everything here is plain data in/out,
    directly testable. The live wire (two `@client.event` handlers) lives in
    `discord_admin.bot`, patched in by `apply_reaction_roles.sh`; it does the
    minimum (unpack payload, call in here, call Discord, audit_log) and
    nothing more.
  • **One JSON file per guild** (`<data>/reaction_roles/<guild_id>/
    bindings.json`), atomic write (tmp + fsync + replace), corrupt/missing
    file -> empty list — same durable-file convention as `welcome.py` and
    `members.py`.
  • **No dedup ledger for the grant itself** — Discord's `add_roles`/
    `remove_roles` are naturally idempotent (granting a role someone already
    has is a harmless no-op), so unlike `welcome.py`'s "never twice" ledger,
    this only needs an audit trail, not a guard. Every attempt is logged via
    the existing `discord_admin.bot.audit_log()` — deliberately fixing a real
    gap found in that same file: `subscribe_cmd`/`_grant_role` call
    `add_roles`/`remove_roles` with no audit_log at all. This module always
    logs.
  • **Dry-run by default** — `decide_reaction_role_action(..., live=False)`
    (the default posture, gated by `DISCORD_ENABLE_REACTION_ROLE_GRANTS=1` in
    the live wire) never touches Discord, only describes what it would do —
    mirrors `discord_runtime.delivery.DryRunDelivery`'s "default sends
    nothing" doctrine.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "ReactionRoleDecision",
    "emoji_key",
    "bindings_path",
    "add_binding",
    "remove_binding",
    "bindings_for_message",
    "find_binding",
    "list_bindings",
    "decide_reaction_role_action",
    "build_audit_entry",
    "validate_panel_options",
]

_MAX_BINDINGS_PER_GUILD = 200


def emoji_key(emoji_id: int | str | None, emoji_name: str) -> str:
    """Canonical match key for a reaction's emoji: a custom emoji matches by
    its stable snowflake id (name can be renamed by Discord admins); a
    unicode emoji matches by the raw character itself. Never depends on
    discord.py types — callers pass plain values pulled off `payload.emoji`.

    Raises ValueError if neither is present — Discord's own API guarantees
    every real emoji has an id (custom) or a name (unicode); both missing
    means a caller bug, not live gateway data, so this is safe to raise
    (callers on the live gateway path are already wrapped in a broad
    except that audit-logs and no-ops on any exception)."""
    if not emoji_id and not emoji_name:
        raise ValueError("emoji_key requires an emoji_id or an emoji_name")
    if emoji_id:
        return str(emoji_id)
    return str(emoji_name)


def _require_guild_id(guild_id: str) -> str:
    guild_id = str(guild_id or "").strip()
    if not guild_id:
        raise ValueError("guild_id is required — refusing to write an unscoped path")
    return guild_id


# ── per-guild bindings store ─────────────────────────────────────────────────
def _guild_dir(data_dir: Path, guild_id: str) -> Path:
    p = Path(data_dir) / "reaction_roles" / _require_guild_id(guild_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def bindings_path(data_dir: Path, guild_id: str) -> Path:
    if not str(guild_id or "").strip():
        raise ValueError("bindings_path: guild_id is required")
    return _guild_dir(data_dir, guild_id) / "bindings.json"


def _read_bindings(data_dir: Path, guild_id: str) -> list[dict[str, Any]]:
    try:
        raw = json.loads(bindings_path(data_dir, guild_id).read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
    except Exception:  # noqa: BLE001
        return []


def _write_bindings(data_dir: Path, guild_id: str, bindings: list[dict[str, Any]]) -> None:
    path = bindings_path(data_dir, guild_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(bindings), encoding="utf-8")
    with open(tmp, "r+", encoding="utf-8") as fh:
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)


def _emit_binding_event(flag: str, binding_id: str, guild_id: str, extra: dict[str, Any]) -> None:
    """Dual observability, alongside discord_admin.bot's per-guild audit_log:
    binding add/remove also lands in Aria's global events.jsonl (plane
    "discord") so system-wide tooling that reads the event stream sees it
    too, not just Discord admins reading the audit trail. Lazy import (this
    module has zero hard dependency on the events subsystem) and never
    raises — an observability hiccup must never break a real binding
    change, same posture as the storage try/except above."""
    try:
        from ..events import emit_event
        emit_event(flag, plane="discord", trace_id=f"reaction-role:{binding_id}",
                  payload={"guild_id": guild_id, "binding_id": binding_id, **extra})
    except Exception:  # noqa: BLE001
        pass


def add_binding(
    data_dir: Path, guild_id: str, *, message_id: str, channel_id: str,
    emoji_key: str, emoji_display: str, role_id: str, created_by: str,
    now: float | None = None,
) -> dict[str, Any]:
    """Add a binding. Validates required fields up front (raises ValueError
    on any missing one — a binding with e.g. no role_id could never grant
    anything, so refusing it early beats silently persisting a dead entry).
    Storage trouble after validation is swallowed, not raised — matches
    welcome.py's convention of never crashing the caller over a disk hiccup."""
    for field_name, value in (
        ("message_id", message_id), ("channel_id", channel_id),
        ("role_id", role_id), ("created_by", created_by),
    ):
        if not str(value or "").strip():
            raise ValueError(f"add_binding: {field_name} is required")
    guild_id = _require_guild_id(guild_id)
    bindings = _read_bindings(data_dir, guild_id)
    entry = {
        "binding_id": uuid.uuid4().hex[:10],
        "message_id": str(message_id),
        "channel_id": str(channel_id),
        "emoji_key": emoji_key,
        "emoji_display": emoji_display,
        "role_id": str(role_id),
        "created_by": str(created_by),
        "created_at": time.time() if now is None else now,
    }
    bindings.append(entry)
    if len(bindings) > _MAX_BINDINGS_PER_GUILD:
        bindings = bindings[-_MAX_BINDINGS_PER_GUILD:]
    try:
        _write_bindings(data_dir, guild_id, bindings)
    except Exception:  # noqa: BLE001
        pass
    _emit_binding_event("reaction-role-bind-d", entry["binding_id"], guild_id,
                        {"message_id": entry["message_id"], "role_id": entry["role_id"]})
    return entry


def remove_binding(data_dir: Path, guild_id: str, binding_id: str) -> bool:
    """Returns True if a binding was actually removed."""
    if not str(binding_id or "").strip():
        raise ValueError("remove_binding: binding_id is required")
    bindings = _read_bindings(data_dir, guild_id)
    kept = [b for b in bindings if b.get("binding_id") != binding_id]
    if len(kept) == len(bindings):
        return False
    try:
        _write_bindings(data_dir, guild_id, kept)
    except Exception:  # noqa: BLE001
        return False
    _emit_binding_event("reaction-role-unbind-d", binding_id, guild_id, {})
    return True


def bindings_for_message(data_dir: Path, guild_id: str, message_id: str) -> list[dict[str, Any]]:
    if not str(message_id or "").strip():
        raise ValueError("bindings_for_message: message_id is required")
    message_id = str(message_id)
    return [b for b in _read_bindings(data_dir, guild_id) if b.get("message_id") == message_id]


def find_binding(data_dir: Path, guild_id: str, message_id: str, emoji_key_: str) -> dict[str, Any] | None:
    if not str(emoji_key_ or "").strip():
        raise ValueError("find_binding: emoji_key_ is required")
    for b in bindings_for_message(data_dir, guild_id, message_id):
        if b.get("emoji_key") == emoji_key_:
            return b
    return None


def list_bindings(data_dir: Path, guild_id: str) -> list[dict[str, Any]]:
    if not str(guild_id or "").strip():
        raise ValueError("list_bindings: guild_id is required")
    return _read_bindings(data_dir, guild_id)


# ── the decision + audit shape ───────────────────────────────────────────────
@dataclass
class ReactionRoleDecision:
    action: str          # "grant" | "revoke" | "none"
    dry_run: bool
    message: str          # human-readable, e.g. "would grant role 123 to user 456"


def decide_reaction_role_action(
    binding: dict[str, Any] | None, event_type: str, *, live: bool,
) -> ReactionRoleDecision:
    """Pure decision: no binding -> no-op. A matched binding + a reaction add
    -> grant; a reaction remove -> revoke. live=False never implies touching
    Discord regardless of action — the caller must still gate on dry_run.

    `live` must be a real bool, not caller-supplied Discord data — a wrong
    type here is a programmer error, not something the gateway should ever
    silently absorb, so this raises (the live gateway wrapper's broad except
    still keeps this from ever crashing the actual event loop)."""
    if not isinstance(live, bool):
        raise TypeError("decide_reaction_role_action: live must be a bool")
    if binding is None or event_type not in ("add", "remove"):
        return ReactionRoleDecision(action="none", dry_run=not live, message="no matching binding")
    action = "grant" if event_type == "add" else "revoke"
    verb = "would " + action if not live else action
    role_id = binding.get("role_id", "?")
    message = f"{verb} role {role_id}"
    return ReactionRoleDecision(action=action, dry_run=not live, message=message)


def build_audit_entry(
    decision: ReactionRoleDecision, guild_id: str, user_id: str,
    message_id: str, role_id: str,
) -> dict[str, Any]:
    """Pure dict construction, ready for discord_admin.bot.audit_log().
    Requires a real ReactionRoleDecision — an audit entry with no decision
    behind it would misrepresent what happened, so this refuses to build one."""
    if not isinstance(decision, ReactionRoleDecision):
        raise TypeError("build_audit_entry: decision must be a ReactionRoleDecision")
    return {
        "op": "reaction_role",
        "action": decision.action,
        "dry_run": decision.dry_run,
        "guild_id": str(guild_id),
        "user_id": str(user_id),
        "message_id": str(message_id),
        "role_id": str(role_id),
        "detail": decision.message,
    }


def validate_panel_options(emoji_keys: list[str]) -> None:
    """Guard for /reaction-role-panel (2026-08-04): a panel needs at least
    one option, and can't offer the same reaction twice — Discord itself
    would just merge duplicate emoji into one reaction, silently breaking
    the second binding. Raises ValueError; callers check before posting
    anything, so nothing gets published then has to be corrected."""
    if not emoji_keys:
        raise ValueError("validate_panel_options: at least one option is required")
    if len(emoji_keys) != len(set(emoji_keys)):
        raise ValueError("validate_panel_options: duplicate emoji in panel options")
