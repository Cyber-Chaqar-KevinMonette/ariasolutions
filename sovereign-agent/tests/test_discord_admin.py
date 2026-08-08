"""Tests for discord_admin — blueprint, idempotent create-only planner, gate."""
from __future__ import annotations

from sovereign_agent.discord_admin.blueprint import SEND, VIEW, shop_blueprint
from sovereign_agent.discord_admin.gate import (
    DESTRUCTIVE_OPS,
    GateResult,
    check_command,
    is_destructive,
    is_owner,
    needs_confirmation,
)
from sovereign_agent.discord_admin.planner import Action, CurrentState, plan, render_plan


# ── blueprint ───────────────────────────────────────────────────────────────
def test_blueprint_matches_the_server():
    bp = shop_blueprint()
    assert "Subscriber-VIP" in bp.role_names()
    cats = [c.name for c in bp.categories]
    assert cats == [
                    # reorg-d (Kevin, 2026-08-03): ordered how a new member
                    # reads it, with the two private staff categories pinned
                    # above (invisible to members, one scroll for the owner).
                    "ADMIN",   # consolidate-d: BACKEND folded in
                    "WELCOME", "SHOP", "LOUNGE",
                    "SUBSCRIBERS", "MEAD LOUNGE",
                    "WARFRAME",               # warframe-flip-d
                    "OLD SCHOOL RUNESCAPE",   # osrs-flips-d
                    # code-school-d: one private category per
                    # ENABLED track (tracks.ENABLED)
                    "PYTHON", "AI SYSTEMS"]
    assert "storefront" in bp.channel_names() and "aria-control" in bp.channel_names()
    assert "osrs-starter" in bp.channel_names()    # focus-d
    # retirement-d (2026-08-03): COMPUTERS is retired, so #desktop-parts and
    # every other generic-category channel is gone from the blueprint. The
    # OSRS tier channels are the live example of a real, categorised tracker.
    assert "desktop-parts" not in bp.channel_names()
    assert "osrs-starter" in bp.channel_names()
    # mead-d: the lounge is Discord-native age-restricted (18+)
    mead = next(c for c in bp.categories if c.name == "MEAD LOUNGE")
    assert mead.private and all(ch.age_restricted for ch in mead.channels)


def test_subscribers_private_backend_private():
    bp = shop_blueprint()
    subs = next(c for c in bp.categories if c.name == "SUBSCRIBERS")
    assert subs.private and "Subscriber-Basic" in subs.allow_roles


# ── planner: idempotent, create-only ────────────────────────────────────────
def test_plan_on_empty_creates_everything():
    actions = plan(shop_blueprint(), CurrentState())
    ops = [a.op for a in actions]
    assert ops.count("create_role") == 26     # +2 code-school track roles
    assert ops.count("create_category") == 10  # code-school-d
    assert ops.count("create_channel") == 46   # code-school-d
    assert "overwrite" in ops


def test_plan_is_idempotent_skips_existing():
    bp = shop_blueprint()
    current = CurrentState(roles=set(bp.role_names()),
                           categories={c.name for c in bp.categories},
                           channels=set(bp.channel_names()))
    actions = plan(bp, current)
    # nothing to CREATE, but permission overwrites are still (safely) emitted
    assert not any(a.op.startswith("create") for a in actions)
    assert all(a.op == "overwrite" for a in actions)


def test_plan_never_deletes():
    actions = plan(shop_blueprint(), CurrentState())
    assert not any("delete" in a.op for a in actions)


def test_private_category_denies_everyone_allows_roles():
    actions = plan(shop_blueprint(), CurrentState())
    subs = [a for a in actions if a.op == "overwrite" and a.name == "SUBSCRIBERS"]
    everyone = next(a for a in subs if a.params["target"] == "@everyone")
    assert VIEW in everyone.params.get("deny", [])
    roles = {a.params["target"] for a in subs if a.params["target"] != "@everyone"}
    assert {"Subscriber-Basic", "Subscriber-Pro", "Subscriber-VIP"} <= roles


