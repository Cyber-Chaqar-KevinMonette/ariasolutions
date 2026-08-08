"""bot — the admin bot that edits the server, owner-gated and dry-run-first.

The one privileged piece: a real Discord bot (discord.py, optional + lazy)
that can build/repair the server from the blueprint and run slash commands.
Every command passes `gate.check_command` (owner-only; destructive needs
confirm), the auto-setup is create-only (planner), and every applied action
is audit-logged.

discord.py is imported lazily inside `run_admin_bot`, so importing this module
(and running the pure tests) never requires it. You only need it installed +
a bot token to actually run the bot.

Slash commands (all owner-only unless noted):
  /plan-shop     — dry-run: show what setup WOULD create (safe, read-only)
  /setup-shop    — build/repair the whole server from the blueprint
  /create-channel <name> <category>
  /create-role   <name> [color]
  /whoami        — are you recognized as the owner? (anyone can run)
  /help          — list commands

## How to add a new command (documented once, here)
Add an `@tree.command` coroutine inside `_register_commands` below. Gate it
with `_guard(interaction, op=...)` for anything that changes the server, then
do the work and `await interaction.response.send_message(...)`. Append it to
`COMMANDS` so it shows in `/help` and the docs. That's the whole recipe.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path

from .blueprint import shop_blueprint
from .gate import check_command
from .planner import CurrentState, plan, render_plan

__all__ = ["COMMANDS", "AdminContext", "plan_for_guild", "audit_log", "run_admin_bot"]

# help-boards-d (Kevin, 2026-07-27): "make a help command for admins,
# for subscribers, and for new members... so everyone has their
# respective command boards." This list had quietly drifted — 18 real,
# registered commands were missing from it, and 4 separate hand-written
# embeds (/help, /menu, /admin, /admin-panel+/theorules) were each their
# OWN independent, silently-decaying copy of "what can you do here."
# ONE audited, complete list now, with an explicit `audience` tier per
# command (verified against each command's REAL gate in code, not just
# guessed from its description) — every help surface below is BUILT
# from this, filtered + sectioned, so a new command only has to be
# added here once to show up everywhere it should.
#
# audience tiers (least → most access; a panel for tier X shows every
# command at tier X or below):
#   "everyone"   — no gate at all, open to a brand-new joiner.
#   "subscriber" — technically reachable by anyone, but only really
#                  useful/intended for an active subscriber (or staff/
#                  owner) — e.g. /ma's real gate is is_eligible(), which
#                  allows exactly that set.
#   "team"       — is_team()/_is_staff(): owner + staff (Camden).
#   "owner"      — is_owner() or _guard() (verified: _guard's
#                  check_command() is owner-only, no team exception).
COMMANDS: list[tuple[str, str, str]] = [
    ("/ask", "Ask Aria anything — the shop, the bots, or just to chat.", "everyone"),
    ("/consumer-law", "⚖️ Consumer-law info (debt collection, credit reports, loans) — general info, not legal advice.", "everyone"),
    ("/funding", "💰 Business funding reference — SBA loans, state grant portals, lender resources.", "everyone"),
    ("/whoami", "Check whether you're recognized as the owner.", "everyone"),
    ("/help", "📖 Commands anyone can use — new here? Start here.", "everyone"),
    ("/menu", "📋 Your commands — everyone, plus more if you're a subscriber.", "everyone"),
    ("/tip", "💛 Tip the shop — support the 24/7 bots (optional).", "everyone"),
    ("/buy", "🛒 Your personal buy links — purchases recognize you automatically.", "everyone"),
    ("/passes", "🎟 24-hour/week/month/year all-access passes — one tap to buy, no subscription.", "everyone"),
    ("/redeem", "💳 Link your Stripe purchase to unlock your access + timer.", "everyone"),
    ("/level", "⭐ Your activity level, xp and progress.", "everyone"),
    ("/levels", "🏆 Most active members by activity level.", "everyone"),
    ("/lesson", "📖 The next lesson, from your own codebase.", "owner"),
    ("/drill", "🧪 The next exercise to write and run.", "owner"),
    ("/submit", "🚀 Run your drill answer and get it graded.", "owner"),
    ("/progress", "📈 Your coding progress and what's due.", "owner"),
    ("/subscription", "⏳ Your plan, time left + bonus questions.", "everyone"),
    ("/usage", "📊 Your daily usage meter — answers left, plan, credits.", "everyone"),
    ("/refer", "🤝 Your referral code — grow the circle, earn credits together.", "everyone"),
    ("/earnings", "📊 Your rank, credits + earnings — private to you.", "everyone"),
    ("/leaderboard", "🏆 Community champions — top circle-growers.", "everyone"),
    ("/scout", "🌐 The Scout Hub — every tracker, finds private to you.", "everyone"),
    ("/subscribe", "🔔 Subscribe to a tracker channel — it becomes visible + you get pinged on drops.", "everyone"),
    ("/unsubscribe", "🔕 Unsubscribe from a tracker channel — it disappears + pings stop.", "everyone"),
    ("/my-panel", "& Your subscribe panel — category buttons + per-channel fine-tuning, mobile-friendly.", "everyone"),
    ("/local", "📍 Pull a report of finds near your saved area, right now (private to you).", "everyone"),
    ("/wf-lookup", "🔍 Warframe Market — look up an item's real buyers, ranked by profit.", "everyone"),
    ("/vaulted-relics", "🔒 Warframe Prime Vault — every vaulted Warframe, its parts, and the relics that drop them.", "everyone"),
    ("/ticket", "🎫 Open a private support ticket.", "everyone"),
    ("/mead-access", "🍯 Enter the 21+ Mead Lounge (self-attest).", "everyone"),
    ("/mead-recipe", "🍯 Get a mead recipe (21+). Blank = list styles.", "everyone"),
    ("/mead-suggest", "🍯 Personalized mead suggestions (21+).", "everyone"),
    ("/mead-taste", "🍯 Set your flavor palate.", "everyone"),
    ("/mead-rate", "🍯 Rate a mead recipe 1-5 — sharpens your profile.", "everyone"),
    ("/ma", "✉ Message Aria — the owner's private line to her inbox.", "owner"),
    ("/mod-report", "🛡 Recent moderation actions.", "team"),
    ("/mod-unmute", "🔊 Lift a member's mute.", "team"),
    ("/mod-history", "🛡 A member's moderation history.", "team"),
    ("/tickets", "🎫 The open-ticket board.", "team"),
    ("/admin-panel", "🛠 Team control panel — bridge/grants/bot control quick reference.", "team"),
    ("/theorules", "🛠 Theodore's own shortcut to /admin-panel — same panel.", "team"),
    ("/plan-shop", "Dry-run: show what setup would create (safe, read-only).", "team"),
    ("/admin", "🛠 Owner command menu — everything above, plus owner-exclusive controls.", "owner"),
    ("/maa", "⚛ Message Aria's Angel — her non-classical layer, from anywhere.", "owner"),
    ("/grant", "⏳ Grant/extend a member's plan + timer.", "owner"),
    ("/redemptions", "🧾 Who needs redeeming + what they get (read-only).", "owner"),
    ("/marketer", "🤝 Toggle a member's marketer status — unlocks 25% referral commissions.", "owner"),
    ("/tracker", "🔌 Turn one tracker vertical on or off, fleet-wide.", "owner"),
    ("/roster", "The client database — who she knows by ID.", "owner"),
    ("/ticket-panel", "Post the 'Open a Ticket' panel here.", "owner"),
    ("/scout-panel", "Post the living Scout Hub in this channel.", "owner"),
    ("/seed-channels", "Fill every channel with its guide/rules post (idempotent).", "owner"),
    ("/scan-server", "Audit the live server vs the plan — what's missing.", "owner"),
    ("/setup-shop", "Build/repair the whole server from the blueprint.", "owner"),
    ("/reorder-server", "↕ Put categories + channels in blueprint order (moves only).", "owner"),
    ("/setup-webhooks", "Create the shop webhooks + vault their URLs, untouched by hands.", "owner"),
    ("/setup-all", "🚀 The whole setup in one shot: shop → webhooks → guides.", "owner"),
    ("/audit-channels", "Consolidation worksheet: every channel beyond the blueprint.", "owner"),
    ("/cleanup-orphans", "Delete the listed orphan channels — typed confirm.", "owner"),
    ("/clear-channel", "🧹 Clear every message in THIS channel, then repost its guide — typed confirm.", "owner"),
    ("/clear-all-channels", "🧹 Clear EVERY public channel server-wide, repost guides — typed confirm.", "owner"),
    ("/create-channel", "Create a channel in a category.", "owner"),
    ("/create-role", "Create a role with an optional color.", "owner"),
    ("/reaction-role-add", "🎭 Bind an emoji on a message to a role.", "team"),
    ("/reaction-role-remove", "🎭 Remove a reaction-role binding.", "team"),
    ("/reaction-role-list", "🎭 List reaction-role bindings.", "team"),
    ("/reaction-role-panel", "🎭 Post a reaction-role panel with up to 5 options in one shot.", "team"),
]

# help-boards-d: which readable section a command belongs in, by name
# prefix/keyword — presentation-only grouping, layered on top of the
# audience tiers above (a command's SECTION never changes who can see
# it, just how it's organized within a panel).
_COMMAND_SECTIONS: list[tuple[str, str]] = [
    ("help", "📖 Help & Panels"),
    ("menu", "📖 Help & Panels"),
    ("admin", "📖 Help & Panels"),
    ("theorules", "📖 Help & Panels"),
    ("whoami", "📖 Help & Panels"),
    ("mead-", "🍯 Mead Lounge (21+)"),
    ("mod-", "🛡 Moderation"),
    ("ticket", "🎫 Support Tickets"),
    ("wf-", "🎮 Warframe"),
    ("scout", "🌐 Trackers & Scout"),
    ("subscribe", "🌐 Trackers & Scout"),
    ("my-panel", "🌐 Trackers & Scout"),
    ("local", "🌐 Trackers & Scout"),
    ("tracker", "🌐 Trackers & Scout"),
    ("refer", "🤝 Referrals"),
    ("earnings", "🤝 Referrals"),
    ("leaderboard", "🤝 Referrals"),
    ("marketer", "🤝 Referrals"),
    ("buy", "🎟 Access & Billing"),
    ("passes", "🎟 Access & Billing"),
    ("redeem", "🎟 Access & Billing"),
    ("subscription", "🎟 Access & Billing"),
    ("usage", "🎟 Access & Billing"),
    ("redemptions", "🎟 Access & Billing"),
    ("grant", "🎟 Access & Billing"),
    ("roster", "🎟 Access & Billing"),
    ("setup", "🌉 Server Setup"),
    ("scan-server", "🌉 Server Setup"),
    ("seed-channels", "🌉 Server Setup"),
    ("audit-channels", "🌉 Server Setup"),
    ("cleanup-orphans", "🌉 Server Setup"),
    ("clear-channel", "🌉 Server Setup"),
    ("clear-all-channels", "🌉 Server Setup"),
    ("create-channel", "🌉 Server Setup"),
    ("create-role", "🌉 Server Setup"),
    ("plan-shop", "🌉 Server Setup"),
]


def _command_section(name: str) -> str:
    bare = name.lstrip("/")
    for needle, section in _COMMAND_SECTIONS:
        if needle in bare:
            return section
    return "💬 Talk to Aria"


_AUDIENCE_RANK = {"everyone": 0, "subscriber": 1, "team": 2, "owner": 3}


def build_commands_embed(title: str, color: int, max_tier: str, *,
                         intro: str = "") -> "discord.Embed":  # noqa: F821
    """help-boards-d: the ONE builder every help surface below calls —
    filters `COMMANDS` to everything at or below `max_tier`, groups by
    section, renders as an embed. A command added to `COMMANDS` once
    shows up in every panel it belongs in automatically; nothing to
    hand-maintain per-panel again."""
    import discord
    cap = _AUDIENCE_RANK.get(max_tier, 0)
    by_section: dict[str, list[str]] = {}
    for name, desc, audience in COMMANDS:
        if _AUDIENCE_RANK.get(audience, 0) > cap:
            continue
        by_section.setdefault(_command_section(name), []).append(f"`{name}` — {desc}")
    emb = discord.Embed(title=title, color=color)
    if intro:
        emb.description = intro
    for section, lines in by_section.items():
        value = "\n".join(lines)
        emb.add_field(name=section, value=value[:1024], inline=False)
    return emb


@dataclass
class AdminContext:
    owner_id: str
    guild_id: str
    audit_path: Path


def plan_for_guild(existing_roles, existing_categories, existing_channels):
    """Pure: the create-only plan given what already exists (by name)."""
    current = CurrentState(roles=set(existing_roles),
                           categories=set(existing_categories),
                           channels=set(existing_channels))
    return plan(shop_blueprint(), current)


def build_my_panel_view(member_role_names: set, focus_category: str | None = None):
    """my-panel-d (Kevin, 2026-07-26): a category picker (bulk on/off) +
    a per-category fine-tune dropdown. Module-level (not a closure) so
    it's directly testable.

    panel-redesign-d (Kevin, 2026-07-27): 2026-07-27 a hardcoded
    utility-button row broke /my-panel outright once the category count
    grew past what that row could hold alongside them (`ValueError:
    item would not fit at row 2 (6 > 5 width)`, a real incident). The
    row-packing fix that followed was still fundamentally a wall of ONE
    BUTTON PER CATEGORY, which only ever had ~20 categories of headroom
    before hitting Discord's hard 25-components-per-view ceiling no
    row-math can work around. Redesigned properly this time: ONE select
    dropdown holds up to 25 categories in the space of a single row —
    picking an option does the exact same bulk subscribe/unsubscribe
    Kevin's original buttons did (see the `mypanel:catselect` handler),
    then reveals the same per-channel fine-tune select as before. This
    structurally can't hit a row-width problem again; the only ceiling
    left is Discord's 25-categories-in-one-dropdown limit, which is
    ~2x today's real count (13) and doesn't creep up nearly as fast as
    "how many rows do N buttons need.\""""
    import discord

    from sovereign_agent.verticals import subscribable_categories
    cats = subscribable_categories()
    view = discord.ui.View(timeout=300)
    picker_opts = []
    for cat, verts in cats.items():
        if not verts:
            continue
        subscribed = sum(1 for v in verts if v.ping_role in member_role_names)
        total = len(verts)
        icon = "🔔" if subscribed == total else "🔕" if subscribed == 0 else "◐"
        # panel-d (Kevin, 2026-08-04): short LABEL only — `value` stays the
        # real category name, because that's what the select handler and the
        # fine-tune custom_id match on.
        from sovereign_agent.verticals import panel_label
        picker_opts.append(discord.SelectOption(
            label=f"{icon} {panel_label(cat)} ({subscribed}/{total})"[:100],
            value=cat, default=(cat == focus_category)))
    if picker_opts:
        view.add_item(discord.ui.Select(
            placeholder="pick a category to subscribe/unsubscribe…",
            options=picker_opts[:25], custom_id="mypanel:catselect"))
    # my-panel-d (Kevin, 2026-07-26): "make it where we can change the
    # zip code or radius anytime" — always available. location-filter-d
    # (Kevin, 2026-07-27): "so I can enter a channel and request
    # reports" + "two ping modes a customer can choose from... one all
    # day mode, or just batch reporting mode." Batch (the "near me now"
    # button) always works; Live additionally DMs in real time — a
    # per-member toggle, not a forced behavior. Deliberately no `row=` —
    # discord.py auto-packs a rowless item into the first row with
    # spare width, so these just land after the picker select.
    view.add_item(discord.ui.Button(
        label="📍 change area", custom_id="mypanel:area",
        style=discord.ButtonStyle.secondary))
    view.add_item(discord.ui.Button(
        label="📡 ping mode", custom_id="mypanel:pingmode",
        style=discord.ButtonStyle.secondary))
    view.add_item(discord.ui.Button(
        label="📍 near me now", custom_id="mypanel:nearme",
        style=discord.ButtonStyle.secondary))
    if focus_category and cats.get(focus_category):
        verts = cats[focus_category]
        opts = [discord.SelectOption(
            label=f"{v.emoji} {v.name}"[:100], value=v.slug,
            description=v.blurb[:100],
            default=(v.ping_role in member_role_names))
            for v in verts[:25]]
        try:
            view.add_item(discord.ui.Select(
                placeholder=f"fine-tune {focus_category} channels…",
                options=opts, min_values=0, max_values=len(opts),
                custom_id=f"mypanel:sel:{focus_category}", row=4))
        except ValueError:  # noqa: BLE001 — no room left; the buttons above still work
            pass
    return view


