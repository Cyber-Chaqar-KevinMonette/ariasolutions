"""discord_admin — the owner-gated admin bot that can edit the server.

Safe by construction: owner-only commands, dry-run-first, create-only
auto-setup (never deletes), full audit trail. discord.py is optional + lazy
so the pure logic (blueprint/planner/gate) imports and tests without it.
"""
from __future__ import annotations

from .blueprint import (
    CategorySpec,
    ChannelSpec,
    RoleSpec,
    ServerBlueprint,
    shop_blueprint,
)
from .bot import COMMANDS, plan_for_guild, run_admin_bot
from .gate import GateResult, check_command, is_owner, needs_confirmation
from .planner import Action, CurrentState, plan, render_plan

__all__ = [
    "shop_blueprint",
    "ServerBlueprint",
    "RoleSpec",
    "CategorySpec",
    "ChannelSpec",
    "plan",
    "render_plan",
    "Action",
    "CurrentState",
    "check_command",
    "is_owner",
    "needs_confirmation",
    "GateResult",
    "COMMANDS",
    "plan_for_guild",
    "run_admin_bot",
]