def test_readonly_public_category_allows_view_denies_send():
    actions = plan(shop_blueprint(), CurrentState())
    welcome = next(a for a in actions if a.op == "overwrite" and a.name == "WELCOME"
                   and a.params["target"] == "@everyone")
    assert VIEW in welcome.params["allow"] and SEND in welcome.params["deny"]


def test_channel_overrides_hide_and_open():
    actions = plan(shop_blueprint(), CurrentState())
    # order-here opens send for everyone
    oh = next(a for a in actions if a.op == "overwrite" and a.name == "order-here")
    assert SEND in oh.params["allow"]
    # priority-support hides from Basic; early-access hides from Basic + Pro
    ps = [a for a in actions if a.op == "overwrite" and a.name == "priority-support"]
    assert any("Subscriber-Basic" == a.params["target"] and VIEW in a.params["deny"]
               for a in ps)
    ea = [a.params["target"] for a in actions
          if a.op == "overwrite" and a.name == "early-access"]
    assert "Subscriber-Basic" in ea and "Subscriber-Pro" in ea


# ── subscribe-d: per-channel opt-in role gates tracker channels ────────────
def test_tracker_channel_is_private_with_its_own_subscriber_role():
    bp = shop_blueprint()
    osrs = next(c for c in bp.categories if c.name == "OLD SCHOOL RUNESCAPE")
    starter = next(ch for ch in osrs.channels if ch.name == "osrs-starter")
    assert starter.private is True
    assert starter.allow_roles == ["Track-OsrsStarter"]
    # reorg-d (2026-08-03): TRACKERS and its catch-all are gone — after the
    # focus cut every surviving vertical lives in a named category, so there
    # is no long-tail left for a catch-all to carry.
    assert "TRACKERS" not in [c.name for c in bp.categories]
    assert "track-everything-else" not in bp.channel_names()


def test_every_channeled_vertical_has_a_provisioned_subscriber_role():
    from sovereign_agent.verticals import channeled_verticals
    bp = shop_blueprint()
    role_names = set(bp.role_names())
    for v in channeled_verticals():
        assert v.ping_role in role_names


def test_tracker_channel_overwrite_denies_everyone_allows_its_role():
    actions = plan(shop_blueprint(), CurrentState())
    cards = [a for a in actions if a.op == "overwrite" and a.name == "osrs-starter"]
    everyone = next(a for a in cards if a.params["target"] == "@everyone")
    assert VIEW in everyone.params.get("deny", [])
    roles = {a.params["target"] for a in cards if a.params["target"] != "@everyone"}
    assert "Track-OsrsStarter" in roles
    allow_action = next(a for a in cards if a.params["target"] == "Track-OsrsStarter")
    assert VIEW in allow_action.params.get("allow", [])


def test_render_plan_readable_and_empty():
    assert "already matches" in render_plan([])
    txt = render_plan(plan(shop_blueprint(), CurrentState()))
    assert "to create" in txt and "role" in txt


# ── gate ────────────────────────────────────────────────────────────────────
def test_is_owner_fails_closed():
    assert is_owner("123", "123") is True
    assert is_owner("123", "999") is False
    assert is_owner(None, "123") is False
    assert is_owner("123", None) is False
    assert is_owner("", "") is False           # blank owner trusts nobody


def test_destructive_classification():
    assert is_destructive("delete_channel")
    assert not is_destructive("create_channel")
    assert "wipe_permissions" in DESTRUCTIVE_OPS


def test_needs_confirmation():
    assert needs_confirmation([Action("delete_role", "x")]) is True
    assert needs_confirmation([Action("create_channel", "x")]) is False


def test_check_command_owner_and_confirm():
    assert check_command(user_id="1", owner_id="1", op="create_channel").allowed
    # non-owner refused
    r = check_command(user_id="2", owner_id="1", op="create_channel")
    assert not r.allowed and "owner-only" in r.reason
    # destructive without confirm refused
    r = check_command(user_id="1", owner_id="1", op="delete_channel")
    assert not r.allowed and "destructive" in r.reason
    # destructive with confirm allowed
    assert check_command(user_id="1", owner_id="1", op="delete_channel", confirm=True).allowed