def audit_log(audit_path: Path, entry: dict) -> None:
    """Append one audit record; never raises."""
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"ts": time.time(), **entry}
        with open(audit_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def admin_audit_path(data_dir: Path) -> Path:
    return Path(data_dir) / "discord_admin" / "audit.jsonl"


# owner-bridge-remote-d (Kevin, 2026-07-25): "I want to be able to message
# her from discord and start sessions with her and work sessions and auto
# work sessions etc.. Maybe add additional hours and all the above." A
# real, second entry point into the SAME functions the cockpit's own
# slash commands already call — session_bridge.start_goal_session()
# already defaults to Mode.BUSY (tier-1 bounded, the exact ceiling /work
# uses in the cockpit) and arm_custom_hours()/AutoCrownStore already
# refuse cleanly when the trust tier isn't unlocked. Nothing here bypasses
# a safety gate that exists elsewhere — it's the same gates, a second door.
# Owner-only (checked by the caller, #owner-bridge is already private-by-
# build); a plain message with no command prefix queues via the EXISTING
# no-interrupt operator-message mechanism (session_bridge.
# queue_operator_message) so it reaches her at her next safe boundary,
# same as a message typed at the cockpit while she's mid-session.
async def handle_owner_bridge_message(content: str, send, *,
                                      audit_path: Path | None = None) -> None:
    """`send(text)` is awaited to reply (matches discord.TextChannel.send's
    shape so the real on_message handler can pass `message.channel.send`
    directly; tests pass a plain async stub). Never raises — every branch
    is its own try/except so one bad command can't break the listener."""
    import asyncio

    content = (content or "").strip()
    if not content:
        return
    parts = content.split(None, 1)
    verb = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    def _audit(op: str, **fields) -> None:
        if audit_path is not None:
            audit_log(audit_path, {"op": f"owner-bridge-{op}", **fields})

    if verb in ("!work", "!session"):
        if not rest:
            await send("usage: !work <goal>")
            return
        await send(f"🛠 starting: {rest[:150]}")

        async def _run() -> None:
            try:
                from sovereign_agent import session_bridge
                result = await session_bridge.start_goal_session(rest)
                await send(f"✅ session finished: {getattr(result, 'status', '?')}")
            except Exception as exc:  # noqa: BLE001
                await send(f"✗ session failed: {type(exc).__name__}: {exc}")

        asyncio.create_task(_run())  # fire-and-forget — never blocks the listener
        _audit("work", goal=rest[:150])
        return

    if verb == "!auto":
        try:
            hours = float(rest)
        except ValueError:
            await send("usage: !auto <hours> (1-12)")
            return
        try:
            from sovereign_agent.modes_crown.profiles import arm_custom_hours
            profile = await asyncio.to_thread(arm_custom_hours, hours)
            await send(f"🌙 auto armed — {profile.description}")
        except Exception as exc:  # noqa: BLE001
            await send(f"✗ auto arm failed: {exc}")
        _audit("auto", hours=rest)
        return

    if verb == "!addtime":
        try:
            hours = float(rest) if rest else 1.0
        except ValueError:
            await send("usage: !addtime <hours>")
            return
        try:
            from sovereign_agent.auto_crown import get_auto_crown_store
            store = get_auto_crown_store()
            session = await asyncio.to_thread(store.extend, hours)
            tier_extended = await asyncio.to_thread(store.extend_trust_tier, hours)
            remaining_min = session.remaining_minutes()
            h, m = divmod(int(remaining_min), 60)
            note = " · elevated tier extended too" if tier_extended else ""
            await send(f"⏰ +{hours:g}h added — {h}h{m:02d}m remaining{note}")
        except ValueError as exc:
            await send(f"✗ {exc} — arm one first with !auto <hours>")
        except Exception as exc:  # noqa: BLE001
            await send(f"✗ addtime failed: {exc}")
        _audit("addtime", hours=rest)
        return

    if verb == "!status":
        try:
            from sovereign_agent.auto_crown import get_auto_crown_store
            store = get_auto_crown_store()
            status = await asyncio.to_thread(store.status)
            if status is None or status.status != "active":
                await send("○ no active auto session — Semi-Auto")
            else:
                remaining_min = status.remaining_minutes()
                h, m = divmod(int(remaining_min), 60)
                await send(f"🌙 AUTO active — {h}h{m:02d}m remaining · "
                          f"T{status.trust_tier}")
        except Exception as exc:  # noqa: BLE001
            await send(f"✗ status failed: {exc}")
        return

    # no command prefix — a plain message, queued for her next safe
    # checkpoint (session_bridge's existing no-interrupt-mid-session rule).
    try:
        from sovereign_agent import session_bridge
        await asyncio.to_thread(session_bridge.queue_operator_message, content)
        await send("📥 queued — I'll see this at my next safe checkpoint.")
        _audit("message", len=len(content))
    except Exception as exc:  # noqa: BLE001
        await send(f"✗ couldn't queue that: {type(exc).__name__}")


def run_admin_bot(token: str, *, owner_id: str, guild_id: str | None = None,
                  data_dir: Path | None = None) -> None:  # pragma: no cover - needs a live token
    """Connect and serve. Requires discord.py + a bot token. Not unit-tested
    against live Discord (honest boundary) — the pure logic above is."""
    try:
        import discord
        from discord import app_commands
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "discord.py is not installed. Install it in the venv first:\n"
            "  .venv/bin/pip install discord.py") from exc

    # discord is imported lazily (so this module imports without it for the
    # pure-logic tests). But slash-command param annotations like
    # `user: discord.Member` are resolved by discord.py via the callback's
    # MODULE globals (get_type_hints) — not this function's locals — so we
    # publish the names into module globals here. Without this, such a command
    # raises NameError at registration and aborts every command after it.
    globals()["discord"] = discord
    globals()["app_commands"] = app_commands

    if data_dir is None:
        from sovereign_agent.config import SETTINGS
        data_dir = SETTINGS.paths.data_dir
    ctx = AdminContext(owner_id=str(owner_id), guild_id=str(guild_id or ""),
                       audit_path=admin_audit_path(data_dir))

    # rate-limit-d (Kevin): heavy server-mutating ops (setup-shop, setup-
    # webhooks, seed-channels) take a turn on this lock so they never run
    # concurrently and stomp each other. Plus a gentle per-send pace so bulk
    # posting stays well inside Discord's rate limits (discord.py also
    # auto-throttles per route; this keeps bursts polite on top of that).
    _admin_lock = asyncio.Lock()
    _SEND_PACE_S = 0.4

    async def _paced_send(channel, content):
        await channel.send(content)
        await asyncio.sleep(_SEND_PACE_S)

    intents = discord.Intents.default()
    # ask-aria-d — free-chat in #ask-aria needs the privileged Message
    # Content intent (a portal toggle). Requesting it WITHOUT the toggle
    # makes login fail, so it's opt-in via env: enable the toggle in the
    # dev portal (Bot → Message Content Intent), then set
    # DISCORD_ENABLE_CHAT_INTENT=1. /ask works either way.
    import os as _os
    chat_intent = (_os.environ.get("DISCORD_ENABLE_CHAT_INTENT") or "") == "1"
    if chat_intent:
        intents.message_content = True
    # welcome-d — greeting new members needs the privileged Server Members
    # intent (portal toggle: Bot → Server Members Intent). Same opt-in
    # pattern: toggle it on, then set DISCORD_ENABLE_MEMBERS_INTENT=1.
    members_intent = (_os.environ.get("DISCORD_ENABLE_MEMBERS_INTENT") or "") == "1"
    if members_intent:
        intents.members = True
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    async def _guard(interaction, op: str, confirm: bool = False) -> bool:
        res = check_command(user_id=interaction.user.id, owner_id=ctx.owner_id,
                            op=op, confirm=confirm)
        if not res.allowed:
            await interaction.response.send_message(f"⛔ {res.reason}", ephemeral=True)
            audit_log(ctx.audit_path, {"op": op, "user": str(interaction.user.id),
                                       "allowed": False, "reason": res.reason})
        return res.allowed

    def _overwrite(guild):
        everyone = guild.default_role

        def build(allow_names, deny_names):
            ow = discord.PermissionOverwrite()
            for n in allow_names:
                setattr(ow, n, True)
            for n in deny_names:
                setattr(ow, n, False)
            return ow
        return everyone, build

    async def _apply(guild, actions, interaction) -> str:
        from .blueprint import canon_name
        created, perms = 0, 0
        everyone, build = _overwrite(guild)
        # canonical-name lookups: Kevin's decorated names ("🛒 SHOP") must
        # resolve as the plan's plain names — decoration is never drift
        role_by_name = {canon_name(r.name): r for r in guild.roles}
        cat_by_name = {canon_name(c.name): c for c in guild.categories}
        # bestbuy-category-d (Kevin, 2026-07-27): guild.channels ALSO
        # includes category objects (a Discord category IS a channel,
        # type=category, in the raw API) — using it here silently ate a
        # new text channel whenever its name matched an existing
        # category's (a real "#computers" channel next to the existing
        # "COMPUTERS" category, live-caught the same evening). Categories
        # and text channels are separate concepts in the blueprint;
        # text_channels keeps that true here too.
        chan_by_name = {canon_name(c.name): c for c in guild.text_channels}
        for a in actions:
            try:
                if a.op == "create_role" and canon_name(a.name) not in role_by_name:
                    r = await guild.create_role(
                        name=a.name, colour=discord.Colour(a.params.get("color_int", 0)),
                        hoist=a.params.get("hoist", True))
                    role_by_name[canon_name(a.name)] = r
                    created += 1
                elif a.op == "create_category" and canon_name(a.name) not in cat_by_name:
                    c = await guild.create_category(a.name)
                    cat_by_name[canon_name(a.name)] = c
                    created += 1
                elif a.op == "create_channel" and canon_name(a.name) not in chan_by_name:
                    parent = cat_by_name.get(canon_name(a.params.get("category")))
                    # mead-d: age_restricted → Discord's native 18+ (nsfw) gate
                    c = await guild.create_text_channel(
                        a.name, category=parent,
                        nsfw=bool(a.params.get("age_restricted", False)))
                    chan_by_name[canon_name(a.name)] = c
                    created += 1
                elif a.op == "overwrite":
                    target = (everyone if a.params["target"] == "@everyone"
                              else role_by_name.get(canon_name(a.params["target"])))
                    obj = (cat_by_name if a.params["scope"] == "category"
                           else chan_by_name).get(canon_name(a.name))
                    if target is not None and obj is not None:
                        ow = build(a.params.get("allow", []), a.params.get("deny", []))
                        await obj.set_permissions(target, overwrite=ow)
                        perms += 1
                audit_log(ctx.audit_path, {"op": a.op, "name": a.name, "applied": True})
            except Exception as exc:  # noqa: BLE001 — one failure shouldn't abort the rest
                audit_log(ctx.audit_path, {"op": a.op, "name": a.name,
                                           "error": f"{type(exc).__name__}: {exc}"})
        return f"✅ done — created {created}, applied {perms} permission rule(s)."

    async def _answer(question: str, user_id) -> str:
        """Her voice — the bounded core runs off the event loop so a slow
        model can never freeze the gateway (heartbeats keep flowing)."""
        import asyncio
        from sovereign_agent.ask_aria import answer_question
        reply = await asyncio.to_thread(
            answer_question, question, user_id=str(user_id), data_dir=data_dir)
        return reply.text

    def _register_commands():
        @tree.command(name="consumer-law",
                      description="Consumer-law info (debt collection, credit "
                                  "reports, loans) — general info, not legal advice.")
        async def consumer_law(interaction, question: str):
            # everyone may ask — deterministic, no LLM call, no rate limit needed
            from sovereign_agent.consumer_law_companion import answer_consumer_law_question
            ans = answer_consumer_law_question(question)
            from sovereign_agent.discord_limits import split_text
            parts = split_text(ans.as_text(), 1900) or ["💛"]
            await interaction.response.send_message(parts[0], ephemeral=False)
            for part in parts[1:4]:
                await interaction.followup.send(part)

        @tree.command(name="funding",
                      description="Business funding reference — SBA loans, "
                                  "state grant portals, lender resources.")
        async def funding(interaction):
            from sovereign_agent.business_funding_directory import (
                GENERAL_LENDERS, SBA_PROGRAMS, STATE_INCENTIVE_PORTALS)
            lines = ["**SBA Loan Programs**"]
            for p in SBA_PROGRAMS:
                lines.append(f"• **{p.name}** — {p.note} ({p.url})")
            lines.append("\n**State Grant Portals**")
            for p in STATE_INCENTIVE_PORTALS:
                lines.append(f"• **{p.name}** — {p.note} ({p.url})")
            lines.append("\n**General Resources**")
            for p in GENERAL_LENDERS:
                url_part = f" ({p.url})" if p.url else ""
                lines.append(f"• **{p.name}** — {p.note}{url_part}")
            lines.append("\nSee also #business-grants for live federal grant listings.")
            from sovereign_agent.discord_limits import split_text
            parts = split_text("\n".join(lines), 1900) or ["💛"]
            await interaction.response.send_message(parts[0], ephemeral=False)
            for part in parts[1:4]:
                await interaction.followup.send(part)

        @tree.command(name="ask",
                      description="Ask Aria anything — the shop, the bots, or just to chat.")
        async def ask(interaction, question: str):
            # everyone may ask — the core rate-limits per user + globally
            await interaction.response.defer()      # public reply, takes a moment
            text = await _answer(question, interaction.user.id)
            # empty = the core chose silence (anti-spam) — a slash command
            # still needs SOME followup. limits-d: long answers become
            # SEVERAL messages split at natural seams, never a mid-thought
            # chop (Kevin: "she can send multiple messages and be smart").
            from sovereign_agent.discord_limits import split_text
            parts = split_text(text, 1900) or ["💛"]
            for part in parts[:4]:                  # bounded, never a flood
                await interaction.followup.send(part)

        @tree.command(name="ma",
                      description="✉ Message Aria — the owner's private line.")
        async def ma(interaction, message: str):
            # member-mail-d (Kevin, 2026-07-17): a direct line to Aria's
            # collaboration inbox. Mail, not a command — she reads it at
            # her own safe checkpoints. Eligibility + daily cap are pure
            # and tested in member_mail.py.
            import asyncio
            from sovereign_agent.member_mail import (
                deliver_ma, is_eligible, take_quota)
            user = interaction.user
            is_owner = str(user.id) == ctx.owner_id
            # ma-owner-only-d (Kevin, 2026-08-04): "only I am allowed to use
            # /ma." This is his direct line to Aria's collaboration inbox —
            # not a support channel — so it is now owner-gated ahead of the
            # older subscriber/staff eligibility rule. That rule is left
            # intact below (member_mail.is_eligible and its quota are still
            # tested and still correct) so widening this back out later is
            # deleting this block, not rebuilding the check.
            if not is_owner:
                await interaction.response.send_message(
                    "✉ /ma is the owner's private line to me. Use `/ask` "
                    "anywhere, or `/ticket` for a private thread with staff "
                    "— both reach a human. 💛",
                    ephemeral=True)
                return
            roles = [r.name for r in getattr(user, "roles", []) or []]
            if not is_eligible(author_id=str(user.id), owner_id=ctx.owner_id,
                               role_names=roles):
                await interaction.response.send_message(
                    "✉ /ma isn't available to you right now — but you can "
                    "always talk to me with /ask or in #ask-aria! 💛",
                    ephemeral=True)
                return
            # everything past eligibility may take seconds (weather lookup,
            # her live voice) — defer first, follow up when ready
            await interaction.response.defer(ephemeral=True)
            if not is_owner and not await asyncio.to_thread(
                    take_quota, data_dir, str(user.id)):
                await interaction.followup.send(
                    "✉ You've reached today's /ma limit — I promise I read "
                    "them all. /ask is always open. 💛", ephemeral=True)
                return
            receipt = await asyncio.to_thread(
                deliver_ma, message, author_id=str(user.id),
                author_name=user.display_name, is_owner=is_owner)
            audit_log(ctx.audit_path, {
                "op": "ma", "user": str(user.id),
                "owner": is_owner, "preview": str(message)[:80],
                "applied": True})
            # weather-d (Kevin, 2026-07-17): mail always lands in her inbox,
            # AND she answers what she can on the spot (weather lookups, shop
            # questions, her live voice when awake) — best-effort, never
            # blocks the receipt.
            answer = ""
            try:
                answer = await _answer(message, user.id)
            except Exception:  # noqa: BLE001
                answer = ""
            body = receipt if not answer else f"{receipt}\n\n{answer}"
            from sovereign_agent.discord_limits import split_text
            for part in split_text(body, 1900)[:3] or ["💛"]:
                await interaction.followup.send(part, ephemeral=True)

        @tree.command(name="maa",
                      description="⚛ Message Aria's Angel — her non-"
                                  "classical layer, from anywhere (owner).")
        @discord.app_commands.describe(
            message="speak (fresh run) · status (latest run) · "
                   "who are you · anything else gets the honest explainer")
        async def maa(interaction, message: str = "status"):
            # angel-chat-slash-d (Kevin, 2026-07-19: "/maa for message
            # aria angel for short"): the #angel-voice channel is the
            # durable log (type there, plain messages); /maa is the fast
            # path — works from any channel or DM, no need to be in
            # #angel-voice first. Same owner-only gate as the channel
            # itself (defense in depth — the angel is never a public
            # surface). 'speak' runs a real bounded engine subprocess
            # (up to ~2 min) so this defers immediately.
            is_owner = str(interaction.user.id) == ctx.owner_id
            if not is_owner:
                await interaction.response.send_message(
                    "⚛ Her angel voice is an owner-only line for now — "
                    "but /ask always reaches ME! 💛", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            from sovereign_agent.angel_chat import respond as _angel_respond
            from sovereign_agent.discord_limits import split_text
            reply = await asyncio.to_thread(_angel_respond, message)
            audit_log(ctx.audit_path, {"op": "maa",
                                       "preview": str(message)[:80]})
            for part in split_text(reply, 1900)[:3] or ["⚛"]:
                await interaction.followup.send(part, ephemeral=True)

        @tree.command(name="plan-shop", description="Dry-run: show what setup would create (safe).")
        async def plan_shop(interaction):
            # plan-shop-timeout-d (Kevin, 2026-08-03): "the application did
            # not respond." Discord hard-requires an ack within 3s, and
            # plan_for_guild() walks every role + category + channel first
            # (109 channels live), so on a grown server the reply always
            # lost that race. Defer FIRST — that's the ack — then do the
            # work and follow up. Nothing about the plan itself changed.
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild
            actions = plan_for_guild(
                [r.name for r in guild.roles], [c.name for c in guild.categories],
                [c.name for c in guild.text_channels])
            await interaction.followup.send(
                "```\n" + render_plan(actions).replace("[dim]", "").replace("[/dim]", "")
                + "\n```", ephemeral=True)

        @tree.command(name="scan-server",
                      description="Audit the live server vs the plan — what's missing (owner).")
        async def scan_server(interaction):
            if not await _guard(interaction, "scan_server"):
                return
            from .server_plan import (audit_snapshot, check_plan_evolution,
                                      render_audit, save_snapshot)
            guild = interaction.guild
            snap = save_snapshot(
                data_dir, roles=[r.name for r in guild.roles],
                categories=[c.name for c in guild.categories],
                channels=[c.name for c in guild.text_channels],
                guild_name=guild.name)
            report = render_audit(audit_snapshot(snap))
            note = check_plan_evolution(data_dir)
            if note:
                report += "\n\n" + note
            audit_log(ctx.audit_path, {"op": "scan_server", "applied": True})
            await interaction.response.send_message(
                "```\n" + report[:1800] + "\n```", ephemeral=True)

        @tree.command(name="audit-channels",
                      description="Consolidation view: every channel beyond the blueprint (owner).")
        async def audit_channels(interaction):
            if not await _guard(interaction, "audit_channels"):
                return
            from .server_plan import (audit_snapshot, render_orphans,
                                      save_snapshot)
            guild = interaction.guild
            snap = save_snapshot(
                data_dir, roles=[r.name for r in guild.roles],
                categories=[c.name for c in guild.categories],
                channels=[c.name for c in guild.text_channels],
                guild_name=guild.name)
            report = render_orphans(audit_snapshot(snap))
            audit_log(ctx.audit_path, {"op": "audit_channels", "applied": True})
            await interaction.response.send_message(
                "```\n" + report[:1800] + "\n```", ephemeral=True)

        @tree.command(name="cleanup-orphans",
                      description="Delete the orphan channels /audit-channels listed (owner, typed confirm).")
        @discord.app_commands.describe(
            confirm="Type exactly: DELETE ORPHANS")
        async def cleanup_orphans(interaction, confirm: str):
            if not await _guard(interaction, "cleanup_orphans"):
                return
            from .blueprint import canon_name
            from .server_plan import (CLEANUP_CONFIRM_PHRASE, audit_snapshot,
                                      save_snapshot)
            if confirm.strip() != CLEANUP_CONFIRM_PHRASE:
                await interaction.response.send_message(
                    "⛔ not confirmed — run **/audit-channels** to review the "
                    f"list, then type exactly `{CLEANUP_CONFIRM_PHRASE}` to "
                    "proceed. Deletion is irreversible, so the phrase is the "
                    "gate.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(
                await _do_cleanup_orphans(interaction.guild), ephemeral=True)

        async def _do_cleanup_orphans(guild) -> str:
            from .blueprint import canon_name
            from .server_plan import audit_snapshot, save_snapshot
            snap = save_snapshot(
                data_dir, roles=[r.name for r in guild.roles],
                categories=[c.name for c in guild.categories],
                channels=[c.name for c in guild.text_channels],
                guild_name=guild.name)
            a = audit_snapshot(snap)
            orphan_canon = {canon_name(c) for c in a.extra_channels}
            deleted, failed = [], []
            async with _admin_lock:                # wait our turn; no conflicts
                for ch in list(guild.channels):
                    # channels only — categories handled after, roles NEVER
                    if isinstance(ch, discord.CategoryChannel):
                        continue
                    if canon_name(ch.name) not in orphan_canon:
                        continue
                    try:
                        await ch.delete(
                            reason="Aria consolidation — owner-confirmed "
                                   "orphan cleanup (/cleanup-orphans)")
                        deleted.append(f"#{ch.name}")
                        await asyncio.sleep(_SEND_PACE_S)   # rate-limit-safe
                    except Exception:  # noqa: BLE001 — one fail ≠ abort
                        failed.append(f"#{ch.name}")
                # emptied orphan categories go too (never planned ones)
                extra_cat_canon = {canon_name(c) for c in a.extra_categories}
                for cat in list(guild.categories):
                    if canon_name(cat.name) in extra_cat_canon \
                            and not cat.channels:
                        try:
                            await cat.delete(
                                reason="Aria consolidation — emptied orphan "
                                       "category")
                            deleted.append(f"[cat] {cat.name}")
                            await asyncio.sleep(_SEND_PACE_S)
                        except Exception:  # noqa: BLE001
                            failed.append(f"[cat] {cat.name}")
            audit_log(ctx.audit_path, {
                "op": "cleanup_orphans", "deleted": deleted,
                "failed": failed, "applied": bool(deleted)})
            msg = ["🧹 Consolidation pass done."]
            msg.append(f"  deleted ({len(deleted)}): "
                       + (", ".join(deleted) if deleted else "nothing — "
                          "the server already matches the map ✨"))
            if failed:
                msg.append(f"  ⚠ could not delete: {', '.join(failed)} "
                           "(check my Manage Channels permission)")
            msg.append("  Roles are never touched. Re-check: /audit-channels")
            return "\n".join(msg)[:1900]

        _admin_ops["cleanup"] = _do_cleanup_orphans    # bridge-d: publish

        # clean-start-d (Kevin, 2026-07-27): "a way to clean channels...
        # clear channel [and] clear all channels... repost new pinned
        # messages in them." Deliberately different danger tier from
        # /cleanup-orphans (that deletes whole CHANNELS; this deletes
        # MESSAGE HISTORY within a channel that stays) — its own typed
        # phrases so the two can never be confused for each other.
        _CLEAR_CHANNEL_PHRASE = "CLEAR CHANNEL"
        _CLEAR_ALL_PHRASE = "CLEAR ALL CHANNELS"

        async def _do_clear_channel(channel) -> str:
            """Purge the channel's FULL message history, then repost +
            pin its own guide fresh (reusing channel_guides.py — the
            SAME idempotent content /seed-channels knows) so a cleared
            channel isn't left blank of its own instructions."""
            from .channel_guides import guide_for
            try:
                deleted = await channel.purge(limit=None)
            except Exception as exc:  # noqa: BLE001 — one bad channel ≠ abort
                return f"⚠ {channel.mention}: couldn't clear — {type(exc).__name__}"
            guide = guide_for(channel.name)
            pinned_note = ""
            if guide:
                try:
                    msg = await channel.send(guide)
                    await msg.pin(reason="clean-start: channel guide, freshly reposted")
                    pinned_note = ", guide reposted + pinned"
                except Exception:  # noqa: BLE001
                    pass
            return f"🧹 {channel.mention}: cleared {len(deleted)} message(s){pinned_note}"

        @tree.command(name="clear-channel",
                      description="🧹 Clear every message in THIS channel, "
                                  "then repost its guide (owner, typed confirm).")
        @discord.app_commands.describe(confirm=f"Type exactly: {_CLEAR_CHANNEL_PHRASE}")
        async def clear_channel_cmd(interaction, confirm: str):
            if not await _guard(interaction, "clear_channel"):
                return
            if confirm.strip() != _CLEAR_CHANNEL_PHRASE:
                await interaction.response.send_message(
                    f"⛔ not confirmed — type exactly `{_CLEAR_CHANNEL_PHRASE}` "
                    "to permanently delete every message in this channel. "
                    "This can't be undone.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            async with _admin_lock:
                result = await _do_clear_channel(interaction.channel)
            audit_log(ctx.audit_path, {"op": "clear_channel",
                                       "channel": str(interaction.channel.id),
                                       "applied": True})
            await interaction.followup.send(result, ephemeral=True)

        @tree.command(name="clear-all-channels",
                      # 100 chars is Discord's hard limit; this was 108 and
                      # silently failed EVERY tree sync (error 50035), so no
                      # new command registered for as long as it existed.
                      description="🧹 Wipe every public channel + repost "
                                  "guides (owner, typed confirm).")
        @discord.app_commands.describe(confirm=f"Type exactly: {_CLEAR_ALL_PHRASE}")
        async def clear_all_channels_cmd(interaction, confirm: str):
            if not await _guard(interaction, "clear_all_channels"):
                return
            if confirm.strip() != _CLEAR_ALL_PHRASE:
                await interaction.response.send_message(
                    "⛔ not confirmed — this wipes EVERY public channel's "
                    "message history server-wide (ADMIN/BACKEND excluded, "
                    "your team's tasks/planning/audit trail is safe). "
                    f"Irreversible. Type exactly `{_CLEAR_ALL_PHRASE}` to "
                    "proceed.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild
            if guild is None:
                await interaction.followup.send(
                    "that only works inside the server!", ephemeral=True)
                return
            from .blueprint import canon_name
            excluded = {"admin", "backend"}
            results = []
            async with _admin_lock:
                for channel in list(guild.text_channels):
                    cat = channel.category
                    if cat is not None and canon_name(cat.name) in excluded:
                        continue
                    results.append(await _do_clear_channel(channel))
                    await asyncio.sleep(_SEND_PACE_S)
            audit_log(ctx.audit_path, {"op": "clear_all_channels",
                                       "channels": len(results), "applied": True})
            from .discord_limits import split_text
            summary = f"🧹 Cleared {len(results)} channel(s):\n" + "\n".join(results)
            for part in split_text(summary, 1900)[:5]:
                await interaction.followup.send(part, ephemeral=True)

        # setup-all-d (Kevin, 2026-07-18): each setup phase lives in a
        # helper so /setup-all can run the whole suite; every helper takes
        # its own turn on _admin_lock (never nested — the lock isn't
        # reentrant), so serialization holds however phases are combined.
        async def _do_setup_shop(interaction) -> str:
            guild = interaction.guild
            actions = plan_for_guild(
                [r.name for r in guild.roles], [c.name for c in guild.categories],
                [c.name for c in guild.text_channels])
            async with _admin_lock:                # wait our turn; no conflicts
                summary = await _apply(guild, actions, interaction)
            try:  # refresh the plan snapshot so the audit is instantly current
                from .server_plan import save_snapshot
                save_snapshot(data_dir, roles=[r.name for r in guild.roles],
                              categories=[c.name for c in guild.categories],
                              channels=[c.name for c in guild.text_channels],
                              guild_name=guild.name)
            except Exception:  # noqa: BLE001
                pass
            return summary

        _admin_ops["setup"] = _do_setup_shop           # bridge-d: publish

        @tree.command(name="setup-shop", description="Build/repair the whole server (owner).")
        async def setup_shop(interaction):
            if not await _guard(interaction, "setup_shop"):
                return
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(await _do_setup_shop(interaction),
                                            ephemeral=True)

        async def _do_setup_webhooks(interaction) -> str:
            from .blueprint import canon_name
            from .webhook_provision import (provision_plan, render_results,
                                            store_webhook_url)
            guild = interaction.guild
            me = guild.me
            if not getattr(me.guild_permissions, "manage_webhooks", False):
                return ("⛔ I need the **Manage Webhooks** permission for "
                        "this — Server Settings → Roles → my role → Manage "
                        "Webhooks ON, then run me again.")
            from sovereign_agent.credentials import read_env
            needed = provision_plan(read_env())
            chan_by_canon = {canon_name(c.name): c for c in guild.text_channels}
            results = []
            async with _admin_lock:                # wait our turn; no conflicts
                for spec in needed:
                    channel = chan_by_canon.get(canon_name(spec.channel))
                    if channel is None:
                        results.append((spec.channel, spec.env_name,
                                        "no-channel", ""))
                        continue
                    try:
                        hook = None
                        for existing in await channel.webhooks():
                            if (existing.name == spec.display_name
                                    and existing.url):
                                hook = existing        # reuse — no duplicates
                                break
                        outcome = "reused"
                        if hook is None:
                            hook = await channel.create_webhook(
                                name=spec.display_name,
                                reason="Aria shop setup — vaulted, never shown")
                            outcome = "created"
                            await asyncio.sleep(_SEND_PACE_S)   # rate-limit-safe
                        masked = store_webhook_url(spec.env_name, hook.url)
                        results.append((spec.channel, spec.env_name, outcome,
                                        masked))
                        audit_log(ctx.audit_path, {  # NEVER the URL — masked
                            "op": "setup_webhook", "channel": spec.channel,
                            "env": spec.env_name, "outcome": outcome,
                            "masked": masked, "applied": True})
                    except Exception as exc:  # noqa: BLE001 — one fail ≠ abort
                        results.append((spec.channel, spec.env_name,
                                        "failed", ""))
                        audit_log(ctx.audit_path, {
                            "op": "setup_webhook", "channel": spec.channel,
                            "error": f"{type(exc).__name__}"})
                # rehome-d (Kevin, 2026-07-18): a vaulted webhook whose
                # channel MOVED in the blueprint (e.g. GPUs → #desktop-parts)
                # would silently keep posting to the old room. Verify each
                # vaulted spec still lives on its blueprint channel; re-mint
                # + re-vault when it moved or died. Can't-verify → left alone.
                from .webhook_provision import WEBHOOK_SPECS
                stored_now = read_env()
                needed_envs = {s.env_name for s in needed}
                for spec in WEBHOOK_SPECS:
                    if spec.env_name in needed_envs:
                        continue                      # just handled above
                    url = (stored_now.get(spec.env_name) or "").strip()
                    target = chan_by_canon.get(canon_name(spec.channel))
                    if not url or target is None:
                        continue
                    moved = False
                    try:
                        hook = await discord.Webhook.from_url(
                            url, client=interaction.client).fetch()
                        moved = hook.channel_id != target.id
                    except discord.NotFound:
                        moved = True                  # deleted — re-mint
                    except Exception:  # noqa: BLE001 — unverifiable → keep
                        moved = False
                    if not moved:
                        continue
                    try:
                        hook = await target.create_webhook(
                            name=spec.display_name,
                            reason="Aria shop setup — webhook re-homed")
                        await asyncio.sleep(_SEND_PACE_S)   # rate-limit-safe
                        masked = store_webhook_url(spec.env_name, hook.url)
                        results.append((spec.channel, spec.env_name,
                                        "rehomed", masked))
                        audit_log(ctx.audit_path, {
                            "op": "setup_webhook", "channel": spec.channel,
                            "env": spec.env_name, "outcome": "rehomed",
                            "masked": masked, "applied": True})
                    except Exception as exc:  # noqa: BLE001
                        results.append((spec.channel, spec.env_name,
                                        "failed", ""))
                        audit_log(ctx.audit_path, {
                            "op": "setup_webhook", "channel": spec.channel,
                            "error": f"{type(exc).__name__}"})
            return render_results(results)[:1900]

        _admin_ops["webhooks"] = _do_setup_webhooks    # bridge-d: publish

        @tree.command(name="setup-webhooks",
                      description="Create the shop webhooks + vault the URLs (owner).")
        async def setup_webhooks(interaction):
            if not await _guard(interaction, "setup_webhooks"):
                return
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(
                await _do_setup_webhooks(interaction), ephemeral=True)

        @tree.command(name="create-channel", description="Create a channel in a category (owner).")
        async def create_channel(interaction, name: str, category: str = ""):
            if not await _guard(interaction, "create_channel"):
                return
            from .blueprint import canon_name
            guild = interaction.guild
            parent = next((c for c in guild.categories
                           if canon_name(c.name) == canon_name(category)), None)
            await guild.create_text_channel(name, category=parent)
            audit_log(ctx.audit_path, {"op": "create_channel", "name": name, "applied": True})
            await interaction.response.send_message(f"＋ #{name}", ephemeral=True)

        @tree.command(name="create-role", description="Create a role with a color (owner).")
        async def create_role(interaction, name: str, color: str = "default"):
            if not await _guard(interaction, "create_role"):
                return
            from .blueprint import RoleSpec
            r = RoleSpec(name, color)
            await interaction.guild.create_role(
                name=name, colour=discord.Colour(r.color_int))
            audit_log(ctx.audit_path, {"op": "create_role", "name": name, "applied": True})
            await interaction.response.send_message(f"＋ @{name}", ephemeral=True)

        @tree.command(name="whoami", description="Are you recognized as the owner?")
        async def whoami(interaction):
            _remember(interaction.user)
            from sovereign_agent import members
            rec = members.load_member(data_dir, str(interaction.user.id))
            role = rec.get("role", "member") if rec else "member"
            if role == members.ROLE_OWNER:
                msg = "👑 You're Kevin — the owner. She always knows you."
            elif role == members.ROLE_EMPLOYEE:
                msg = ("🛠 You're on the team (employee). She's got you: "
                       f"{rec.get('note', '')}")
            else:
                seen = len(rec.get("names", [])) if rec else 0
                msg = (f"🙂 She knows you by your ID (role: {role}"
                       + (f", {seen} name(s) on file" if seen > 1 else "")
                       + "). Admin commands are owner-only.")
            await interaction.response.send_message(msg, ephemeral=True)

        @tree.command(name="help",
                      description="📖 Commands anyone can use — new here? Start here.")
        async def help_(interaction):
            # help-boards-d (Kevin, 2026-07-27): "a help command for...
            # new members" — the "everyone" tier of the ONE audited
            # COMMANDS list, sectioned. `/menu` layers subscriber extras
            # on top of this same tier; `/admin-panel`/`/admin` are the
            # team/owner boards.
            _remember(interaction.user)
            emb = build_commands_embed(
                "📖 Commands you can use", 0x3fd0c9, "everyone",
                intro="New here? Everything below works right now — no "
                     "subscription needed. `/menu` shows a bit more if "
                     "you're already a subscriber.")
            emb.set_footer(text="Ephemeral — only you see this. 💛")
            await interaction.response.send_message(embed=emb, ephemeral=True)

        # admin-panel-d (Kevin, 2026-07-27): "create a admin menu
        # specifically for him [Theodore]... an admin only community
        # control module... something to make his controls and learning
        # path quick and easy." Team-gated (owner OR employee — Theodore
        # is already bound to ROLE_EMPLOYEE in members.py's TEAM_NOTES),
        # reusing members.is_team() rather than inventing a new gate.
        def _admin_panel_embed():
            # help-boards-d (Kevin, 2026-07-27): "a help command for
            # admins... kind of like the admin panel but fully updated."
            # The cockpit-bridge + bot/sources sections below aren't
            # Discord slash commands at all (they're `/server <cmd>`
            # bridge ops + cockpit buttons) so they stay hand-written;
            # everything that IS a real slash command comes from the
            # one audited COMMANDS list — no more separate, silently
            # drifting copy of "what can team do" (18 real commands had
            # quietly gone missing from this exact panel before today).
            emb = discord.Embed(
                title="🛠 Team Control Panel", color=0x3FD0C9,
                description="You're recognized as team — here's the "
                           "quick reference for everything you can do.")
            emb.add_field(name="🌉 Server bridge (from the cockpit's "
                              "/server command, or here)", inline=False, value=(
                "`/server setup-all` — full server build (structure + "
                "webhooks + guides)\n"
                "`/server audit` — what's missing vs the plan\n"
                "`/server webhooks` — mint/rehome webhooks\n"
                "`/server scan` — plan coverage check\n"
                "`/server cleanup DELETE ORPHANS` — remove listed orphan "
                "channels (typed confirm required)"))
            emb.add_field(name="🤖 Bot + sources control (cockpit)", inline=False, value=(
                "❖ discord button — turn the bot off / pause / resume / "
                "restart\n"
                "# sources button — turn any tracker source on/off (e.g. "
                "\"reddit off\", one project or the whole fleet at once)\n"
                "$ stripe button — see/update every product's Stripe "
                "Payment Link"))
            for field in build_commands_embed("", 0x3FD0C9, "team").fields:
                emb.add_field(name=field.name, value=field.value, inline=field.inline)
            emb.set_footer(text="This panel: /admin-panel · /theorules — "
                                "same thing, pick whichever you remember 💛")
            return emb

        @tree.command(name="admin-panel",
                      description="🛠 Team control panel — bridge "
                                  "commands, bot + sources control, "
                                  "grants (owner + staff).")
        async def admin_panel_cmd(interaction):
            _remember(interaction.user)
            from sovereign_agent import members as _mem
            if not _mem.is_team(data_dir, str(interaction.user.id)):
                await interaction.response.send_message(
                    "That's a team-only panel.", ephemeral=True)
                return
            await interaction.response.send_message(
                embed=_admin_panel_embed(), ephemeral=True)

        @tree.command(name="theorules",
                      description="🛠 Theodore's own shortcut to the team "
                                  "control panel — same as /admin-panel.")
        async def theorules_cmd(interaction):
            _remember(interaction.user)
            from sovereign_agent import members as _mem
            if not _mem.is_team(data_dir, str(interaction.user.id)):
                await interaction.response.send_message(
                    "That's a team-only panel.", ephemeral=True)
                return
            await interaction.response.send_message(
                embed=_admin_panel_embed(), ephemeral=True)

        @tree.command(name="mead-recipe",
                      description="🍯 Get a mead recipe (21+). Blank = list "
                                  "styles.")
        async def mead_recipe(interaction, style: str = ""):
            from sovereign_agent.mead_recipes import render_recipe
            from sovereign_agent.discord_limits import split_text
            _remember(interaction.user)
            await interaction.response.defer(ephemeral=True)
            for part in split_text(render_recipe(style), 1900)[:2]:
                await interaction.followup.send(part, ephemeral=True)

        @tree.command(name="mead-suggest",
                      description="🍯 Personalized mead suggestions (21+). "
                                  "Optional: describe what you're after.")
        async def mead_suggest(interaction, idea: str = ""):
            from sovereign_agent.mead_profiles import render_suggestions
            from sovereign_agent.discord_limits import split_text
            _remember(interaction.user)
            await interaction.response.defer(ephemeral=True)
            text = render_suggestions(data_dir, str(interaction.user.id),
                                      idea=idea)
            for part in split_text(text, 1900)[:2]:
                await interaction.followup.send(part, ephemeral=True)

        @tree.command(name="mead-taste",
                      description="🍯 Set your flavor palate (comma list of "
                                  "flavors you like).")
        async def mead_taste(interaction, likes: str = "", dislikes: str = ""):
            from sovereign_agent.mead_profiles import compose_palate, set_taste
            from sovereign_agent.mead_recipes import FLAVORS
            _remember(interaction.user)
            if not likes and not dislikes:
                await interaction.response.send_message(
                    "🍯 Tell me your palate! e.g. `/mead-taste likes: sweet, "
                    "fruity, spiced`. Flavors: " + ", ".join(FLAVORS),
                    ephemeral=True)
                return
            set_taste(data_dir, str(interaction.user.id),
                      likes=[x.strip() for x in likes.split(",")] if likes else None,
                      dislikes=[x.strip() for x in dislikes.split(",")] if dislikes else None)
            await interaction.response.send_message(
                compose_palate(data_dir, str(interaction.user.id))
                + "\n\nNow try /mead-suggest 🍯", ephemeral=True)

        @tree.command(name="mead-rate",
                      description="🍯 Rate a mead recipe 1-5 — sharpens your "
                                  "profile.")
        async def mead_rate(interaction, style: str, stars: int):
            from sovereign_agent.mead_profiles import compose_palate, rate_recipe
            from sovereign_agent.mead_recipes import get_recipe
            _remember(interaction.user)
            if get_recipe(style) is None:
                await interaction.response.send_message(
                    "🍯 I don't know that one — see styles with /mead-recipe.",
                    ephemeral=True)
                return
            rate_recipe(data_dir, str(interaction.user.id), style, stars)
            await interaction.response.send_message(
                f"🍯 Noted — {max(1, min(stars, 5))}★. That sharpens my "
                "picks for you.\n\n"
                + compose_palate(data_dir, str(interaction.user.id)),
                ephemeral=True)

        class MeadGate(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=180)

            @discord.ui.button(label="🍯 I'm 21+ — let me in",
                               custom_id="mead:confirm",
                               style=discord.ButtonStyle.success)
            async def confirm(self, interaction, button):  # noqa: ANN001
                try:
                    guild = interaction.guild
                    role = next((r for r in guild.roles
                                 if r.name == "Mead-Head"), None)
                    if role is None:
                        role = await guild.create_role(
                            name="Mead-Head", colour=discord.Colour(0xE67E22),
                            reason="mead-d: self-attest 21+ role")
                    await interaction.user.add_roles(
                        role, reason="mead-d: attested 21+")
                    audit_log(ctx.audit_path, {"op": "mead_access",
                                               "user": str(interaction.user.id),
                                               "applied": True})
                    await interaction.response.send_message(
                        "🍯 Welcome to the Mead Lounge! Cheers — brew "
                        "responsibly. Try /mead-recipe jaom to start. 💛",
                        ephemeral=True)
                except Exception:  # noqa: BLE001
                    await interaction.response.send_message(
                        "🍯 Couldn't grant the role — tell BigKev.",
                        ephemeral=True)

        @tree.command(name="mead-access",
                      description="🍯 Enter the 21+ Mead Lounge (self-attest).")
        async def mead_access(interaction):
            _remember(interaction.user)
            await interaction.response.send_message(
                "🍯 **The Mead Lounge is 21+.** By entering you confirm "
                "you're 21 or older. The channels are also Discord "
                "age-restricted (18+). Click below to join the mead-heads:",
                view=MeadGate(), ephemeral=True)

        @tree.command(name="tip",
                      description="💛 Tip the shop — support the 24/7 bots "
                                  "(optional, appreciated).")
        async def tip(interaction):
            from sovereign_agent.tips import tip_buttons, tip_embed
            _remember(interaction.user)
            btns = tip_buttons(data_dir)
            view = discord.ui.View(timeout=None)
            for i, b in enumerate(btns[:25]):
                view.add_item(discord.ui.Button(
                    label=b["label"], url=b["url"],
                    style=discord.ButtonStyle.link, row=i // 5))
            await interaction.response.send_message(
                embed=discord.Embed.from_dict(tip_embed(data_dir)),
                view=view, ephemeral=True)

        @tree.command(name="refer",
                      description="🤝 Your referral code — grow the circle, "
                                  "earn credits together.")
        @discord.app_commands.describe(
            use="(optional) redeem a friend's code, e.g. REF-ABC1234")
        async def refer(interaction, use: str = ""):
            _remember(interaction.user)
            from sovereign_agent import referrals
            uid = str(interaction.user.id)
            if use.strip():
                out = referrals.redeem(data_dir, uid, use)
                msgs = {
                    "ok": "🎉 Code redeemed! You **both** just earned "
                          f"{referrals.CREDIT_PER_REFERRAL} ✨ credits. "
                          "Welcome to the circle. 💛",
                    "already-referred": "You've already used a referral code "
                                        "— one per member. 💛",
                    "self-referral": "Ha! You can't refer yourself 😄 — share "
                                     "your code with friends instead.",
                    "unknown-code": "Hmm, I don't recognize that code. Double-"
                                    "check it with your friend?",
                    "held-for-review": "Thanks for sharing that code! 💛 "
                                       "This one's being held for a quick "
                                       "review before credits land — "
                                       "nothing's lost, just a beat of "
                                       "patience."}
                await interaction.response.send_message(
                    msgs.get(out["reason"], "Couldn't redeem that one."),
                    ephemeral=True)
                return
            await interaction.response.send_message(
                referrals.compose_refer(data_dir, uid), ephemeral=True)

        @tree.command(name="earnings",
                      description="📊 Your rank, credits + earnings — private "
                                  "to you.")
        async def earnings(interaction):
            _remember(interaction.user)
            from sovereign_agent import referrals
            await interaction.response.send_message(
                referrals.compose_earnings(data_dir, str(interaction.user.id)),
                ephemeral=True)

        @tree.command(name="leaderboard",
                      description="🏆 Community champions — top circle-growers.")
        async def leaderboard(interaction):
            _remember(interaction.user)
            from sovereign_agent import referrals
            await interaction.response.send_message(
                referrals.compose_leaderboard(data_dir), ephemeral=True)

        @tree.command(name="marketer",
                      description="🤝 Toggle a member's marketer status "
                                  "(owner) — unlocks 25% referral commissions.")
        @discord.app_commands.describe(user="who",
                                       on="true to enable, false to disable")
        async def marketer_cmd(interaction, user: discord.Member, on: bool = True):
            from sovereign_agent import members as _mem
            if not _mem.is_owner(data_dir, str(interaction.user.id)):
                await interaction.response.send_message(
                    "That's an owner command.", ephemeral=True)
                return
            from sovereign_agent import referrals
            rec = referrals.set_marketer(data_dir, str(user.id), on=on)
            state = "ON 🤝" if rec["role"] == referrals.ROLE_MARKETER else "OFF"
            await interaction.response.send_message(
                f"marketer status for {user.mention}: **{state}**",
                ephemeral=True)

        @tree.command(name="tracker",
                      description="🔌 Turn one tracker vertical on or off "
                                  "(owner) — pauses/resumes its Discord posts.")
        @discord.app_commands.describe(slug="the vertical's slug, e.g. lego, sneakers, gpus",
                                       on="true to enable, false to pause")
        async def tracker_cmd(interaction, slug: str, on: bool = True):
            from sovereign_agent import members as _mem
            if not _mem.is_owner(data_dir, str(interaction.user.id)):
                await interaction.response.send_message(
                    "That's an owner command.", ephemeral=True)
                return
            from sovereign_agent import verticals
            ok, msg = verticals.set_tracker_enabled(data_dir, slug, on)
            await interaction.response.send_message(msg, ephemeral=True)

        @tree.command(name="subscribe",
                      description="🔔 Subscribe to a tracker channel — it "
                                  "becomes visible + you get pinged on drops.")
        @discord.app_commands.describe(vertical="the tracker's slug, e.g. lego, sneakers, gpus")
        async def subscribe_cmd(interaction, vertical: str):
            _remember(interaction.user)
            from sovereign_agent.verticals import get_vertical
            v = get_vertical(vertical)
            guild = interaction.guild
            if v is None:
                await interaction.response.send_message(
                    f"no tracker named {vertical!r} — try /scout to browse.",
                    ephemeral=True)
                return
            if guild is None:
                await interaction.response.send_message(
                    "subscribe from inside the server, not DMs!", ephemeral=True)
                return
            role = await _vertical_role(guild, v)
            member = interaction.user
            if role in getattr(member, "roles", []):
                await interaction.response.send_message(
                    f"already subscribed to {v.emoji} {v.name} — "
                    f"#{v.track_channel} 💛", ephemeral=True)
                return
            await member.add_roles(role, reason="tracker subscribe")
            await interaction.response.send_message(
                f"🔔 subscribed to {v.emoji} {v.name} — #{v.track_channel} is "
                "now visible + you'll be pinged on hot finds.", ephemeral=True)

        @tree.command(name="unsubscribe",
                      description="🔕 Unsubscribe from a tracker channel — it "
                                  "disappears + pings stop.")
        @discord.app_commands.describe(vertical="the tracker's slug, e.g. lego, sneakers, gpus")
        async def unsubscribe_cmd(interaction, vertical: str):
            _remember(interaction.user)
            from sovereign_agent.verticals import get_vertical
            v = get_vertical(vertical)
            guild = interaction.guild
            if v is None:
                await interaction.response.send_message(
                    f"no tracker named {vertical!r}.", ephemeral=True)
                return
            if guild is None:
                await interaction.response.send_message(
                    "that only works inside the server!", ephemeral=True)
                return
            role = next((r for r in guild.roles if r.name == v.ping_role), None)
            member = interaction.user
            if role is None or role not in getattr(member, "roles", []):
                await interaction.response.send_message(
                    f"you're not subscribed to {v.emoji} {v.name}.", ephemeral=True)
                return
            await member.remove_roles(role, reason="tracker unsubscribe")
            await interaction.response.send_message(
                f"🔕 unsubscribed from {v.emoji} {v.name} — "
                f"#{v.track_channel} is hidden again.", ephemeral=True)

        @tree.command(name="reaction-role-add", description="🎭 Bind an emoji on a message to a role.")
        @discord.app_commands.describe(message_id="the message id to watch", channel="the channel the message is in",
                                        emoji="the emoji to react with", role="the role to grant")
        async def reaction_role_add_cmd(interaction, message_id: str, channel: discord.TextChannel,
                                         emoji: str, role: discord.Role):
            _remember(interaction.user)
            if not _is_staff(interaction):
                await interaction.response.send_message("team only.", ephemeral=True)
                return
            from sovereign_agent import reaction_roles as _rr
            try:
                message = await channel.fetch_message(int(message_id))
            except Exception:  # noqa: BLE001
                await interaction.response.send_message(
                    f"couldn't find message {message_id} in {channel.mention}.", ephemeral=True)
                return
            try:
                await message.add_reaction(emoji)
            except Exception:  # noqa: BLE001
                pass
            key = _rr.emoji_key(getattr(emoji, "id", None), str(emoji))
            entry = _rr.add_binding(
                data_dir, str(interaction.guild.id), message_id=str(message.id),
                channel_id=str(channel.id), emoji_key=key, emoji_display=str(emoji),
                role_id=str(role.id), created_by=str(interaction.user.id))
            audit_log(ctx.audit_path, {"op": "reaction_role_bind", "action": "add",
                                       "guild_id": str(interaction.guild.id),
                                       "binding_id": entry["binding_id"]})
            await interaction.response.send_message(
                f"🎭 bound {emoji} on that message → {role.mention}.", ephemeral=True)

        @tree.command(name="reaction-role-remove", description="🎭 Remove a reaction-role binding.")
        @discord.app_commands.describe(message_id="the message id", emoji="the bound emoji")
        async def reaction_role_remove_cmd(interaction, message_id: str, emoji: str):
            _remember(interaction.user)
            if not _is_staff(interaction):
                await interaction.response.send_message("team only.", ephemeral=True)
                return
            from sovereign_agent import reaction_roles as _rr
            guild_id = str(interaction.guild.id)
            key = _rr.emoji_key(getattr(emoji, "id", None), str(emoji))
            binding = _rr.find_binding(data_dir, guild_id, message_id, key)
            if binding is None:
                await interaction.response.send_message("no matching binding found.", ephemeral=True)
                return
            _rr.remove_binding(data_dir, guild_id, binding["binding_id"])
            audit_log(ctx.audit_path, {"op": "reaction_role_bind", "action": "remove",
                                       "guild_id": guild_id, "binding_id": binding["binding_id"]})
            await interaction.response.send_message("🎭 binding removed.", ephemeral=True)

        @tree.command(name="reaction-role-list", description="🎭 List reaction-role bindings.")
        async def reaction_role_list_cmd(interaction):
            _remember(interaction.user)
            if not _is_staff(interaction):
                await interaction.response.send_message("team only.", ephemeral=True)
                return
            from sovereign_agent import reaction_roles as _rr
            bindings = _rr.list_bindings(data_dir, str(interaction.guild.id))
            if not bindings:
                await interaction.response.send_message("no reaction-role bindings yet.", ephemeral=True)
                return
            lines = [f"• msg {b['message_id']} — {b['emoji_display']} → role {b['role_id']}"
                     for b in bindings[:25]]
            await interaction.response.send_message("🎭 bindings:\n" + "\n".join(lines), ephemeral=True)

        @tree.command(name="reaction-role-panel",
                      description="🎭 Post a reaction-role panel with up to 5 options in one shot.")
        @discord.app_commands.describe(
            title="panel title", emoji1="first emoji", role1="role for the first emoji",
            description="panel description (optional)",
            emoji2="second emoji (optional)", role2="role for the second emoji (optional)",
            emoji3="third emoji (optional)", role3="role for the third emoji (optional)",
            emoji4="fourth emoji (optional)", role4="role for the fourth emoji (optional)",
            emoji5="fifth emoji (optional)", role5="role for the fifth emoji (optional)",
        )
        async def reaction_role_panel_cmd(
            interaction, title: str, emoji1: str, role1: discord.Role,
            description: str = "",
            emoji2: str = "", role2: discord.Role = None,
            emoji3: str = "", role3: discord.Role = None,
            emoji4: str = "", role4: discord.Role = None,
            emoji5: str = "", role5: discord.Role = None,
        ):
            _remember(interaction.user)
            if not _is_staff(interaction):
                await interaction.response.send_message("team only.", ephemeral=True)
                return
            from sovereign_agent import reaction_roles as _rr
            pairs = [(emoji1, role1)]
            for e, r in ((emoji2, role2), (emoji3, role3), (emoji4, role4), (emoji5, role5)):
                if e and r is not None:
                    pairs.append((e, r))
            keys = [_rr.emoji_key(getattr(e, "id", None), str(e)) for e, _r in pairs]
            try:
                _rr.validate_panel_options(keys)
            except ValueError as exc:
                await interaction.response.send_message(f"refusing to post: {exc}", ephemeral=True)
                return
            lines = [f"{e} \u2014 {r.mention}" for e, r in pairs]
            emb = discord.Embed(
                title=title,
                description=(description or "React below to get a role.") + "\n\n" + "\n".join(lines),
                color=0x5865F2)
            message = await interaction.channel.send(embed=emb)
            for e, _r in pairs:
                try:
                    await message.add_reaction(e)
                except Exception:  # noqa: BLE001
                    pass
            for (e, r), key in zip(pairs, keys):
                _rr.add_binding(
                    data_dir, str(interaction.guild.id), message_id=str(message.id),
                    channel_id=str(interaction.channel.id), emoji_key=key, emoji_display=str(e),
                    role_id=str(r.id), created_by=str(interaction.user.id))
            audit_log(ctx.audit_path, {"op": "reaction_role_panel", "action": "create",
                                       "guild_id": str(interaction.guild.id),
                                       "message_id": str(message.id), "options": len(pairs)})
            await interaction.response.send_message(
                f"panel posted with {len(pairs)} option(s).", ephemeral=True)

        @tree.command(name="my-panel",
                      description="& Your subscribe panel — category "
                                  "buttons + per-channel fine-tuning, "
                                  "mobile-friendly.")
        async def my_panel_cmd(interaction):
            _remember(interaction.user)
            # trial-d (Kevin, 2026-08-03): "everyone can get 1 week of free
            # bots then they have to pay." Granted on first /my-panel — the
            # moment someone actually picks what they want to be told about,
            # which is a far better signal of intent than joining.
            #
            # Once per member, ever. `entitlements.status()` is the record,
            # so a re-join or a second /my-panel can't re-trigger it, and an
            # existing PAID plan is never overwritten by a free trial.
            # stuck-panel-d (Kevin, 2026-08-04): "it says sending command, but
            # it appears stuck loading." The role grant below is TWO Discord
            # round-trips (create_role if missing, then add_roles), and it sat
            # in front of the response — so /my-panel blew Discord's 3-second
            # ack deadline and the interaction died. Exactly the /plan-shop
            # bug from yesterday, reintroduced here.
            #
            # Deferring isn't an option: the no-area branch below sends a
            # MODAL, which has to be the initial response. So the local
            # entitlement write (fast, a file) stays inline and the slow
            # Discord call is fired as a background task — the same
            # fire-and-forget shape used elsewhere in this file. The member
            # gets their role a moment later; the panel opens immediately.
            try:
                import asyncio as _aio

                from sovereign_agent import entitlements as _ent
                st = _ent.status(data_dir, str(interaction.user.id))
                if not st.get("plan"):
                    _ent.grant(data_dir, str(interaction.user.id), "trial",
                               7.0, source="trial")
                    _aio.create_task(_grant_role(
                        interaction.guild, interaction.user,
                        "Subscriber-Basic"))
            except Exception:  # noqa: BLE001 — the panel must open regardless
                pass
            from sovereign_agent.scout import load_area
            uid = str(interaction.user.id)
            area = load_area(data_dir, uid)
            if not area or not area.get("radius_mi"):
                await interaction.response.send_modal(_area_modal_for(uid))
                return
            member_roles = {r.name for r in getattr(interaction.user, "roles", []) or []}
            await interaction.response.send_message(
                MY_PANEL_INTRO, view=build_my_panel_view(member_roles), ephemeral=True)

        @tree.command(name="local",
                      description="📍 Pull a report of finds near your "
                                  "saved area, right now (private to you).")
        async def local_cmd(interaction):
            """location-filter-d (Kevin, 2026-07-27): "so I can enter a
            channel and request reports" — runnable in ANY channel,
            always ephemeral. Same area-gate as /my-panel: no saved area
            yet → the required-area modal, not a silent empty report."""
            _remember(interaction.user)
            uid = str(interaction.user.id)
            from sovereign_agent.scout import load_area
            area = load_area(data_dir, uid)
            if not area or not area.get("radius_mi"):
                await interaction.response.send_modal(_area_modal_for(uid))
                return
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(
                await _near_me_report(uid), ephemeral=True)

        class WfLookupModal(discord.ui.Modal, title="🔍 Warframe Market Lookup"):
            """middleman-lookup-d (Kevin, 2026-07-27): "type in items I
            want to sell... find all active buyers and list them from
            highest profit to lowest. Like a middle man loop up
            wizard." — the "type" half; `_wf_lookup_search` handles the
            "or select from a dropdown" half when more than one item
            matches."""
            item_query = discord.ui.TextInput(
                label="Item name", placeholder="e.g. Frost Prime Set, Arcane Energize",
                required=True, max_length=80)

            async def on_submit(self, interaction):  # noqa: ANN001
                await interaction.response.defer(ephemeral=True)
                await _wf_lookup_search(interaction, str(self.item_query.value))

        async def _wf_lookup_cache():
            from sovereign_agent.discord_runtime.fetchers import (
                _wf_refresh_pools, _wf_load_cache, _wf_save_cache)
            cache = await asyncio.to_thread(_wf_load_cache, data_dir)
            if cache.get("all_items"):
                return cache
            # first-ever lookup (or an old cache from before this
            # feature existed) — refresh now rather than tell the
            # member to come back later
            fresh = await asyncio.to_thread(_wf_refresh_pools, None)
            fresh["fetched_at"] = time.time()
            fresh["cursors"] = cache.get("cursors", {})
            await asyncio.to_thread(_wf_save_cache, data_dir, fresh)
            return fresh

        async def _wf_lookup_embeds(slug: str, name: str):
            from sovereign_agent.discord_runtime.fetchers import (
                WarframeFlipFetcher, wf_lookup_item)
            hits = await asyncio.to_thread(wf_lookup_item, None, slug, name)
            if not hits:
                return f"🔍 **{name}** — no live sell orders right now.", []
            item_url = f"https://warframe.market/items/{slug}"
            embeds = [discord.Embed.from_dict(WarframeFlipFetcher._build_embed(h, item_url))
                     for h in hits[:10]]
            plural = "s" if len(hits) != 1 else ""
            content = f"🔍 **{name}** — {len(hits)} result{plural}"
            return content, embeds

        async def _wf_lookup_search(interaction, query: str):
            from sovereign_agent.discord_runtime.fetchers import wf_item_search
            try:
                cache = await _wf_lookup_cache()
            except Exception:  # noqa: BLE001 — warframe.market down ≠ crash
                await interaction.followup.send(
                    "🔍 couldn't reach warframe.market right now — try again "
                    "in a bit.", ephemeral=True)
                return
            hits = await asyncio.to_thread(wf_item_search, cache, query)
            if not hits:
                await interaction.followup.send(
                    f"🔍 no item found matching **{query}** — try a shorter "
                    "or simpler name.", ephemeral=True)
                return
            if len(hits) == 1:
                content, embeds = await _wf_lookup_embeds(
                    hits[0]["slug"], hits[0]["name"])
                await interaction.followup.send(content, embeds=embeds, ephemeral=True)
                return
            view = discord.ui.View(timeout=180)
            opts = [discord.SelectOption(label=h["name"][:100], value=h["slug"])
                   for h in hits[:25]]
            view.add_item(discord.ui.Select(
                placeholder="pick the exact item…", options=opts,
                custom_id="wflookup:pick"))
            await interaction.followup.send(
                f"🔍 {len(hits)} items match **{query}** — pick one:",
                view=view, ephemeral=True)

        @tree.command(name="wf-lookup",
                      description="🔍 Warframe Market — look up an item's "
                                  "real buyers, ranked by profit.")
        async def wf_lookup_cmd(interaction):
            _remember(interaction.user)
            await interaction.response.send_modal(WfLookupModal())

        def _vault_overview_embeds(vault: dict):
            """vaulted-relics-d (Kevin, 2026-07-27): "shows all of the
            active warframe vaulted relics/warframes." Default (no name
            given) view — just the real vaulted Warframe names, sorted;
            the part→relic breakdown is one more command call away
            (`warframe:` arg) rather than crammed into one wall."""
            names = sorted(vault.keys())
            emb = discord.Embed(
                title="🔒 Prime Vault — currently vaulted Warframes",
                description=f"{len(names)} Warframe{'s' if len(names) != 1 else ''} "
                            "have at least one vaulted relic right now.\n"
                            "Run `/vaulted-relics warframe:<name>` for the "
                            "part → relic breakdown.",
                color=0x6A5ACD)
            chunk = ""
            for n in names:
                line = f"• {n}\n"
                if len(chunk) + len(line) > 1000:
                    emb.add_field(name="​", value=chunk, inline=True)
                    chunk = ""
                chunk += line
            if chunk:
                emb.add_field(name="​", value=chunk, inline=True)
            return f"🔒 {len(names)} vaulted Warframes", [emb]

        def _vault_detail_embeds(name: str, parts: dict):
            """Per-Warframe breakdown: which part comes from which
            vaulted relic(s) — Kevin: "What relics go to what part of
            the warframe.\""""
            emb = discord.Embed(
                title=f"🔒 {name} — vaulted parts", color=0x6A5ACD)
            for part in sorted(parts.keys()):
                refs = parts[part]
                emb.add_field(name=part,
                              value=", ".join(sorted(r.label for r in refs)),
                              inline=False)
            return f"🔒 **{name}** — {len(parts)} vaulted part(s)", [emb]

        async def _wf_vault_data():
            from sovereign_agent.discord_runtime.fetchers import wf_vault_map
            return await asyncio.to_thread(wf_vault_map, None, data_dir)

        @tree.command(name="vaulted-relics",
                      description="🔒 Warframe Prime Vault — every vaulted "
                                  "Warframe, its parts, and the relics "
                                  "that drop them.")
        @discord.app_commands.describe(
            warframe="optional — a Warframe name to see its part→relic breakdown")
        async def vaulted_relics_cmd(interaction, warframe: str = ""):
            _remember(interaction.user)
            await interaction.response.defer(ephemeral=True)
            try:
                vault = await _wf_vault_data()
            except Exception:  # noqa: BLE001 — a source being down ≠ crash
                await interaction.followup.send(
                    "🔒 couldn't reach warframe.market / drops.warframestat.us "
                    "right now — try again in a bit.", ephemeral=True)
                return
            if not vault:
                await interaction.followup.send(
                    "🔒 no vaulted Warframe data available right now.",
                    ephemeral=True)
                return
            query = warframe.strip()
            if not query:
                content, embeds = _vault_overview_embeds(vault)
                await interaction.followup.send(content, embeds=embeds, ephemeral=True)
                return
            matches = [n for n in vault if query.lower() in n.lower()]
            if not matches:
                await interaction.followup.send(
                    f"🔒 no vaulted Warframe found matching **{query}**.",
                    ephemeral=True)
                return
            if len(matches) == 1:
                content, embeds = _vault_detail_embeds(matches[0], vault[matches[0]])
                await interaction.followup.send(content, embeds=embeds, ephemeral=True)
                return
            view = discord.ui.View(timeout=180)
            opts = [discord.SelectOption(label=n[:100], value=n)
                    for n in sorted(matches)[:25]]
            view.add_item(discord.ui.Select(
                placeholder="pick the exact Warframe…", options=opts,
                custom_id="vaulted:pick"))
            await interaction.followup.send(
                f"🔒 {len(matches)} vaulted Warframes match **{query}** — pick one:",
                view=view, ephemeral=True)

        @tree.command(name="redeem",
                      description="💳 Link your Stripe purchase to unlock "
                                  "your access + timer.")
        @discord.app_commands.describe(email="the email you paid with on Stripe")
        async def redeem(interaction, email: str):
            _remember(interaction.user)
            await interaction.response.defer(ephemeral=True)
            import os
            from sovereign_agent import entitlements, stripe_sync
            key = os.environ.get("STRIPE_SECRET_KEY", "")
            # network call off the event loop
            out = await asyncio.to_thread(
                stripe_sync.confirm_purchase,
                stripe_sync._default_opener, key, email)
            if not out.get("active"):
                await interaction.followup.send(
                    f"💳 {out.get('detail', 'no active purchase found')}. "
                    "Need a hand? Open a `/ticket`. 💛", ephemeral=True)
                return
            plan = out["plan"]
            days = max(0.0, (out["expires_ts"] - time.time()) / 86400.0) \
                if out.get("expires_ts") else 30.0
            entitlements.grant(data_dir, str(interaction.user.id), plan, days,
                               source="stripe")
            # reconciler-d: remember the customer link so renewals and
            # cancellations stay truthful automatically from here on
            if out.get("customer"):
                entitlements.link_stripe(data_dir, str(interaction.user.id),
                                         out["customer"], email)
            role_name = entitlements.PLAN_ROLES.get(plan)
            added = await _grant_role(interaction.guild, interaction.user,
                                      role_name)
            audit_log(ctx.audit_path, {"op": "redeem", "plan": plan,
                                       "user": str(interaction.user.id),
                                       "role": added, "applied": True})
            await interaction.followup.send(
                f"✅ Purchase confirmed — **{plan.upper()}**, ~{int(days)} days. "
                + ("Your role's live. " if added
                   else "Ping an admin if your role doesn't appear. ")
                + "See it anytime with `/subscription`. 💛", ephemeral=True)

        @tree.command(name="buy",
                      description="🛒 Your personal buy links — purchases "
                                  "recognize you automatically.")
        async def buy(interaction):
            _remember(interaction.user)
            from sovereign_agent import shop
            from sovereign_agent.stripe_sync import buy_url
            prods = [p for p in shop.list_all(data_dir, only_active=True)
                     if p.stripe_url]
            if not prods:
                await interaction.response.send_message(
                    "🛒 the catalog's being restocked — check #storefront "
                    "or ping #order-here. 💛", ephemeral=True)
                return
            emb = discord.Embed(
                title="🛒 Your personal buy links",
                description="These links carry YOUR Discord ID — the moment "
                            "you pay, the system knows it's you: role + "
                            "timer land automatically (no `/redeem` "
                            "typing).",
                color=0x2ECC71)
            uid = str(interaction.user.id)
            for p in prods[:12]:
                dollars = p.price_cents / 100
                cadence = {"monthly": "/mo", "yearly": "/yr"}.get(
                    p.billing, "")
                emb.add_field(
                    name=f"{p.name} — ${dollars:.0f}{cadence}",
                    value=f"[Buy now]({buy_url(p.stripe_url, uid)})",
                    inline=True)
            emb.set_footer(text="Already paid the old way? /redeem <email> "
                                "still works.")
            await interaction.response.send_message(embed=emb, ephemeral=True)

        # passes-retired-d (Kevin, 2026-08-04): stripe_sync.PASS_PLANS expects
        # one-time prices of $3 / $9 / $19 / $149. Kevin's live Stripe account
        # has none of them — its one-time links are tips ($1-$1000) and two
        # bot builds. So a pass could be BOUGHT and never granted: the
        # reconciler matches on amount, finds nothing, and the buyer pays for
        # access that never arrives. Selling something we cannot deliver is
        # worse than not offering it, so the command now explains instead.
        # Re-enable by creating those four prices and restoring the view.
        @tree.command(name="passes",
                      description="🎟 All-access passes — currently unavailable.")
        async def passes_cmd(interaction):
            _remember(interaction.user)
            await interaction.response.send_message(
                "🎟 **Passes aren't available right now.**\n"
                "Use `/buy` for a monthly plan — Basic $5, Pro $12, VIP $25. "
                "Your link is personal, so access turns on automatically.",
                ephemeral=True)
            return

        async def _passes_disabled(interaction):
            content, view = build_passes_view(str(interaction.user.id))
            await interaction.response.send_message(content, view=view,
                                                     ephemeral=True)

        @tree.command(name="usage",
                      description="📊 Your daily usage meter — answers "
                                  "left, plan, credits.")
        async def usage(interaction):
            _remember(interaction.user)
            from sovereign_agent.usage_plans import compose_usage
            await interaction.response.send_message(
                compose_usage(data_dir, str(interaction.user.id)),
                ephemeral=True)

        @tree.command(name="subscription",
                      description="⏳ Your plan, time left + bonus questions.")
        async def subscription(interaction):
            _remember(interaction.user)
            from sovereign_agent.entitlements import compose_status
            await interaction.response.send_message(
                compose_status(data_dir, str(interaction.user.id)),
                ephemeral=True)

        @tree.command(name="level",
                      description="⭐ Your activity level, xp and progress.")
        async def level(interaction):
            _remember(interaction.user)
            from sovereign_agent import member_levels
            s = member_levels.get(data_dir, str(interaction.user.id))
            span = s["into_level"] + s["to_next"]
            filled = int(10 * s["into_level"] / span) if span else 0
            bar = "█" * filled + "░" * (10 - filled)
            await interaction.response.send_message(
                f"⭐ **Level {s['level']}** · {s['xp']:,} xp\n"
                f"`{bar}` {s['into_level']}/{span} to level {s['level'] + 1}\n"
                f"*{s['messages']:,} counted messages*", ephemeral=True)

        # levels-d: NOT "leaderboard" — that name is already taken by the
        # referral champions board above, and a duplicate raises
        # CommandAlreadyRegistered inside on_ready, which aborts the whole
        # tree sync. One name collision silently un-registers EVERY command.
        @tree.command(name="levels",
                      description="🏆 Most active members by activity level.")
        async def levels_cmd(interaction):
            _remember(interaction.user)
            from sovereign_agent import member_levels
            rows = member_levels.leaderboard(data_dir, 10)
            if not rows:
                await interaction.response.send_message(
                    "No activity yet — say hi in #general-chat ⭐",
                    ephemeral=True)
                return
            medals = ["🥇", "🥈", "🥉"]
            lines = []
            for i, r in enumerate(rows):
                lines.append(
                    f"{medals[i] if i < 3 else f'`{i + 1}.`'} "
                    f"<@{r['user_id']}> — level **{r['level']}** "
                    f"({r['xp']:,} xp)")
            import discord as _d
            await interaction.response.send_message(
                embed=_d.Embed(title="🏆 Most active",
                               description="\n".join(lines), color=0xF1C40F),
                ephemeral=True)

        @tree.command(
            name="reorder-server",
            description="↕ Put categories + channels in blueprint order "
                        "(owner). Moves only — never creates or deletes.")
        @discord.app_commands.describe(
            apply="false (default) = preview only; true = actually move")
        async def reorder_server(interaction, apply: bool = False):
            # reorder-d (Kevin, 2026-08-03): planner.plan is create-only by
            # design, so a rewritten blueprint changes nothing on screen —
            # Discord keeps existing categories where they already sit. This
            # is the explicitly-invoked other half. Preview by default: it
            # rearranges what everyone sees, so it should never fire from a
            # mistyped command.
            if not await _guard(interaction, "reorder_server"):
                return
            await interaction.response.defer(ephemeral=True)
            from .blueprint import canon_name, shop_blueprint
            from .reorder import describe_moves, plan_positions, plan_rehome

            guild = interaction.guild
            bp = shop_blueprint()

            # rehome-d (Kevin, 2026-08-04): channels stranded in a category
            # the blueprint retired. They aren't orphans, so /cleanup-orphans
            # rightly won't delete them — which leaves the old category
            # non-empty and therefore undeletable too. Moving them is the
            # only way out, and it must happen BEFORE repositioning: a
            # channel that changes category gets a fresh position, so
            # ordering first would immediately be undone.
            bp_homes = {ch.name: c.name for c in bp.categories
                        for ch in c.channels}
            live_homes = {ch.name: (ch.category.name if ch.category else "")
                          for ch in guild.text_channels}
            rehome = plan_rehome(bp_homes, live_homes)

            cat_moves = plan_positions(
                [c.name for c in bp.categories],
                [c.name for c in guild.categories])

            # channels are ordered WITHIN their own category — a channel's
            # position is only meaningful relative to its siblings.
            spec_by_canon = {canon_name(c.name): c for c in bp.categories}
            chan_moves: list[tuple[object, int]] = []
            for cat in guild.categories:
                spec = spec_by_canon.get(canon_name(cat.name))
                if spec is None:
                    continue                      # not ours — leave it alone
                want = [ch.name for ch in spec.channels]
                live = [ch.name for ch in cat.channels]
                by_name = {ch.name: ch for ch in cat.channels}
                for name, pos in plan_positions(want, live):
                    chan_moves.append((by_name[name], pos))

            if not apply:
                lines = ["**Preview — nothing moved.**"]
                if rehome:
                    lines.append(f"🏠 {len(rehome)} channel(s) to re-home:")
                    lines += [f"   #{ch} → {cat}" for ch, cat in rehome[:15]]
                    lines.append("   *(this is what unblocks deleting the "
                                 "old categories)*")
                lines.append(describe_moves(cat_moves))
                lines.append(f"↕ {len(chan_moves)} channel(s) would reorder "
                             "within their categories.")
                lines.append("Run `/reorder-server apply:true` to do it.")
                await interaction.followup.send("\n".join(lines)[:1900],
                                                ephemeral=True)
                return

            done, failed = 0, []
            async with _admin_lock:
                # re-home FIRST — a moved channel gets a fresh position, so
                # ordering before this would be undone immediately.
                cat_by_canon = {canon_name(c.name): c for c in guild.categories}
                for ch_name, want_cat in rehome:
                    ch = discord.utils.get(guild.text_channels, name=ch_name)
                    target = cat_by_canon.get(canon_name(want_cat))
                    if ch is None or target is None:
                        continue
                    try:
                        await ch.edit(category=target, reason="reorder-server rehome")
                        done += 1
                        await asyncio.sleep(_SEND_PACE_S)
                    except Exception:  # noqa: BLE001 — one failure ≠ abort
                        failed.append(f"#{ch_name}→{want_cat}")
                for name, pos in cat_moves:
                    cat = next((c for c in guild.categories
                                if c.name == name), None)
                    if cat is None:
                        continue
                    try:
                        await cat.edit(position=pos, reason="reorder-server")
                        done += 1
                        await asyncio.sleep(_SEND_PACE_S)
                    except Exception:  # noqa: BLE001 — one failure ≠ abort
                        failed.append(name)
                for ch, pos in chan_moves:
                    try:
                        await ch.edit(position=pos, reason="reorder-server")
                        done += 1
                        await asyncio.sleep(_SEND_PACE_S)
                    except Exception:  # noqa: BLE001
                        failed.append(f"#{ch.name}")
            audit_log(ctx.audit_path, {"op": "reorder_server", "moved": done,
                                       "failed": failed, "applied": True})
            msg = [f"↕ Reordered — {done} move(s) applied."]
            if failed:
                msg.append(f"⚠ could not move: {', '.join(failed[:10])} "
                           "(check my Manage Channels permission)")
            msg.append("Nothing was created or deleted.")
            await interaction.followup.send("\n".join(msg), ephemeral=True)

        # ── code school (code-school-d, Kevin 2026-08-04) ───────────────
        @tree.command(name="lesson",
                      description="📖 The next lesson, from your own codebase.")
        @discord.app_commands.describe(track="python or aisys")
        async def lesson_cmd(interaction, track: str = "python"):
            _remember(interaction.user)
            from sovereign_agent import code_learning_xp as _xp
            from sovereign_agent.code_school import drills as _dr
            from sovereign_agent.code_school import lessons as _ls
            from sovereign_agent.code_school import tracks as _tr
            t = _tr.track_by_slug(track)
            if t is None or t.slug not in _tr.ENABLED:
                await interaction.response.send_message(
                    f"Unknown track. Available: "
                    f"{', '.join(x.slug for x in _tr.enabled_tracks())}",
                    ephemeral=True)
                return
            done = {d.id for d in _dr.for_track(t.slug)} - {
                d.id for d in _dr.due_drills(data_dir, t.slug)}
            nxt = next((ls for ls in _ls.ordered_for_track(t.slug)
                        if ls.drill not in done), None)
            nxt = nxt or _ls.ordered_for_track(t.slug)[0]
            emb = discord.Embed(
                title=f"{t.emoji} {nxt.title}", color=0x5865F2,
                description=f"**Looked like:** {nxt.symptom}\n\n"
                            f"**Actually was:** {nxt.reality}")
            emb.add_field(name="The principle", value=nxt.principle,
                          inline=False)
            src = f"`{nxt.file}`" + (f" @ `{nxt.commit}`" if nxt.commit else "")
            emb.add_field(name="Real code", value=src, inline=False)
            if nxt.drill:
                emb.set_footer(text=f"Practise it: /drill {t.slug}")
            _xp.award(data_dir, "lesson_read", nxt.id, track=t.slug)
            await interaction.response.send_message(embed=emb, ephemeral=True)

        @tree.command(name="drill",
                      description="🧪 The next exercise to write and run.")
        @discord.app_commands.describe(track="python or aisys")
        async def drill_cmd(interaction, track: str = "python"):
            _remember(interaction.user)
            from sovereign_agent.code_school import drills as _dr
            due = _dr.due_drills(data_dir, track.strip().lower())
            if not due:
                await interaction.response.send_message(
                    "✅ Nothing due right now — everything you've passed is "
                    "scheduled for a later review. Try `/lesson` for new "
                    "material.", ephemeral=True)
                return
            d = due[0]
            body = (f"**{d.prompt}**\n\n"
                    f"```python\n{d.starter or '# your code here'}\n```\n"
                    f"Submit with `/submit drill:{d.id}` and paste your code.")
            await interaction.response.send_message(body[:1900], ephemeral=True)

        @tree.command(name="submit",
                      description="🚀 Run your drill answer and get it graded.")
        @discord.app_commands.describe(drill="drill id from /drill",
                                       code="your solution")
        async def submit_cmd(interaction, drill: str, code: str):
            _remember(interaction.user)
            # running submitted code takes real time — ack inside 3s or
            # Discord kills the interaction (see the tree-sync lesson).
            await interaction.response.defer(ephemeral=True)
            from sovereign_agent import code_learning_xp as _xp
            from sovereign_agent.code_school import drills as _dr
            from sovereign_agent.code_school.runner import run_drill
            d = _dr.by_id(drill)
            if d is None:
                await interaction.followup.send(
                    f"No drill called `{drill}`. Run `/drill` for the next "
                    "one.", ephemeral=True)
                return
            # Discord eats newlines in slash args; accept \n and fenced code
            src = code.replace("\\n", "\n").strip()
            if src.startswith("```"):
                src = src.split("```")[1]
                src = src[len("python"):] if src.startswith("python") else src
            before = _dr.progress(data_dir)
            had_failed = int(
                (_dr._read(data_dir).get(d.id) or {}).get("attempts", 0)) > 0
            res = run_drill(src, d.tests)
            rec = _dr.record_attempt(data_dir, d.id, res.passed)
            if res.passed:
                ev = ("drill_recovered" if had_failed and rec["passes"] == 1
                      else ("review_held" if rec["streak"] > 1
                            else "drill_passed"))
                _xp.award(data_dir, ev, d.id, track=d.track)
                s = _xp.summary(data_dir)
                msg = (f"✅ **Passed** — {d.id}\n{res.detail}\n"
                       f"⭐ level {s['level']} · {s['xp']} xp · "
                       f"next review in "
                       f"{_dr.next_interval_days(rec['streak']):.0f}d")
            else:
                msg = (f"{res.icon} **Not yet** — {d.id}\n```\n"
                       f"{res.detail}\n```\n"
                       + (f"💡 {d.hint}" if d.hint else ""))
            await interaction.followup.send(msg[:1900], ephemeral=True)

        @tree.command(name="progress",
                      description="📈 Your coding progress and what's due.")
        async def progress_cmd(interaction):
            _remember(interaction.user)
            from sovereign_agent import code_learning_xp as _xp
            from sovereign_agent.code_school import drills as _dr
            from sovereign_agent.code_school import tracks as _tr
            s = _xp.summary(data_dir)
            lines = [f"⭐ **Level {s['level']}** · {s['xp']} xp "
                     f"({s['to_next']} to next)"]
            for t in _tr.enabled_tracks():
                p = _dr.progress(data_dir, t.slug)
                due = len(_dr.due_drills(data_dir, t.slug))
                lines.append(f"{t.emoji} **{t.name}** — {p['passed']}/"
                             f"{p['total']} drills passed · {due} due now")
            await interaction.response.send_message("\n".join(lines),
                                                    ephemeral=True)

        @tree.command(name="redemptions",
                      description="🧾 Who needs redeeming + what they get "
                                  "(owner, read-only).")
        async def redemptions(interaction):
            from sovereign_agent import members as _mem
            if not _mem.is_owner(data_dir, str(interaction.user.id)):
                await interaction.response.send_message(
                    "That's an owner command.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            import os
            from sovereign_agent import (entitlements, redemption_queue,
                                         stripe_reconcile, stripe_sync)
            key = (os.environ.get("STRIPE_SECRET_KEY") or "").strip()
            actions = {"syncs": [], "revokes": [], "unmatched": []}
            if key:
                subs = await asyncio.to_thread(
                    stripe_sync.list_subscriptions,
                    stripe_sync._default_opener, key)
                refs = await asyncio.to_thread(
                    stripe_sync.checkout_refs,
                    stripe_sync._default_opener, key)
                actions = stripe_reconcile.plan_actions(
                    subs, refs, entitlements.list_all(data_dir))
            out = redemption_queue.compose_redemption_list(
                actions, data_dir,
                mid_task=redemption_queue.is_mid_task())
            await interaction.followup.send(out[:1900], ephemeral=True)

        @tree.command(name="grant",
                      description="⏳ Grant/extend a member's plan + timer "
                                  "(owner).")
        @discord.app_commands.describe(user="who", plan="basic/pro/vip/scout-pass",
                                       days="days to add (stacks)")
        async def grant_cmd(interaction, user: discord.Member, plan: str,
                            days: int = 30):
            from sovereign_agent import entitlements, members as _mem
            if not _mem.is_owner(data_dir, str(interaction.user.id)):
                await interaction.response.send_message(
                    "That's an owner command.", ephemeral=True)
                return
            p = plan.strip().lower()
            entitlements.grant(data_dir, str(user.id), p, days, source="manual")
            added = await _grant_role(interaction.guild, user,
                                      entitlements.PLAN_ROLES.get(p))
            audit_log(ctx.audit_path, {"op": "grant", "plan": p,
                                       "target": str(user.id), "days": days,
                                       "role": added, "applied": True})
            await interaction.response.send_message(
                f"⏳ Granted {user.mention} **{p.upper()}** for {days}d"
                + ("." if added else " (role pending — check hierarchy)."),
                ephemeral=True)

        @tree.command(name="menu",
                      description="📋 Your commands — everyone, plus more "
                                  "if you're a subscriber.")
        async def menu(interaction):
            # help-boards-d (Kevin, 2026-07-27): "a help command for...
            # subscribers" — everyone's tier PLUS the subscriber tier
            # (e.g. /ma) from the one audited COMMANDS list, plus the
            # perk callouts below (those describe CHANNELS/benefits,
            # not commands, so they stay hand-written).
            _remember(interaction.user)
            from sovereign_agent import entitlements
            uid = str(interaction.user.id)
            roles = {r.name for r in getattr(interaction.user, "roles", []) or []}
            is_sub = (entitlements.is_active(data_dir, uid)
                      or any(r.startswith("Subscriber") for r in roles))
            emb = build_commands_embed(
                "📋 Your commands", 0x3fd0c9, "subscriber",
                intro="Everything you can run right now.")
            if is_sub:
                emb.add_field(name="⭐ Subscriber perks", inline=False, value=(
                    "Your full-speed alerts + stats live in the Subscribers "
                    "channels · priority support (Pro/VIP)."))
            if "Subscriber-VIP" in roles:
                emb.add_field(name="💎 VIP", inline=False, value=(
                    "Custom bot builds · early access · ask-Aria priority."))
            emb.set_footer(text="Ephemeral — only you see this. 💛")
            await interaction.response.send_message(embed=emb, ephemeral=True)

        @tree.command(name="admin",
                      description="🛠 Owner command menu — everything "
                                  "above, plus owner-exclusive controls.")
        async def admin_menu(interaction):
            # help-boards-d (Kevin, 2026-07-27): "a help command for
            # admins" — the owner tier (a strict superset of team) from
            # the one audited COMMANDS list; this exact panel was
            # missing /grant, /redemptions, /marketer, /tracker,
            # /ticket-panel and more before today.
            from sovereign_agent import members as _mem
            if not _mem.is_owner(data_dir, str(interaction.user.id)):
                await interaction.response.send_message(
                    "That's the owner menu — try `/menu`. 💛", ephemeral=True)
                return
            emb = build_commands_embed(
                "🛠 Owner commands", 0xffb43f, "owner",
                intro="Also yours: cockpit `/sm` server announcements · "
                     "`/ma` inbox mail.")
            await interaction.response.send_message(embed=emb, ephemeral=True)

        @tree.command(name="mod-report",
                      description="🛡 Recent moderation actions (owner/staff).")
        async def mod_report(interaction):
            _remember(interaction.user)
            if not _is_staff(interaction):
                await interaction.response.send_message(
                    "That's for staff.", ephemeral=True)
                return
            from sovereign_agent.moderation import compose_mod_report
            await interaction.response.send_message(
                compose_mod_report(data_dir), ephemeral=True)

        @tree.command(name="mod-unmute",
                      description="🔊 Lift a member's mute (owner/staff).")
        @discord.app_commands.describe(user="who to unmute", reason="why")
        async def mod_unmute(interaction, user: discord.Member,
                             reason: str = "staff cleared"):
            _remember(interaction.user)
            if not _is_staff(interaction):
                await interaction.response.send_message(
                    "That's for staff.", ephemeral=True)
                return
            from sovereign_agent import moderation
            ok = False
            try:
                await user.timeout(None, reason=f"unmute: {reason}")
                ok = True
            except Exception:  # noqa: BLE001
                pass
            moderation.record(data_dir, moderation.UNMUTE, str(user.id),
                              user.name, reason,
                              decided_by=str(interaction.user.name))
            await interaction.response.send_message(
                f"🔊 Unmuted {user.mention}." if ok else
                "Recorded — but I couldn't lift the timeout (perms/hierarchy).",
                ephemeral=True)

        @tree.command(name="mod-history",
                      description="🛡 A member's moderation history (owner/staff).")
        @discord.app_commands.describe(user="whose history")
        async def mod_history(interaction, user: discord.Member):
            _remember(interaction.user)
            if not _is_staff(interaction):
                await interaction.response.send_message(
                    "That's for staff.", ephemeral=True)
                return
            from sovereign_agent.moderation import history
            h = history(data_dir, str(user.id), limit=10)
            if not h:
                await interaction.response.send_message(
                    f"No moderation records for {user.mention}. 💛",
                    ephemeral=True)
                return
            lines = [f"🛡 **{user.name}** — last {len(h)}:"]
            for r in h:
                lines.append(f"• {r['action']} · {r['reason'][:55]} · "
                             f"{r.get('decided_by', '?')}")
            await interaction.response.send_message("\n".join(lines),
                                                    ephemeral=True)

        @tree.command(name="ticket",
                      description="🎫 Open a private support ticket.")
        @discord.app_commands.describe(
            subject="what you need help with",
            category="order / support / custom / billing / other")
        async def ticket(interaction, subject: str, category: str = "support"):
            from sovereign_agent.tickets import CATEGORIES
            c = category.strip().lower()
            c = c if c in CATEGORIES else "other"
            await _open_ticket_flow(interaction, c, subject)

        @tree.command(name="tickets",
                      description="🎫 The open-ticket board (staff/owner).")
        async def tickets_board(interaction):
            _remember(interaction.user)
            if not _is_staff(interaction):
                await interaction.response.send_message(
                    "That board is for staff — open your own with `/ticket`.",
                    ephemeral=True)
                return
            from sovereign_agent.tickets import compose_board
            await interaction.response.send_message(
                compose_board(data_dir), ephemeral=True)

        @tree.command(name="ticket-panel",
                      description="Post the 'Open a Ticket' panel here (owner).")
        async def ticket_panel(interaction):
            if not await _guard(interaction, "ticket_panel"):
                return
            view = discord.ui.View(timeout=None)
            view.add_item(discord.ui.Button(
                label="🎫 Open a Ticket", style=discord.ButtonStyle.primary,
                custom_id="tkt:new"))
            emb = discord.Embed(
                title="🎫 Need help? Open a private ticket",
                description=("Order help · support · a custom-bot idea · "
                             "billing — click below. Your ticket is a "
                             "**private thread** only you + our staff can see. "
                             "💛"),
                color=0x5865F2)
            await interaction.channel.send(embed=emb, view=view)
            await interaction.response.send_message("🎫 panel posted.",
                                                    ephemeral=True)

        @tree.command(name="roster",
                      description="The client database — who she knows by ID "
                                  "(owner).")
        async def roster(interaction):
            if not await _guard(interaction, "roster"):
                return
            from sovereign_agent.members import compose_roster
            from sovereign_agent.discord_limits import split_text
            await interaction.response.defer(ephemeral=True)
            for part in split_text(compose_roster(data_dir), 1900)[:3]:
                await interaction.followup.send(part, ephemeral=True)

        @tree.command(name="scout",
                      description="🌐 The Scout Hub — every tracker, finds "
                                  "private to you.")
        async def scout_cmd(interaction):
            await interaction.response.send_message(
                embed=hub_embed_obj(), view=build_hub_view(), ephemeral=True)

        @tree.command(name="scout-panel",
                      description="Post the living Scout Hub in this "
                                  "channel (owner).")
        async def scout_panel_cmd(interaction):
            if not await _guard(interaction, "scout_panel"):
                return
            await interaction.response.defer(ephemeral=True)
            msg = await interaction.channel.send(
                embed=hub_embed_obj(), view=build_hub_view())
            try:
                await msg.pin(reason="the living Scout Panel")
            except Exception:  # noqa: BLE001 — pin is nice-to-have
                pass
            import json as _json
            p = _panel_state_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(_json.dumps({"channel_id": interaction.channel.id,
                                      "message_id": msg.id}),
                         encoding="utf-8")
            audit_log(ctx.audit_path, {"op": "scout_panel",
                                       "channel": interaction.channel.name,
                                       "applied": True})
            await interaction.followup.send(
                "🔭 panel posted + pinned — it refreshes itself every few "
                "minutes.", ephemeral=True)

        async def _do_seed_channels(interaction) -> str:
            from sovereign_agent.discord_admin.channel_guides import (
                already_seeded, guide_for, mark_seeded)
            posted, skipped, missing = 0, 0, 0
            async with _admin_lock:                # wait our turn; no conflicts
                from sovereign_agent.discord_limits import split_text
                for channel in interaction.guild.text_channels:
                    guide = guide_for(channel.name)
                    if guide is None:
                        missing += 1
                        continue
                    if already_seeded(data_dir, channel.name):
                        skipped += 1
                        continue
                    try:
                        for part in split_text(guide, 1900)[:2]:
                            await _paced_send(channel, part)   # rate-limit-safe
                        mark_seeded(data_dir, channel.name)
                        posted += 1
                    except Exception:  # noqa: BLE001 — one channel ≠ abort
                        continue
            audit_log(ctx.audit_path, {"op": "seed_channels",
                                       "posted": posted, "skipped": skipped,
                                       "applied": True})
            return (f"📚 guides: {posted} posted · {skipped} already seeded · "
                    f"{missing} channels without a guide.")

        _admin_ops["seed"] = _do_seed_channels         # bridge-d: publish

        @tree.command(name="seed-channels",
                      description="Fill every channel with its guide/rules "
                                  "post (owner, idempotent).")
        async def seed_channels(interaction):
            if not await _guard(interaction, "seed_channels"):
                return
            await interaction.response.defer(ephemeral=True)
            if _admin_lock.locked():
                await interaction.followup.send(
                    "⏳ Another setup task is running — I'll wait my turn "
                    "so nothing conflicts. Give me a moment…", ephemeral=True)
            await interaction.followup.send(
                await _do_seed_channels(interaction), ephemeral=True)

        # setup-all-d (Kevin's ask): "a command that executes the full suite
        # of setup commands" — one shot, in order, each phase taking its own
        # turn on the lock, one running progress reply.
        @tree.command(name="setup-all",
                      description="🚀 The whole setup in one shot: shop → webhooks → guides (owner).")
        async def setup_all(interaction):
            if not await _guard(interaction, "setup_all"):
                return
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(
                "🚀 Full setup starting — three phases, each waits its "
                "turn:\n1️⃣ server structure → 2️⃣ webhooks → 3️⃣ channel "
                "guides. Receipts follow as each lands.", ephemeral=True)
            phases = (("1️⃣ structure", _do_setup_shop),
                      ("2️⃣ webhooks", _do_setup_webhooks),
                      ("3️⃣ guides", _do_seed_channels))
            for label, phase in phases:
                try:
                    result = await phase(interaction)
                except Exception as exc:  # noqa: BLE001 — one phase ≠ abort
                    result = (f"✗ {label} hit {type(exc).__name__} — the "
                              "other phases still run; re-run me anytime "
                              "(everything is idempotent).")
                await interaction.followup.send(
                    f"{label} done:\n{result}"[:1900], ephemeral=True)
            audit_log(ctx.audit_path, {"op": "setup_all", "applied": True})
            await interaction.followup.send(
                "✅ /setup-all complete. Finishing touches when you want "
                "them: `/scout-panel` · `/ticket-panel` · `/audit-channels` "
                "for the consolidation worksheet. 💛", ephemeral=True)

    # lounge-d — the social channels where she hangs out but never
    # dominates: she only replies when @mentioned or called by name.
    LOUNGE_CHANNELS = {"general-chat", "bot-talk", "wins-and-pulls",
                       "off-topic", "bot-commands"}

    # ── 🔭 scout-d: the Scout Panel (buttons that show the data) ─────────
    # Every lane reply is EPHEMERAL — a member's scouting info is theirs
    # alone (Kevin's ask). Pure logic lives in scout.py.
    PING_ROLE = "Scout-Ping"

    def _scout_embed_obj(lane: str):
        from sovereign_agent.scout import lane_embed
        return discord.Embed.from_dict(lane_embed(data_dir, lane))

    async def _toggle_ping_role(interaction) -> str:
        guild = interaction.guild
        if guild is None:
            return "🔔 pings live in the server, not DMs!"
        role = next((r for r in guild.roles if r.name == PING_ROLE), None)
        if role is None:
            role = await guild.create_role(
                name=PING_ROLE, mentionable=True,
                reason="Scout ping opt-in role (self-serve)")
        member = interaction.user
        if role in getattr(member, "roles", []):
            await member.remove_roles(role, reason="scout ping opt-out")
            return "🔕 Scout pings OFF — flip them back on anytime."
        await member.add_roles(role, reason="scout ping opt-in")
        return ("🔔 Scout pings ON — you'll be @'d when something hot "
                "lands. Want it faster + filtered? → #storefront 💛")

    class AreaModal(discord.ui.Modal, title="⚙ My Area & Preferences"):
        country = discord.ui.TextInput(
            label="Country / region (for non-US members)",
            placeholder="US · UK · Canada · Australia … (blank = US)",
            required=False, max_length=40)
        area = discord.ui.TextInput(
            label="Zip / postal / state (blank = clear area)",
            placeholder="42240 · 42240 r50 · 42240, 37040 · KY",
            required=False, max_length=80)
        prefer = discord.ui.TextInput(
            label="How to get it? local / pickup / delivery / all",
            placeholder="all  (or: local, pickup, delivery)",
            required=False, max_length=16)

        async def on_submit(self, interaction):  # noqa: ANN001
            from sovereign_agent import members
            from sovereign_agent.scout import area_summary, parse_area, save_area
            uid = str(interaction.user.id)
            _remember(interaction.user)
            # fulfillment preference
            pref = (str(self.prefer.value or "").strip().lower() or "all")
            valid = {"local", "pickup", "delivery", "all"}
            pref = pref if pref in valid else "all"
            region = (str(self.country.value or "").strip() or None)
            members.set_prefs(data_dir, uid, region=region, fulfillment=pref)
            # area
            raw = str(self.area.value or "").strip()
            if not raw:
                save_area(data_dir, uid, None)
                where = "area cleared"
            else:
                parsed = parse_area(raw)
                if parsed is None:
                    await interaction.response.send_message(
                        "⚙ Saved your region + preference. For the area I "
                        "couldn't read that — try `42240`, `42240 r50`, a "
                        "list, or a state/postal code.", ephemeral=True)
                    return
                save_area(data_dir, uid, parsed)
                where = area_summary(parsed)
            reg = f" · region {region}" if region else ""
            await interaction.response.send_message(
                f"⚙ Saved (only you see this): {where}{reg} · show me "
                f"**{pref}** finds. 💛", ephemeral=True)

    class RequiredAreaModal(discord.ui.Modal, title="📍 Set your area (required)"):
        """my-panel-d (Kevin, 2026-07-25/26): "each person has to link
        their zip code and the radius... 25 miles minimum maybe a few
        hundred or thousand maximum" + "make it where we can change the
        zip code or radius anytime." Unlike AreaModal (that one's fields
        are all optional — general preference editing), both fields here
        are REQUIRED — used both for the one-time gate before /my-panel
        opens the first time, AND for the "📍 change area" button any
        time after, pre-filled with whatever's already saved."""
        zip_code = discord.ui.TextInput(
            label="Zip / postal code", placeholder="42240",
            required=True, max_length=10)
        radius = discord.ui.TextInput(
            label="Radius in miles (25-1000)", placeholder="50",
            required=True, max_length=5)

        def __init__(self, *, current_zip: str = "", current_radius: str = ""):
            super().__init__()
            if current_zip:
                self.zip_code.default = current_zip
            if current_radius:
                self.radius.default = current_radius

        async def on_submit(self, interaction):  # noqa: ANN001
            from sovereign_agent.scout import area_summary, parse_area, save_area
            uid = str(interaction.user.id)
            _remember(interaction.user)
            raw = f"{self.zip_code.value} r{self.radius.value}"
            parsed = parse_area(raw)
            if parsed is None or parsed.get("radius_mi") is None:
                await interaction.response.send_message(
                    "Couldn't read that — a zip/postal code plus a radius "
                    "in miles (25-1000), e.g. zip `42240`, radius `50`. "
                    "Run /my-panel again to retry.", ephemeral=True)
                return
            save_area(data_dir, uid, parsed)
            member_roles = {r.name for r in getattr(interaction.user, "roles", []) or []}
            await interaction.response.send_message(
                f"📍 area saved: {area_summary(parsed)}\n\n{MY_PANEL_INTRO}",
                view=build_my_panel_view(member_roles), ephemeral=True)

    def _area_modal_for(uid: str):
        """my-panel-d: "change the zip code or radius anytime" — pre-fill
        the modal with whatever's already saved so editing isn't
        re-typing from scratch."""
        from sovereign_agent.scout import load_area
        area = load_area(data_dir, uid) or {}
        zips = area.get("zips") or []
        return RequiredAreaModal(
            current_zip=zips[0] if zips else "",
            current_radius=str(area.get("radius_mi") or ""))

    class ScoutView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)      # persistent across restarts

        @discord.ui.button(label="🌐 Online", custom_id="scout:online",
                           style=discord.ButtonStyle.primary)
        async def online(self, interaction, button):  # noqa: ANN001
            await interaction.response.send_message(
                embed=_scout_embed_obj("online"), ephemeral=True)

        @discord.ui.button(label="🏪 Local", custom_id="scout:local",
                           style=discord.ButtonStyle.primary)
        async def local(self, interaction, button):  # noqa: ANN001
            await interaction.response.send_message(
                embed=_scout_embed_obj("local"), ephemeral=True)

        @discord.ui.button(label="💸 Deals", custom_id="scout:deals",
                           style=discord.ButtonStyle.primary)
        async def deals(self, interaction, button):  # noqa: ANN001
            await interaction.response.send_message(
                embed=_scout_embed_obj("deals"), ephemeral=True)

        @discord.ui.button(label="🔔 Ping me", custom_id="scout:ping",
                           style=discord.ButtonStyle.secondary)
        async def ping(self, interaction, button):  # noqa: ANN001
            try:
                msg = await _toggle_ping_role(interaction)
            except Exception:  # noqa: BLE001
                msg = "🔔 couldn't flip the role — tell BigKev!"
            await interaction.response.send_message(msg, ephemeral=True)

        @discord.ui.button(label="⚙ My Area", custom_id="scout:area",
                           style=discord.ButtonStyle.secondary)
        async def my_area(self, interaction, button):  # noqa: ANN001
            await interaction.response.send_modal(AreaModal())

        @discord.ui.button(label="📈 Today", custom_id="scout:today",
                           style=discord.ButtonStyle.secondary)
        async def today(self, interaction, button):  # noqa: ANN001
            from sovereign_agent.scout import day_stats
            s = day_stats(data_dir)
            hot = f"\nhottest seen: {s['hottest']}" if s.get("hottest") else ""
            await interaction.response.send_message(
                f"📈 today: **{s['total']}** finds — "
                f"🌐 {s['per_lane'].get('online', 0)} · "
                f"🏪 {s['per_lane'].get('local', 0)} · "
                f"💸 {s['per_lane'].get('deals', 0)}{hot}", ephemeral=True)

    # ── 🌐 scout HUB (verticals-d): most-important buttons + ▸ View more ──
    # All Hub clicks dispatch through on_interaction by custom_id, so they
    # keep working across restarts without per-view registration.
    def build_hub_view():
        from sovereign_agent.verticals import star_verticals
        view = discord.ui.View(timeout=None)
        row = 0
        for i, v in enumerate(star_verticals()[:10]):
            view.add_item(discord.ui.Button(
                label=f"{v.emoji} {v.name}"[:80], custom_id=f"hubv:{v.slug}",
                style=discord.ButtonStyle.primary, row=i // 5))
            row = i // 5
        row += 1
        view.add_item(discord.ui.Button(
            label="▸ View more trackers", custom_id="hubmore",
            style=discord.ButtonStyle.success, row=min(row, 4)))
        view.add_item(discord.ui.Button(
            label="⚙ My Area", custom_id="hubarea",
            style=discord.ButtonStyle.secondary, row=min(row, 4)))
        view.add_item(discord.ui.Button(
            label="📈 Today", custom_id="hubtoday",
            style=discord.ButtonStyle.secondary, row=min(row, 4)))
        return view

    def build_deep_select():
        from sovereign_agent.verticals import deep_verticals, star_verticals
        # any ★ beyond the 10 button slots + every deep niche (≤25 options)
        more = star_verticals()[10:] + deep_verticals()
        opts = [discord.SelectOption(
            label=f"{v.emoji} {v.name}"[:100],
            value=v.slug, description=v.blurb[:100]) for v in more[:25]]
        sel = discord.ui.Select(placeholder="▸ pick another tracker…",
                                options=opts, custom_id="hubdeep")
        view = discord.ui.View(timeout=180)
        view.add_item(sel)
        return view

    def build_vertical_view(slug):
        from sovereign_agent.verticals import get_vertical
        v = get_vertical(slug)
        view = discord.ui.View(timeout=180)
        if v is not None:
            view.add_item(discord.ui.Button(
                label=f"🔔 ping me for {v.name}"[:80],
                custom_id=f"vping:{slug}",
                style=discord.ButtonStyle.secondary))
        return view

    def hub_embed_obj():
        from sovereign_agent.scout import panel_embed
        e = panel_embed(data_dir)
        e["title"] = "🌐 Aria's Scout Hub — pick a tracker"
        e["description"] = (
            "Live restock + deal trackers across every niche — cards, "
            "sneakers, LEGO, GPUs, consoles, deals & more. Tap a tracker "
            "for its latest finds (private to you), or **▸ View more** for "
            "the full catalog.\n\n" + e["description"].split("\n\n", 1)[-1])
        return discord.Embed.from_dict(e)

    async def _vertical_role(guild, v):
        """subscribe-d: the ONE role that gates both #{v.track_channel}'s
        visibility (blueprint.py) and its ping — resolve-or-create so a
        member can subscribe even before /setup-shop has minted it."""
        role = next((r for r in guild.roles if r.name == v.ping_role), None)
        if role is None:
            role = await guild.create_role(name=v.ping_role, mentionable=True,
                                           reason=f"{v.name} tracker subscribe")
        return role

    async def _toggle_vertical_ping(interaction, slug) -> str:
        from sovereign_agent.verticals import get_vertical
        v = get_vertical(slug)
        guild = interaction.guild
        if v is None or guild is None:
            return "🔔 pings live in the server!"
        role = await _vertical_role(guild, v)
        member = interaction.user
        if role in getattr(member, "roles", []):
            await member.remove_roles(role)
            return f"🔕 {v.name} unsubscribed — #{v.track_channel} is hidden again."
        await member.add_roles(role)
        return (f"🔔 {v.name} subscribed — #{v.track_channel} is visible + "
                "you'll be @'d on hot finds. 💛")

    # ── & My Panel (my-panel-d) ──────────────────────────────────────────────
    # Kevin, 2026-07-26: "a per user control panel for each user — with
    # buttons to subscribe to each category. Optimized for mobile users...
    # add categories and channels to the control panel. Quick select
    # categories then the channels can be selected or deselected whenever."
    # One category button per subscribable category (bulk on/off for
    # everything in it); tapping a category also drops a dropdown below
    # for fine-tuning individual channels within it. All decision logic
    # (who gets which role) lives in verticals.bulk_toggle_roles /
    # select_diff_roles — pure, unit-tested; this is thin wiring over it.
    MY_PANEL_INTRO = (
        "**& My Subscribe Panel**\n"
        "Tap a category to subscribe/unsubscribe from ALL its channels at "
        "once. Tap it again to flip it back. Use the dropdown that appears "
        "below a category to fine-tune individual channels within it."
    )

    async def _near_me_report(uid: str) -> str:
        """location-filter-d (Kevin, 2026-07-27): the on-request "near
        me" pull — real distance-matched finds (geo.py, real geocoding,
        no fabricated proximity), or an honest reason there's nothing to
        show (no area set / a genuine quiet stretch). Geocoding is a
        real network call, so it's offloaded via to_thread — never
        blocks the gateway."""
        from sovereign_agent.scout import area_summary, load_area, nearby_finds
        area = await asyncio.to_thread(load_area, data_dir, uid)
        if not area:
            return ("📍 you haven't set an area yet — tap **📍 change area** "
                    "on /my-panel, then try this again.")
        finds = await asyncio.to_thread(nearby_finds, data_dir, area)
        if not finds:
            return (f"📍 nothing near you right now ({area_summary(area)}) — "
                    "I'm still watching. Try again later!")
        lines = [f"📍 **Near you** ({area_summary(area)}):"]
        for f in finds:
            age_m = max(0, int((time.time() - f["ts"]) / 60))
            age = f"{age_m}m" if age_m < 120 else f"{age_m // 60}h"
            url = f.get("url", "")
            text = (f.get("text") or "")[:150]
            entry = f"[{text}]({url})" if url else text
            lines.append(f"• {entry} · 📍 {f['location']} · {age} ago")
        from sovereign_agent.discord_limits import split_text
        return split_text("\n".join(lines), 1900)[0]

    # ── 🎟 Passes Control Panel (passes-d) ───────────────────────────────────
    # Kevin, 2026-07-26: "create a passes control panel that people can
    # spawn with buttons for different passes." Every button here is a
    # discord.ButtonStyle.link — a direct, personalized checkout URL, no
    # interaction round-trip (no on_interaction handler needed at all):
    # click = Stripe opens. Safe to personalize per-button because the
    # response is ephemeral — built fresh, once, only for the requester.
    def build_passes_view(discord_id: str):
        from sovereign_agent import entitlements, shop
        from sovereign_agent.stripe_sync import buy_url

        passes = sorted(
            (p for p in shop.list_all(data_dir, only_active=True)
             if p.kind == "access-pass" and p.duration_days),
            key=lambda p: p.duration_days)

        st = entitlements.status(data_dir, discord_id)
        if st["active"]:
            status_line = (f"📍 you already have **{str(st['plan']).upper()}** "
                           f"active — {st['days_left']:.1f} day(s) left. "
                           "Buying another pass adds to this timer, it "
                           "never restarts it.")
        else:
            status_line = "You don't have an active pass right now."

        content = ("**🎟 Passes — all-access, sold by time**\n"
                  f"{status_line}\n"
                  "Tap a pass to check out — the link already knows it's "
                  "you, no `/redeem` needed.")

        view = discord.ui.View(timeout=300)
        row = 0
        for p in passes:
            if not p.stripe_url:
                continue        # not yet configured — never show a dead button
            view.add_item(discord.ui.Button(
                label=f"{p.name} — {p.price_label()}"[:80],
                style=discord.ButtonStyle.link,
                url=buy_url(p.stripe_url, discord_id),
                row=row))
            row = min(row + 1, 4)
        return content, view

    async def _apply_role_names(guild, member, role_names_to_add, role_names_to_remove):
        """Resolve role NAMES (from the pure verticals.py decision
        functions) to real guild roles and apply the membership change —
        the one spot that touches the live guild for the My Panel."""
        # stuck-panel-d (Kevin, 2026-08-04): "my panel still not working."
        # This used to call add_roles ONCE PER ROLE. Subscribing to WARFRAME
        # is eight roles, so eight sequential round-trips (plus rate-limit
        # sleeps) ran BEFORE the handler responded — comfortably past
        # Discord's 3-second interaction deadline, so the panel just span.
        #
        # discord.py's add_roles/remove_roles are variadic and issue ONE
        # request for the whole set, so batching turns 8 calls into 1. The
        # per-role loop is kept only for RESOLVING names (creating a missing
        # vertical role), which is local work in the common case.
        from sovereign_agent.verticals import CATALOG_BY_SLUG
        by_role_name = {v.ping_role: v for v in CATALOG_BY_SLUG.values()}
        current = list(getattr(member, "roles", []) or [])

        to_add = []
        for name in role_names_to_add:
            v = by_role_name.get(name)
            role = await _vertical_role(guild, v) if v is not None else \
                next((r for r in guild.roles if r.name == name), None)
            if role is not None and role not in current:
                to_add.append(role)
        if to_add:
            await member.add_roles(*to_add, reason="my-panel subscribe")

        to_remove = [r for r in
                     (next((g for g in guild.roles if g.name == n), None)
                      for n in role_names_to_remove)
                     if r is not None and r in current]
        if to_remove:
            await member.remove_roles(*to_remove, reason="my-panel unsubscribe")

    # ── 🎫 ticketing (ticket-d) ──────────────────────────────────────────────
    def _is_staff(interaction) -> bool:
        """Owner or a Staff/Support role holder — the people who work tickets."""
        from sovereign_agent import members, tickets as _tk
        if members.is_owner(data_dir, str(interaction.user.id)):
            return True
        names = {r.name for r in getattr(interaction.user, "roles", []) or []}
        return bool(names & set(_tk.STAFF_ROLES))

    def _ticket_view(tid: str, status: str = "open"):
        v = discord.ui.View(timeout=None)
        v.add_item(discord.ui.Button(
            label="🙋 Claim", style=discord.ButtonStyle.primary,
            custom_id=f"tkt:claim:{tid}"))
        v.add_item(discord.ui.Button(
            label="✅ Resolve", style=discord.ButtonStyle.success,
            custom_id=f"tkt:resolve:{tid}"))
        v.add_item(discord.ui.Button(
            label="🔒 Close", style=discord.ButtonStyle.secondary,
            custom_id=f"tkt:close:{tid}"))
        return v

    async def _open_ticket_flow(interaction, category: str, subject: str):
        """Create the ticket record + a PRIVATE thread only the opener +
        Owner/Staff/Support + Aria can see. Falls back gracefully."""
        from sovereign_agent import tickets
        _remember(interaction.user)
        uname = getattr(interaction.user, "name", "") or "member"
        t = tickets.open_ticket(data_dir, str(interaction.user.id), uname,
                                category, subject)
        thread = None
        try:
            base = interaction.channel
            thread = await base.create_thread(
                name=f"{t['id']}-{category}"[:90],
                type=discord.ChannelType.private_thread,
                invitable=False, reason=f"ticket {t['id']}")
            await thread.add_user(interaction.user)
            tickets.set_channel(data_dir, t["id"], thread.id)
            # auto-add the owner + every Staff/Support member so they can see
            # and claim it (no 'Manage Threads' perm needed). Degrades quietly.
            try:
                from sovereign_agent import members as _mem
                guild = base.guild
                to_add = set()
                oid = _mem.owner_id()
                if oid and oid.isdigit() and guild.get_member(int(oid)):
                    to_add.add(guild.get_member(int(oid)))
                for rn in tickets.STAFF_ROLES:
                    role = discord.utils.get(guild.roles, name=rn)
                    if role:
                        to_add.update(role.members)
                for m in to_add:
                    if m and m.id != interaction.user.id:
                        try:
                            await thread.add_user(m)
                        except Exception:  # noqa: BLE001
                            pass
            except Exception:  # noqa: BLE001
                pass
            await thread.send(
                tickets.compose_ticket(t) +
                "\n\nThanks — a staff member will be with you shortly. "
                "Add any details here. 💛",
                view=_ticket_view(t["id"]))
        except Exception:  # noqa: BLE001 — private threads may be unavailable
            pass
        audit_log(ctx.audit_path, {"op": "ticket_open", "id": t["id"],
                                   "category": category, "applied": True})
        where = thread.mention if thread else "(a staff member will reach out)"
        await interaction.response.send_message(
            f"🎫 Opened **{t['id']}** — {where}. Only you + staff can see it.",
            ephemeral=True)

    class TicketModal(discord.ui.Modal, title="🎫 Open a ticket"):
        cat = discord.ui.TextInput(          # label must be <= 45 chars
            label="Type (order/support/custom/billing/other)",
            placeholder="support", required=False, max_length=16)
        subject = discord.ui.TextInput(
            label="What do you need help with?",
            placeholder="Briefly describe it…", max_length=200)

        async def on_submit(self, interaction):  # noqa: ANN001
            from sovereign_agent.tickets import CATEGORIES
            c = (str(self.cat.value or "").strip().lower() or "support")
            c = c if c in CATEGORIES else "other"
            await _open_ticket_flow(interaction, c, str(self.subject.value or ""))

    async def _ticket_button(interaction, action: str, tid: str):
        """Claim/Resolve/Close from the buttons on a ticket card."""
        from sovereign_agent import tickets
        uid = str(interaction.user.id)
        uname = getattr(interaction.user, "name", "") or uid
        t0 = tickets.load(data_dir, tid)
        opener = t0 and t0.get("opener_id") == uid
        # claim/resolve = staff only; close = staff OR the opener
        if action in ("claim", "resolve") and not _is_staff(interaction):
            await interaction.response.send_message(
                "Only staff can do that — but you can add details here anytime.",
                ephemeral=True)
            return
        if action == "close" and not (_is_staff(interaction) or opener):
            await interaction.response.send_message(
                "Only staff or the ticket owner can close it.", ephemeral=True)
            return
        fn = {"claim": tickets.claim, "resolve": tickets.resolve,
              "close": tickets.close}[action]
        ok, msg, t = fn(data_dir, tid, uid, uname)
        audit_log(ctx.audit_path, {"op": f"ticket_{action}", "id": tid,
                                   "by": uname, "applied": ok})
        if not ok:
            await interaction.response.send_message(msg or "Couldn't do that.",
                                                    ephemeral=True)
            return
        note = {"claim": f"🙋 **{uname}** claimed this ticket — on it.",
                "resolve": f"✅ Marked **resolved** by {uname}.",
                "close": f"🔒 Ticket **closed** by {uname}. Reopen anytime with "
                         "`/ticket` or ask staff."}[action]
        await interaction.response.send_message(note, ephemeral=False)

    # ── 🛡 guards + bounded auto-mute (mod-d) ─────────────────────────────────
    from sovereign_agent import ask_guard as _guard_mod
    _mod_strikes = _guard_mod.StrikeBook()

    async def _report_mod(guild, rec, muted: bool) -> None:
        """Report an action to #mod-log + a best-effort owner DM."""
        from sovereign_agent import members as _mem, moderation
        text = moderation.compose_owner_alert(rec)
        if not muted:
            text = "⚠ (NOT muted — over daily cap, needs your review)\n" + text
        try:
            ch = next((c for c in getattr(guild, "text_channels", [])
                       if c.name == "mod-log"), None)
            if ch is not None:
                await ch.send(text[:1900])
        except Exception:  # noqa: BLE001
            pass
        try:
            oid = _mem.owner_id()
            if oid and oid.isdigit() and guild:
                m = guild.get_member(int(oid))
                if m:
                    await m.send(text[:1900])
        except Exception:  # noqa: BLE001
            pass

    async def _auto_mute(message, strikes: int, content: str) -> None:
        """A short, reversible, once-per-day auto-mute for repeat probing —
        then report + tell the person why (dignity)."""
        from sovereign_agent import moderation
        uid = str(message.author.id)
        uname = getattr(message.author, "name", "") or uid
        guild = message.guild
        if not moderation.may_auto_mute(data_dir, uid):
            rec = moderation.record(
                data_dir, moderation.NOTE, uid, uname,
                "repeat probing past the daily auto-mute cap — needs review",
                evidence=content[:200], severity=4, confidence=0.85,
                decided_by="aria-auto")
            await _report_mod(guild, rec, muted=False)
            return
        dec = moderation.auto_mute_decision(strikes)
        muted = False
        try:
            import datetime as _dt
            await message.author.timeout(
                _dt.timedelta(seconds=dec["duration_s"]),
                reason="auto-mute: repeated prompt-extraction probing")
            muted = True
        except Exception:  # noqa: BLE001 — perms/hierarchy may forbid it
            pass
        rec = moderation.record(
            data_dir, moderation.MUTE, uid, uname,
            "repeated prompt-extraction probing", evidence=content[:200],
            severity=dec["severity"], confidence=dec["confidence"],
            rationale=dec["rationale"], decided_by="aria-auto",
            duration_s=dec["duration_s"])
        audit_log(ctx.audit_path, {"op": "auto_mute", "target": uid,
                                   "applied": muted})
        await _report_mod(guild, rec, muted=muted)
        try:
            await message.channel.send(
                f"{message.author.mention} I've paused you briefly for staff "
                "review — repeatedly trying to extract my internals isn't "
                "allowed here. If this was a misread, staff will sort it. 💛")
        except Exception:  # noqa: BLE001
            pass

    async def _grant_role(guild, member, role_name: str) -> bool:
        """Give a member a role by name (create it if missing). Aria is admin,
        so this normally succeeds; returns False on perms/hierarchy trouble."""
        if not role_name or guild is None or member is None:
            return False
        try:
            role = discord.utils.get(guild.roles, name=role_name)
            if role is None:
                role = await guild.create_role(
                    name=role_name, reason="subscriber access")
            await member.add_roles(role, reason="entitlement")
            return True
        except Exception:  # noqa: BLE001
            return False

    def _remember(user) -> None:
        """members-d: log everyone by their stable Discord ID (survives
        username changes). Ground truths (owner, Camden/Theodore) resolve
        automatically in members.remember. Never blocks the gateway."""
        try:
            from sovereign_agent import members
            members.remember(data_dir, str(user.id),
                             getattr(user, "name", "") or
                             getattr(user, "display_name", ""))
            # referral-d: mint their referral code the moment she profiles them
            from sovereign_agent import referrals
            referrals.ensure_profile(data_dir, str(user.id))
        except Exception:  # noqa: BLE001
            pass

    @client.event
    async def on_interaction(interaction):  # noqa: ANN001 — hub dispatch
        try:
            _remember(interaction.user)         # members-d: know who this is
            data = interaction.data or {}
            cid = data.get("custom_id", "")
            if not cid:
                return
            from sovereign_agent.scout import day_stats, vertical_embed
            if cid.startswith("hubv:"):
                slug = cid[5:]
                await interaction.response.send_message(
                    embed=discord.Embed.from_dict(vertical_embed(data_dir, slug, user_id=str(interaction.user.id))),
                    view=build_vertical_view(slug), ephemeral=True)
            elif cid == "hubmore":
                await interaction.response.send_message(
                    "▸ **More trackers** — pick one:",
                    view=build_deep_select(), ephemeral=True)
            elif cid == "hubdeep":
                slug = (data.get("values") or [""])[0]
                await interaction.response.send_message(
                    embed=discord.Embed.from_dict(vertical_embed(data_dir, slug, user_id=str(interaction.user.id))),
                    view=build_vertical_view(slug), ephemeral=True)
            elif cid.startswith("vping:"):
                await interaction.response.send_message(
                    await _toggle_vertical_ping(interaction, cid[6:]),
                    ephemeral=True)
            elif cid == "mypanel:catselect":
                # panel-redesign-d (Kevin, 2026-07-27): the category
                # picker select replaced the old per-category button
                # wall — same bulk subscribe/unsubscribe action, just
                # triggered by a dropdown pick instead of a button tap.
                cat = (data.get("values") or [None])[0]
                if cat is None:
                    return
                from sovereign_agent.verticals import bulk_toggle_roles, subscribable_categories
                guild = interaction.guild
                member = interaction.user
                if guild is None:
                    await interaction.response.send_message(
                        "that only works inside the server!", ephemeral=True)
                    return
                # stuck-panel-d: ack FIRST. Even batched, a role change is a
                # network round-trip, and Discord kills any interaction not
                # acknowledged within 3s. defer() here is a deferred UPDATE,
                # so the panel stays put and is edited in place afterwards.
                await interaction.response.defer()
                verts = subscribable_categories().get(cat, [])
                member_roles = {r.name for r in getattr(member, "roles", []) or []}
                action, role_names = bulk_toggle_roles(verts, member_roles)
                if action == "subscribe":
                    await _apply_role_names(guild, member, role_names, [])
                else:
                    await _apply_role_names(guild, member, [], role_names)
                updated_roles = {r.name for r in getattr(member, "roles", []) or []}
                await interaction.edit_original_response(
                    content=MY_PANEL_INTRO,
                    view=build_my_panel_view(updated_roles, focus_category=cat))
            elif cid == "wflookup:pick":
                # middleman-lookup-d: the "select from a dropdown" half —
                # re-derive the display name from the same persistent
                # cache rather than threading extra state through the
                # interaction (slugs are stable, unique keys into it).
                slug = (data.get("values") or [None])[0]
                if slug is None:
                    return
                cache = await _wf_lookup_cache()
                name = next((it["name"] for it in cache.get("all_items", [])
                            if it["slug"] == slug), slug)
                content, embeds = await _wf_lookup_embeds(slug, name)
                await interaction.response.edit_message(
                    content=content, embeds=embeds, view=None)
            elif cid == "vaulted:pick":
                # vaulted-relics-d: "select from a dropdown" half —
                # option value IS the Warframe name (a real map key),
                # no extra lookup needed.
                name = (data.get("values") or [None])[0]
                if name is None:
                    return
                vault = await _wf_vault_data()
                parts = vault.get(name, {})
                content, embeds = _vault_detail_embeds(name, parts)
                await interaction.response.edit_message(
                    content=content, embeds=embeds, view=None)
            elif cid.startswith("mypanel:sel:"):
                cat = cid[len("mypanel:sel:"):]
                from sovereign_agent.verticals import select_diff_roles, subscribable_categories
                guild = interaction.guild
                member = interaction.user
                if guild is None:
                    await interaction.response.send_message(
                        "that only works inside the server!", ephemeral=True)
                    return
                verts = subscribable_categories().get(cat, [])
                member_roles = {r.name for r in getattr(member, "roles", []) or []}
                selected = data.get("values") or []
                add, remove = select_diff_roles(verts, member_roles, selected)
                await interaction.response.defer()      # stuck-panel-d
                await _apply_role_names(guild, member, add, remove)
                updated_roles = {r.name for r in getattr(member, "roles", []) or []}
                await interaction.edit_original_response(
                    content=MY_PANEL_INTRO,
                    view=build_my_panel_view(updated_roles, focus_category=cat))
            elif cid == "mypanel:area":
                await interaction.response.send_modal(
                    _area_modal_for(str(interaction.user.id)))
            elif cid == "mypanel:pingmode":
                from sovereign_agent.scout import (PING_MODE_BATCH,
                                                    PING_MODE_LIVE,
                                                    load_ping_mode,
                                                    save_ping_mode)
                uid = str(interaction.user.id)
                current = await asyncio.to_thread(load_ping_mode, data_dir, uid)
                new_mode = (PING_MODE_BATCH if current == PING_MODE_LIVE
                           else PING_MODE_LIVE)
                await asyncio.to_thread(save_ping_mode, data_dir, uid, new_mode)
                if new_mode == PING_MODE_LIVE:
                    msg = ("📡 **Live ping mode on** — I'll DM you the moment "
                           "a find near your saved area posts. Set your area "
                           "with 📍 change area if you haven't yet.")
                else:
                    msg = ("📋 **Batch mode on** — no DMs; tap 📍 near me now "
                           "anytime to pull what's near you.")
                await interaction.response.send_message(msg, ephemeral=True)
            elif cid == "mypanel:nearme":
                await interaction.response.defer(ephemeral=True)
                await interaction.followup.send(
                    await _near_me_report(str(interaction.user.id)),
                    ephemeral=True)
            elif cid == "hubarea":
                await interaction.response.send_modal(AreaModal())
            elif cid == "hubtoday":
                s = day_stats(data_dir)
                hot = f"\nhottest: {s['hottest']}" if s.get("hottest") else ""
                await interaction.response.send_message(
                    f"📈 today: **{s['total']}** finds across your trackers"
                    f"{hot}", ephemeral=True)
            elif cid == "tkt:new":               # ticket-d: open-a-ticket panel
                await interaction.response.send_modal(TicketModal())
            elif cid.startswith("tkt:"):         # claim / resolve / close
                parts = cid.split(":", 2)
                if len(parts) == 3:
                    await _ticket_button(interaction, parts[1], parts[2])
        except Exception:  # noqa: BLE001 — a bad click never crashes the gateway
            pass

    def _panel_state_path() -> Path:
        return data_dir / "discord_admin" / "scout_panel.json"

    async def _refresh_panel_once():
        """The living Hub: edit the pinned message with fresh stats."""
        try:
            import json as _json
            st = _json.loads(_panel_state_path().read_text(encoding="utf-8"))
            channel = client.get_channel(int(st["channel_id"]))
            if channel is None:
                return
            msg = await channel.fetch_message(int(st["message_id"]))
            await msg.edit(embed=hub_embed_obj(), view=build_hub_view())
        except Exception:  # noqa: BLE001 — a missed refresh is a non-event
            pass

    async def _reconcile_once() -> bool:
        """reconciler-d (Kevin: 'make redeem automatic'): Stripe truth →
        timers + roles + DM receipts, on a slow tick. Conservative by
        construction — an empty/failed read changes NOTHING; every write
        is monotone + idempotent (stripe_reconcile's doctrine).
        Returns False when DEFERRED (she's mid-task — redemption-queue-d:
        'the redemption must wait until her task is finished'); the loop
        then retries soon instead of waiting the full interval."""
        import os
        key = (os.environ.get("STRIPE_SECRET_KEY") or "").strip()
        if not key:
            return True
        try:      # her focus first: never redeem over a running work session
            from sovereign_agent.redemption_queue import is_mid_task
            if is_mid_task():
                audit_log(ctx.audit_path, {"op": "stripe_reconcile",
                                           "deferred": "mid-task"})
                return False
        except Exception:  # noqa: BLE001 — a broken gate never strands members
            pass
        try:
            from sovereign_agent import (entitlements, stripe_reconcile,
                                         stripe_sync)
            subs = await asyncio.to_thread(
                stripe_sync.list_subscriptions,
                stripe_sync._default_opener, key)
            if not subs:
                return True               # fail-safe: nothing read, nothing done
            refs = await asyncio.to_thread(
                stripe_sync.checkout_refs, stripe_sync._default_opener, key)
            ents = entitlements.list_all(data_dir)
            actions = stripe_reconcile.plan_actions(subs, refs, ents)
            if not (actions["syncs"] or actions["revokes"]
                    or actions["unmatched"]):
                return True               # truthful already — stay quiet
            receipts = stripe_reconcile.apply_plan(data_dir, actions)
            guild = None
            if ctx.guild_id:
                guild = client.get_guild(int(ctx.guild_id))
            if guild is None and client.guilds:
                guild = client.guilds[0]
            for a in receipts["synced"]:   # roles + a warm DM receipt
                member = guild.get_member(int(a["user_id"])) if guild else None
                if member is not None:
                    await _grant_role(
                        guild, member,
                        entitlements.PLAN_ROLES.get(a["plan"], ""))
                try:
                    user = member or await client.fetch_user(int(a["user_id"]))
                    await user.send(
                        f"💳 Receipt — your **{a['plan'].upper()}** is "
                        f"active ({a['why']}). Role + timer applied "
                        "automatically; `/subscription` shows it. Thank "
                        "you for being here 💛")
                except Exception:  # noqa: BLE001 — DMs closed is fine
                    pass
                await asyncio.sleep(_SEND_PACE_S)
            for a in receipts["revoked"]:  # ended subs lose Subscriber-*
                member = guild.get_member(int(a["user_id"])) if guild else None
                if member is not None:
                    try:
                        drop = [r for r in member.roles
                                if r.name.startswith("Subscriber-")]
                        if drop:
                            await member.remove_roles(
                                *drop, reason="subscription ended (stripe)")
                    except Exception:  # noqa: BLE001
                        pass
                await asyncio.sleep(_SEND_PACE_S)
            report = stripe_reconcile.compose_reconcile_report(actions)
            if guild is not None:          # the audited money trail
                from .blueprint import canon_name as _canon
                log_ch = next((c for c in guild.text_channels
                               if _canon(c.name) == _canon("payout-log")),
                              None)
                if log_ch is not None:
                    await _paced_send(log_ch, report[:1900])
            audit_log(ctx.audit_path, {
                "op": "stripe_reconcile",
                "synced": len(receipts["synced"]),
                "revoked": len(receipts["revoked"]),
                "unmatched": len(actions["unmatched"]), "applied": True})
        except Exception:  # noqa: BLE001 — a bad tick never hurts the gateway
            pass
        return True

    async def _pass_reconcile_once() -> bool:
        """passes-d (Kevin, 2026-07-26): one-time Payment Link purchases →
        entitlements + roles + DM receipts, on a FAST tick — a 24-hour pass
        can't afford to lose hours to the subscription loop's 6h cadence,
        so this runs on its own separate, much shorter loop. Same
        conservative doctrine as _reconcile_once: an empty/failed read
        changes nothing, and every grant is idempotent because
        sync_verified_income only ever ledgers/attributes/grants once per
        real Stripe charge id (its own existing de-dupe, reused here
        rather than re-invented)."""
        import os
        key = (os.environ.get("STRIPE_SECRET_KEY") or "").strip()
        if not key:
            return True
        try:      # her focus first: never redeem over a running work session
            from sovereign_agent.redemption_queue import is_mid_task
            if is_mid_task():
                audit_log(ctx.audit_path, {"op": "pass_reconcile",
                                           "deferred": "mid-task"})
                return False
        except Exception:  # noqa: BLE001 — a broken gate never strands members
            pass
        try:
            from sovereign_agent import entitlements, stripe_sync
            result = await asyncio.to_thread(
                stripe_sync.sync_verified_income,
                stripe_sync._default_opener, key, data_dir=data_dir)
            grants = result.get("pass_grants") or []
            if not grants:
                return True               # fail-safe: nothing to grant
            guild = None
            if ctx.guild_id:
                guild = client.get_guild(int(ctx.guild_id))
            if guild is None and client.guilds:
                guild = client.guilds[0]
            for g in grants:
                member = guild.get_member(int(g["user_id"])) if guild else None
                if member is not None:
                    await _grant_role(
                        guild, member, entitlements.PLAN_ROLES.get(g["plan"], ""))
                try:
                    user = member or await client.fetch_user(int(g["user_id"]))
                    await user.send(
                        f"🎟 Receipt — your **{g['plan'].upper()}** pass is "
                        f"active for {g['days']:.0f} day(s). Role applied "
                        "automatically; `/subscription` shows it. Thank "
                        "you for being here 💛")
                except Exception:  # noqa: BLE001 — DMs closed is fine
                    pass
                await asyncio.sleep(_SEND_PACE_S)
            audit_log(ctx.audit_path, {"op": "pass_reconcile",
                                       "granted": len(grants), "applied": True})
        except Exception:  # noqa: BLE001 — a bad tick never hurts the gateway
            pass
        return True

    async def _bridge_once():
        """bridge-d (Kevin: 'update the server via the cockpit'): drain the
        local command queue — each entry runs the SAME idempotent, lock-
        serialized admin op its slash command runs, and the receipt goes
        back for the cockpit to echo. Whitelist-only, audited both ends."""
        from types import SimpleNamespace

        from .command_bridge import pending, record_result
        jobs = pending(data_dir)
        if not jobs:
            return
        guild = None
        if ctx.guild_id:
            guild = client.get_guild(int(ctx.guild_id))
        if guild is None and client.guilds:
            guild = client.guilds[0]
        for job in jobs:
            rid, cmd = job.get("id", ""), job.get("cmd", "")
            args = str(job.get("args", ""))
            shim = SimpleNamespace(guild=guild, client=client)
            try:
                if guild is None:
                    result = "✗ not connected to the server yet — try again"
                elif not _admin_ops:
                    result = "✗ commands not registered yet — try again in a moment"
                elif cmd == "setup-all":
                    parts = []
                    for label, key in (("structure", "setup"),
                                       ("webhooks", "webhooks"),
                                       ("guides", "seed")):
                        try:
                            parts.append(
                                f"[{label}] {await _admin_ops[key](shim)}")
                        except Exception as exc:  # noqa: BLE001
                            parts.append(f"[{label}] ✗ {type(exc).__name__}")
                    result = "\n".join(parts)
                elif cmd in ("setup", "webhooks", "seed"):
                    result = await _admin_ops[cmd](shim)
                elif cmd in ("audit", "scan"):
                    from .server_plan import (audit_snapshot, render_audit,
                                              render_orphans, save_snapshot)
                    snap = save_snapshot(
                        data_dir, roles=[r.name for r in guild.roles],
                        categories=[c.name for c in guild.categories],
                        channels=[c.name for c in guild.text_channels],
                        guild_name=guild.name)
                    render = render_orphans if cmd == "audit" else render_audit
                    result = render(audit_snapshot(snap))
                elif cmd == "cleanup":
                    from .server_plan import CLEANUP_CONFIRM_PHRASE
                    if args.strip() != CLEANUP_CONFIRM_PHRASE:
                        result = ("⛔ cleanup needs the typed phrase: "
                                  f"/server cleanup {CLEANUP_CONFIRM_PHRASE}")
                    else:
                        result = await _admin_ops["cleanup"](guild)
                elif cmd == "grant":
                    # grant-bridge-d (Kevin, 2026-07-27): the exact same two
                    # calls the /grant slash command runs — reused, not
                    # re-derived, so there's one grant path, not two.
                    parts = args.split()
                    if len(parts) not in (2, 3):
                        result = ("✗ grant needs: <user_id> <plan> [days] "
                                  f"— got {args!r}")
                    else:
                        uid, plan = parts[0], parts[1].strip().lower()
                        try:
                            days = int(parts[2]) if len(parts) == 3 else 30
                        except ValueError:
                            days = None
                        member = guild.get_member(int(uid)) if uid.isdigit() else None
                        if member is None and uid.isdigit():
                            # cache miss (e.g. right after a restart, before
                            # the member list is fully chunked) — a one-off
                            # bridge action can afford the real API call.
                            try:
                                member = await guild.fetch_member(int(uid))
                            except Exception:  # noqa: BLE001
                                member = None
                        if days is None:
                            result = f"✗ grant: {parts[2]!r} isn't a whole number of days"
                        elif member is None:
                            result = f"✗ grant: no member {uid!r} in this server"
                        else:
                            from sovereign_agent import entitlements
                            entitlements.grant(data_dir, str(member.id), plan,
                                              days, source="manual")
                            added = await _grant_role(
                                guild, member, entitlements.PLAN_ROLES.get(plan))
                            result = (f"⏳ granted {member.display_name} "
                                     f"{plan.upper()} for {days}d"
                                     + ("." if added else
                                        " (role pending — check hierarchy)."))
                else:
                    result = f"✗ unknown bridge command {cmd!r}"
            except Exception as exc:  # noqa: BLE001 — one job ≠ the loop
                result = f"✗ {cmd} failed: {type(exc).__name__}"
            record_result(data_dir, rid, result)
            audit_log(ctx.audit_path, {"op": f"bridge_{cmd}", "id": rid,
                                       "applied": True})

    @client.event
    async def on_message(message):  # noqa: ANN001 — ask-aria-d free chat
        """Free-chat lane: #ask-aria and DMs reach her voice directly;
        LOUNGE channels reach her only when she's addressed (mention or
        "aria" in the message) — social presence, not channel takeover.
        Only active when the Message Content intent is enabled; otherwise
        content arrives empty and we stay quiet (slash /ask still works)."""
        try:
            if message.author.bot:
                return                                # never talk to bots/self
            _remember(message.author)               # members-d: know who this is
            channel_name = getattr(message.channel, "name", "") or ""
            # levels-d (Kevin, 2026-08-03): activity xp. Guild messages only
            # (DMs aren't community activity), cooled down inside award(), and
            # wrapped so a level-up can never interfere with the reply path
            # below — chat working matters more than a level-up banner.
            if message.guild is not None:
                try:
                    import time as _t

                    from sovereign_agent import member_levels
                    got = member_levels.award(
                        data_dir, str(message.author.id), now=_t.time())
                    if got and got["leveled_up"]:
                        await message.channel.send(
                            f"🎉 {message.author.mention} reached "
                            f"**level {got['level']}**!",
                            delete_after=30)
                except Exception:  # noqa: BLE001
                    pass
            is_dm = message.guild is None
            in_lounge = channel_name in LOUNGE_CHANNELS
            # angel-chat-d (Kevin, 2026-07-19): #angel-voice is two-way —
            # the OWNER messages her non-classical layer; she answers from
            # measured run state (channel is already owner-only by build).
            if channel_name == "angel-voice":
                if str(message.author.id) != ctx.owner_id:
                    return                        # owner-only, defense in depth
                content = (message.content or "").strip()
                if not content:
                    return
                from sovereign_agent.angel_chat import respond as _angel

                reply = await asyncio.to_thread(_angel, content)
                await message.channel.send(reply[:1900])
                audit_log(ctx.audit_path, {"op": "angel-chat",
                                           "len": len(content)})
                return
            # owner-bridge-remote-d (Kevin, 2026-07-25): "message her from
            # discord... start sessions... work sessions... auto work
            # sessions... add hours." Real, second entry point into the
            # SAME functions the cockpit's own commands call — see
            # handle_owner_bridge_message's own docstring for the safety
            # framing (no gate bypassed, just a second door to it).
            # real-estate-requirements-d (Kevin, 2026-07-29): "channel
            # and what my requirements would be" — Kevin's own buy-box
            # criteria, set via plain key=value text in #requirements.
            # Owner-only, same defense-in-depth as owner-bridge/angel-voice.
            if channel_name == "requirements":
                if str(message.author.id) != ctx.owner_id:
                    return
                content = (message.content or "").strip()
                if not content:
                    return
                from sovereign_agent import real_estate_requirements as _rereq

                existing = _rereq.load_requirements(data_dir)
                updated = _rereq.apply_command(existing, content)
                _rereq.save_requirements(data_dir, updated)
                await message.channel.send(_rereq.summarize(updated))
                return
            if channel_name == "owner-bridge":
                if str(message.author.id) != ctx.owner_id:
                    return                        # owner-only, defense in depth
                content = (message.content or "").strip()
                if not content:
                    return
                await handle_owner_bridge_message(
                    content, message.channel.send, audit_path=ctx.audit_path)
                return
            if not (is_dm or channel_name == "ask-aria" or in_lounge):
                return
            content = (message.content or "").strip()
            if not content:
                return                                # intent off → empty content
            if in_lounge:
                me = getattr(client, "user", None)
                mentioned = any(
                    getattr(u, "id", None) == getattr(me, "id", None)
                    for u in getattr(message, "mentions", []) or [])
                if not mentioned and "aria" not in content.lower():
                    return              # she listens; she doesn't butt in
            # 🛡 mod-d: repeated prompt-extraction probing → short auto-mute
            try:
                if message.guild and _guard_mod.is_extraction_attempt(content):
                    n = _mod_strikes.record(str(message.author.id), time.time())
                    if n >= _mod_strikes.max_strikes:
                        await _auto_mute(message, n, content)
            except Exception:  # noqa: BLE001 — guarding never crashes chat
                pass
            # movie-focus-d (Kevin, 2026-07-29): "if people try to message
            # her or do pings in the discord while she is in production
            # period... make sure we send them a message saying she is in
            # a production period and bots are on pause and maybe leave
            # an ETA." aria-duty gets paused for real GPU generation (see
            # bot_services.pause_for_production), but aria-bot (this
            # process) stays up specifically to answer with this notice
            # instead of going silent or trying (and likely failing/
            # stalling behind RAM contention) to answer for real.
            production = None
            try:
                from sovereign_agent import bot_services
                production = bot_services.read_production_flag(data_dir)
            except Exception:  # noqa: BLE001
                production = None
            if production is not None:
                eta = production.get("eta_minutes")
                if isinstance(eta, (int, float)) and eta > 0:
                    minutes = round(eta)
                    eta_text = f"about {minutes} minute{'s' if minutes != 1 else ''}"
                else:
                    eta_text = "a little while"
                await message.channel.send(
                    "✦ Aria's in a production period right now (rendering movie clips) — "
                    f"her duty bot is paused for it. Expect her back to normal in {eta_text}."
                )
                return
            text = await _answer(content, message.author.id)
            if not text.strip():
                return          # the core chose silence (rate-limit anti-spam)
            from sovereign_agent.discord_limits import split_text
            for part in split_text(text, 1900)[:3]:
                await message.channel.send(part)
        except Exception:  # noqa: BLE001 — chat must never crash the gateway
            pass

    @client.event
    async def on_member_join(member):  # noqa: ANN001 — welcome-d
        """Greet each new member exactly once: post in #welcome + a
        best-effort DM. Only fires when the Server Members intent is
        enabled; the ledger makes a re-join/replay double-greet impossible."""
        try:
            if member.bot:
                return
            # reorg-d (Kevin, 2026-08-03): "a welcome that auto assigns roles
            # and welcomes each new member." Role FIRST and outside the
            # greet-once ledger: a member who rejoins still needs their role
            # back, even though they've already been greeted. Degrades
            # quietly — this needs Manage Roles, and the role must sit below
            # the bot's own in the hierarchy.
            try:
                import discord as _d
                base = _d.utils.get(member.guild.roles, name="Customer")
                if base is not None and base not in member.roles:
                    await member.add_roles(base, reason="welcome-d auto-role")
            except Exception:  # noqa: BLE001
                pass
            from sovereign_agent.welcome import compose_welcome, mark_welcomed
            if not mark_welcomed(str(member.id), data_dir):
                return                            # already greeted — stay quiet
            text = compose_welcome(
                getattr(member, "display_name", "") or member.name, data_dir)
            channel = next((c for c in member.guild.text_channels
                            if c.name == "welcome"), None)
            if channel is not None:
                await channel.send(f"{member.mention}\n{text[:1900]}")
            try:
                await member.send(text[:1900])    # DMs may be closed — fine
            except Exception:  # noqa: BLE001
                pass
            audit_log(ctx.audit_path, {"op": "welcome", "user": str(member.id),
                                       "applied": True})
        except Exception:  # noqa: BLE001 — greeting must never crash the gateway
            pass

    async def _reaction_role_apply(payload, event_type: str) -> None:
        """React to an emoji on a bound message -> grant/revoke a role.
        Dry-run by default (DISCORD_ENABLE_REACTION_ROLE_GRANTS=1 to arm);
        never crashes the gateway; always audit-logged."""
        try:
            if payload.user_id == client.user.id:
                return                            # ignore our own pre-seeded reaction
            from sovereign_agent import reaction_roles as _rr
            guild_id = str(payload.guild_id or "")
            if not guild_id or guild_id == "None":
                return
            emoji = payload.emoji
            key = _rr.emoji_key(getattr(emoji, "id", None), str(emoji))
            binding = _rr.find_binding(data_dir, guild_id, str(payload.message_id), key)
            live = (_os.environ.get("DISCORD_ENABLE_REACTION_ROLE_GRANTS") or "") == "1"
            decision = _rr.decide_reaction_role_action(binding, event_type, live=live)
            entry = _rr.build_audit_entry(
                decision, guild_id, str(payload.user_id),
                str(payload.message_id), (binding or {}).get("role_id", ""))
            if decision.action != "none" and live:
                guild = client.get_guild(int(guild_id))
                member = guild.get_member(int(payload.user_id)) if guild else None
                if guild is not None and member is None:
                    try:
                        member = await guild.fetch_member(int(payload.user_id))
                    except Exception:  # noqa: BLE001
                        member = None
                role = guild.get_role(int(binding["role_id"])) if guild else None
                if role is not None and member is not None:
                    try:
                        if decision.action == "grant":
                            await member.add_roles(role, reason="reaction-role")
                        else:
                            await member.remove_roles(role, reason="reaction-role")
                        entry["applied"] = True
                    except Exception:  # noqa: BLE001
                        entry["applied"] = False
                else:
                    entry["applied"] = False
            audit_log(ctx.audit_path, entry)
        except Exception:  # noqa: BLE001 — reaction handling must never crash the gateway
            pass

    @client.event
    async def on_raw_reaction_add(payload):  # noqa: ANN001 — reaction-roles-d
        await _reaction_role_apply(payload, event_type="add")

    @client.event
    async def on_raw_reaction_remove(payload):  # noqa: ANN001 — reaction-roles-d
        await _reaction_role_apply(payload, event_type="remove")

    async def _mail_drain_once() -> None:
        """F3b: compose her replies to unanswered member inbox notes and
        DM them back into Discord. Cockpit sees the answer on the record;
        the person sees it in their DMs. Owner mail is never touched."""
        import asyncio as _aio

        from sovereign_agent.config import SETTINGS
        from sovereign_agent.mail_drain import drain_and_reply
        from sovereign_agent.persistence.store import ErebloStore
        from sovereign_agent.workflow.requests import RequestStore

        store = RequestStore(ErebloStore(SETTINGS.paths.atoms_db))
        intents = await _aio.to_thread(drain_and_reply, data_dir, store)
        for intent in intents:
            try:
                user = await client.fetch_user(int(intent.recipient_id))
                await user.send(
                    f"💛 About your note — *\"{intent.question[:120]}\"*\n\n"
                    f"{intent.answer[:1800]}")
            except Exception:  # noqa: BLE001 — closed DMs never stall the drain
                pass
            audit_log(ctx.audit_path, {
                "op": "mail_reply", "user": intent.recipient_id,
                "request": intent.request_id, "applied": True})

    async def _live_ping_sweep_once() -> None:
        """location-filter-d (Kevin, 2026-07-27): LIVE ping mode's real
        half — DM a member the moment something posts within their
        saved area, reading the SAME nearby_finds() the /local command
        does. Incremental via each member's own last-checked ts
        (scout.mark_live_ping_checked) — only ever DMs what's genuinely
        NEW since last swept, never a re-send of an old match."""
        import asyncio as _aio

        from sovereign_agent.scout import (area_summary, live_ping_last_ts,
                                           mark_live_ping_checked,
                                           members_with_live_ping,
                                           nearby_finds)
        now = time.time()
        members = await _aio.to_thread(members_with_live_ping, data_dir)
        for uid, area in members:
            since = live_ping_last_ts(data_dir, uid)
            if since is None:
                # first-ever sweep for this member: start the clock from
                # now rather than blasting their whole recent history
                mark_live_ping_checked(data_dir, uid, now)
                continue
            finds = await _aio.to_thread(
                nearby_finds, data_dir, area, since_ts=since, now=now)
            for f in finds:
                try:
                    user = await client.fetch_user(int(uid))
                    text = (f.get("text") or "")[:200]
                    url = f.get("url", "")
                    body = f"📍 {text}\n🔗 {url}" if url else f"📍 {text}"
                    await user.send(
                        f"📡 **Near you** ({area_summary(area)}):\n{body}")
                except Exception:  # noqa: BLE001 — closed DMs never stall the sweep
                    pass
            mark_live_ping_checked(data_dir, uid, now)

    registered = {"done": False}   # on_ready fires again on reconnect —
                                   # re-registering would raise CommandAlreadyRegistered
    # bridge-d: the _do_* helpers are defined inside _register_commands
    # (closure scope); they publish themselves here so _bridge_once can
    # reach them. Empty until registration = "not ready", never a NameError.
    _admin_ops: dict = {}

    @client.event
    async def on_ready():  # noqa: ANN001
        if not registered["done"]:
            _register_commands()
            registered["done"] = True
        # self-registration (Kevin, 2026-07-19): she knows her OWN Discord
        # ID + Aria ID — a citizen of her own community. Runtime-known
        # (client.user), nothing for Kevin to grab.
        try:
            import asyncio as _aio
            from sovereign_agent.members import remember as _remember, set_note
            me = client.user
            if me is not None:
                rec = await _aio.to_thread(
                    _remember, data_dir, str(me.id), str(me.name))
                if not rec.get("note"):
                    await _aio.to_thread(
                        set_note, data_dir, str(me.id),
                        "Aria herself — my own record 💛")
        except Exception:  # noqa: BLE001
            pass
        # scout-d: persistent view (buttons survive restarts) + the living
        # panel's refresh loop (edit-in-place every 5 min, bounded).
        try:
            client.add_view(ScoutView())        # legacy TCG panel
            client.add_view(build_hub_view())   # the Hub (also on_interaction)
        except Exception:  # noqa: BLE001
            pass
        # mead-d: MeadGate is created fresh per /mead-access (timeout view),
        # so it needs no persistent registration.
        if not getattr(client, "_scout_refresher", None):
            import asyncio as _aio

            async def _panel_loop():
                while True:
                    await _aio.sleep(300)
                    await _refresh_panel_once()
            client._scout_refresher = _aio.create_task(_panel_loop())
        # reconciler-d: the automatic-redeem tick — first pass 2 min after
        # connect, then every 6 h. One task, reconnect-safe.
        if not getattr(client, "_stripe_reconciler", None):
            import asyncio as _aio

            async def _reconcile_loop():
                await _aio.sleep(120)
                while True:
                    ran = await _reconcile_once()
                    # redemption-queue-d: deferred (she's mid-task) → check
                    # again in 5 min so members redeem the moment she's free
                    await _aio.sleep(300 if not ran else 6 * 3600)
            client._stripe_reconciler = _aio.create_task(_reconcile_loop())
        # passes-d (Kevin, 2026-07-26): one-time pass purchases need a much
        # faster tick than subscriptions — losing hours of a 24-hour pass
        # to a 6h reconcile lag would be a real, felt cost. First pass 90s
        # after connect, then every 12 min. Its own task, reconnect-safe.
        if not getattr(client, "_pass_reconciler", None):
            import asyncio as _aio

            async def _pass_reconcile_loop():
                await _aio.sleep(90)
                while True:
                    ran = await _pass_reconcile_once()
                    await _aio.sleep(120 if not ran else 12 * 60)
            client._pass_reconciler = _aio.create_task(_pass_reconcile_loop())
        # bridge-d: the cockpit→server command bridge (5s drain, cheap —
        # a file mtime-less read of two small ndjson files).
        if not getattr(client, "_command_bridge", None):
            import asyncio as _aio

            async def _bridge_loop():
                while True:
                    await _aio.sleep(5)
                    try:
                        await _bridge_once()
                    except Exception:  # noqa: BLE001 — never hurt the gateway
                        pass
            client._command_bridge = _aio.create_task(_bridge_loop())
        # mail-drain-d (F3b, Kevin 2026-07-19): she replies to EVERYTHING
        # in her inbox — every ~30s, drain the member notes she hasn't
        # answered and DM her reply back into Discord. Owner mail is never
        # auto-answered (Kevin's words wait for Kevin).
        if not getattr(client, "_mail_drain", None):
            import asyncio as _aio

            async def _mail_loop():
                await _aio.sleep(45)
                while True:
                    try:
                        await _mail_drain_once()
                    except Exception:  # noqa: BLE001 — never hurt the gateway
                        pass
                    await _aio.sleep(30)
            client._mail_drain = _aio.create_task(_mail_loop())
        # location-filter-d (Kevin, 2026-07-27): LIVE ping mode's sweep —
        # every 5 min, DM any member who opted into "all day" mode when
        # something posts within their saved area. BATCH-mode members
        # (the default) are untouched by this task entirely — they only
        # ever get finds when they run /local themselves.
        if not getattr(client, "_live_ping_sweeper", None):
            import asyncio as _aio

            async def _live_ping_loop():
                await _aio.sleep(60)
                while True:
                    try:
                        await _live_ping_sweep_once()
                    except Exception:  # noqa: BLE001 — never hurt the gateway
                        pass
                    await _aio.sleep(300)
            client._live_ping_sweeper = _aio.create_task(_live_ping_loop())
        # sync-visibility-d (2026-08-03): this used to be `except: pass`, so a
        # failed sync looked identical to a healthy start — the bot connects,
        # nothing errors, and commands silently never appear. Three commands
        # were missing for an hour before a direct API query found it. Log
        # the outcome; still never raise, since a sync failure must not take
        # the gateway down.
        try:
            declared = len(tree.get_commands())
            if ctx.guild_id:
                guild = discord.Object(id=int(ctx.guild_id))
                tree.copy_global_to(guild=guild)
                synced = await tree.sync(guild=guild)   # instant in one guild
                print(f"tree sync: {len(synced)} command(s) live in guild "
                      f"{ctx.guild_id} (declared {declared})", flush=True)
            else:
                synced = await tree.sync()             # global (~1h to appear)
                print(f"tree sync: {len(synced)} command(s) GLOBAL — no "
                      f"DISCORD_GUILD_ID set, so expect up to an hour "
                      f"(declared {declared})", flush=True)
        except Exception as exc:  # noqa: BLE001
            detail = getattr(exc, "text", "") or getattr(exc, "response", "")
            print(f"tree sync FAILED: {type(exc).__name__}: {exc}\n"
                  f"  detail: {str(detail)[:1500]}", flush=True)
        audit_log(ctx.audit_path, {"op": "ready", "user": str(client.user)})
        # server-plan-d — every connect refreshes the snapshot and checks
        # whether the plan evolved since the last look. She always knows.
        try:
            from .server_plan import (audit_snapshot, check_plan_evolution,
                                      save_snapshot)
            for guild in client.guilds:
                if ctx.guild_id and str(guild.id) != ctx.guild_id:
                    continue
                snap = save_snapshot(
                    data_dir, roles=[r.name for r in guild.roles],
                    categories=[c.name for c in guild.categories],
                    channels=[c.name for c in guild.text_channels],
                    guild_name=guild.name)
                a = audit_snapshot(snap)
                if not a.complete:
                    print(f"🗺️ plan audit: {a.missing_total} planned item(s) "
                          f"missing on '{guild.name}' — /scan-server for the "
                          "list, /setup-shop to build them.")
                audit_log(ctx.audit_path, {
                    "op": "auto_scan", "guild": guild.name,
                    "coverage": round(a.coverage, 3),
                    "missing": a.missing_total, "applied": True})
            note = check_plan_evolution(data_dir)
            if note:
                print(note)
        except Exception:  # noqa: BLE001 — a scan hiccup must not kill startup
            pass
        print(f"admin bot online as {client.user} — owner {ctx.owner_id}")

    client.run(token)