# ── bot pure helpers (no discord.py needed) ─────────────────────────────────
def test_plan_for_guild_pure_helper():
    from sovereign_agent.discord_admin.bot import COMMANDS, plan_for_guild
    # empty guild → full create plan
    acts = plan_for_guild([], [], [])
    assert sum(1 for a in acts if a.op == "create_role") == 26  # +2 school roles
    # a guild that already has everything → no creates
    from sovereign_agent.discord_admin.blueprint import shop_blueprint
    bp = shop_blueprint()
    acts2 = plan_for_guild(bp.role_names(), [c.name for c in bp.categories],
                           bp.channel_names())
    assert not any(a.op.startswith("create") for a in acts2)
    assert len(COMMANDS) >= 6


def test_audit_log_writes(tmp_path):
    from sovereign_agent.discord_admin.bot import audit_log
    p = tmp_path / "sub" / "audit.jsonl"
    audit_log(p, {"op": "setup_shop", "applied": True})
    import json
    rec = json.loads(p.read_text().splitlines()[0])
    assert rec["op"] == "setup_shop" and "ts" in rec


def test_ask_aria_channel_in_blueprint_and_open_for_chat():
    from sovereign_agent.discord_admin.blueprint import SEND, shop_blueprint
    from sovereign_agent.discord_admin.planner import CurrentState, plan
    bp = shop_blueprint()
    assert "ask-aria" in bp.channel_names()
    actions = plan(bp, CurrentState())
    ow = [a for a in actions if a.op == "overwrite" and a.name == "ask-aria"]
    assert any(SEND in a.params.get("allow", []) for a in ow)   # everyone can talk


def test_ask_command_in_catalog():
    from sovereign_agent.discord_admin.bot import COMMANDS
    assert any(n == "/ask" for n, _, _ in COMMANDS)


# ── help-boards-d (Kevin, 2026-07-27): "a help command for admins, for
# subscribers, and for new members... so everyone has their respective
# command boards." COMMANDS had quietly drifted (18 real, registered
# commands were missing) — these guard against that ever going unnoticed
# again, and cover the new audience-tiered panel builder. ──────────────
def test_every_registered_slash_command_is_in_the_catalog():
    """The real, structural regression test: every `@tree.command(name=
    ...)` in bot.py must have a COMMANDS entry. This is what actually
    caught the staleness — 18 commands (grant, refer, ticket, mod-*,
    and more) had silently gone missing from COMMANDS before this."""
    import re
    from pathlib import Path
    from sovereign_agent.discord_admin.bot import COMMANDS
    src = (Path(__file__).parent.parent / "src" / "sovereign_agent"
          / "discord_admin" / "bot.py").read_text(encoding="utf-8")
    registered = set(re.findall(r'@tree\.command\(\s*name="([^"]+)"', src))
    cataloged = {n.lstrip("/") for n, _, _ in COMMANDS}
    missing = registered - cataloged
    assert not missing, f"registered but not in COMMANDS: {sorted(missing)}"


def test_every_catalog_entry_has_a_real_audience_tier():
    from sovereign_agent.discord_admin.bot import COMMANDS, _AUDIENCE_RANK
    for name, _, audience in COMMANDS:
        assert audience in _AUDIENCE_RANK, f"{name} has an unknown tier {audience!r}"


def test_build_commands_embed_filters_by_tier():
    from sovereign_agent.discord_admin.bot import build_commands_embed
    everyone_emb = build_commands_embed("T", 0x000000, "everyone")
    owner_emb = build_commands_embed("T", 0x000000, "owner")
    everyone_text = " ".join(f.value for f in everyone_emb.fields)
    owner_text = " ".join(f.value for f in owner_emb.fields)
    assert "/ask" in everyone_text
    assert "/grant" not in everyone_text     # owner-only, hidden from everyone
    assert "/grant" in owner_text            # owner sees everything below it too
    assert "/ask" in owner_text


def test_build_commands_embed_never_exceeds_discord_field_limits():
    from sovereign_agent.discord_admin.bot import build_commands_embed
    emb = build_commands_embed("T", 0x000000, "owner")
    assert len(emb.fields) <= 25
    assert all(len(f.value) <= 1024 for f in emb.fields)


# ── webhook self-provisioning (she vaults her own URLs) ─────────────────────
def test_provision_plan_is_idempotent():
    from sovereign_agent.discord_admin.webhook_provision import (
        WEBHOOK_SPECS, provision_plan)
    total = len(WEBHOOK_SPECS)
    assert total >= 5                              # core + per-tracker (grows)
    assert len(provision_plan({})) == total
    stored = {"DISCORD_STATUS_WEBHOOK_URL": "https://discord.com/api/webhooks/1/a"}
    needed = [s.env_name for s in provision_plan(stored)]
    assert "DISCORD_STATUS_WEBHOOK_URL" not in needed and len(needed) == total - 1
    assert len(provision_plan(stored, refresh=True)) == total  # explicit refresh


def test_store_webhook_url_vaults_and_returns_masked_only(tmp_path, monkeypatch):
    monkeypatch.setenv("ARIA_KEYS_FILE", str(tmp_path / "vault.env"))
    from sovereign_agent.credentials import read_env
    from sovereign_agent.discord_admin.webhook_provision import store_webhook_url
    url = "https://discord.com/api/webhooks/1234567890/SECRETtoken"
    masked = store_webhook_url("DISCORD_SHOP_WEBHOOK_URL", url)
    assert "SECRETtoken" not in masked and masked.startswith("••••")
    assert read_env()["DISCORD_SHOP_WEBHOOK_URL"] == url    # vaulted for real


def test_render_results_can_never_leak_a_url():
    from sovereign_agent.discord_admin.webhook_provision import render_results
    out = render_results([
        ("storefront", "DISCORD_SHOP_WEBHOOK_URL", "created", "••••oken"),
        ("aria-status", "DISCORD_STATUS_WEBHOOK_URL", "reused", "••••2345"),
        ("announcements", "DISCORD_ADS_WEBHOOK_URL", "failed", ""),
        ("aria-control", "DISCORD_WEBHOOK_URL", "no-channel", ""),
    ])
    assert "discord.com/api/webhooks" not in out             # structural: no URLs
    assert "＋ #storefront" in out and "↺ #aria-status" in out
    assert "Manage Webhooks" in out and "channel not found" in out
    assert render_results([]).startswith("✅")


# ── my-panel-d: build_my_panel_view — a real incident, now regression-tested ─
def test_build_my_panel_view_never_raises_against_the_real_catalog():
    """2026-07-27: /my-panel raised `ValueError: item would not fit at
    row 2 (6 > 5 width)` in production — a hardcoded utility-button row
    collided with a wall of per-category buttons once the category
    count grew. Extracted to a module-level function specifically so
    this is directly testable, never again just "closures aren't
    tested". Redesigned the same day: category BUTTONS (one row-width
    slot each) became one category-picker SELECT (one slot, period) —
    structurally immune to the row-math problem that broke this once."""
    from sovereign_agent.discord_admin.bot import build_my_panel_view

    view = build_my_panel_view(set())
    assert len(view.children) > 0


def test_build_my_panel_view_holds_the_category_picker_in_one_select(monkeypatch):
    """panel-redesign-d (Kevin, 2026-07-27): "design a new panel that
    will not hit this issue in the future" — a category wall of BUTTONS
    only had ~20 categories of headroom before hitting Discord's row/
    component limits; a single SELECT holds up to 25 categories in the
    space of ONE row. 20 fake categories (well past today's real count,
    13) must all land in exactly one Select, alongside just the 3
    utility buttons — never a wall of per-category components again."""
    import discord
    from dataclasses import dataclass

    from sovereign_agent.discord_admin import bot as bot_mod

    @dataclass
    class _FakeVertical:
        slug: str
        name: str = "Fake"
        emoji: str = "🔹"
        blurb: str = "a fake vertical"
        ping_role: str = "Track-Fake"

    fake_cats = {f"CAT-{i}": [_FakeVertical(slug=f"fake-{i}")] for i in range(20)}
    monkeypatch.setattr(
        "sovereign_agent.verticals.subscribable_categories", lambda: fake_cats)
    view = bot_mod.build_my_panel_view(set())      # must not raise
    selects = [c for c in view.children if isinstance(c, discord.ui.Select)]
    assert len(selects) == 1
    assert len(selects[0].options) == 20
    assert len(view.children) == 4   # 1 picker select + 3 utility buttons


def test_build_my_panel_view_caps_the_picker_at_twentyfive_without_crashing(monkeypatch):
    """Discord hard-caps a Select at 25 options. Even well past that
    (30 fake categories — more than double today's real count), the
    panel degrades honestly (truncates the picker) instead of raising —
    the one ceiling left after the redesign, and it fails safe."""
    from dataclasses import dataclass

    from sovereign_agent.discord_admin import bot as bot_mod

    @dataclass
    class _FakeVertical:
        slug: str
        name: str = "Fake"
        emoji: str = "🔹"
        blurb: str = "a fake vertical"
        ping_role: str = "Track-Fake"

    fake_cats = {f"CAT-{i}": [_FakeVertical(slug=f"fake-{i}")] for i in range(30)}
    monkeypatch.setattr(
        "sovereign_agent.verticals.subscribable_categories", lambda: fake_cats)
    view = bot_mod.build_my_panel_view(set())      # must not raise
    import discord
    selects = [c for c in view.children if isinstance(c, discord.ui.Select)]
    assert len(selects) == 1
    assert len(selects[0].options) == 25


def test_lounge_is_social_and_open():
    # lounge-d (Kevin, 2026-07-17): the community's living room — open
    # posting for everyone, four channels, never private.
    bp = shop_blueprint()
    lounge = next(c for c in bp.categories if c.name == "LOUNGE")
    assert lounge.read_only is False and lounge.private is False
    assert [ch.name for ch in lounge.channels] == [
        "general-chat", "wins-and-pulls",
        "bot-commands",   # scout-d
        "referrals"]      # reorg-d: folded in from the retired PAYOUTS
    assert "Aria" in lounge.channels[0].topic       # she's invited, visibly


# ── phantom-role guard ─────────────────────────────────────────────────
def test_every_permission_references_a_role_that_exists():
    """consolidate-d (2026-08-04): ADMIN granted allow_roles=["Aria",
    "Staff"] and hid channels via hide_from=["Staff"], but no role named
    Staff was ever defined. Discord silently ignores an overwrite for a
    role that doesn't exist, so Camden could never open ADMIN (its entire
    purpose) and #owner-bridge was never actually restricted. Both failed
    open and quiet, which is the worst shape for a permission bug."""
    bp = shop_blueprint()
    known = set(bp.role_names())
    bad = []
    for cat in bp.categories:
        for r in cat.allow_roles:
            if r not in known:
                bad.append(f"category {cat.name}: allow_roles {r!r}")
        for ch in cat.channels:
            for r in ch.allow_roles:
                if r not in known:
                    bad.append(f"#{ch.name}: allow_roles {r!r}")
            for r in ch.hide_from:
                if r not in known:
                    bad.append(f"#{ch.name}: hide_from {r!r}")
    assert not bad, "permission(s) naming a role that doesn't exist: " + "; ".join(bad)


def test_owner_only_channels_are_hidden_from_support():
    """The audit + owner surfaces folded in from BACKEND lost their
    category-level gate in the merge, so the per-channel hide is now the
    only thing restricting them. Assert it explicitly."""
    bp = shop_blueprint()
    admin = next(c for c in bp.categories if c.name == "ADMIN")
    by_name = {ch.name: ch for ch in admin.channels}
    for name in ("owner-bridge", "angel-voice", "aria-control",
                 "aria-status", "payout-log", "mod-log"):
        assert "Support" in by_name[name].hide_from, f"#{name} is exposed to Support"
