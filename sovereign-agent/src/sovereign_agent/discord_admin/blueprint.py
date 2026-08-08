"""blueprint — the shop server described as data, so a bot can build it.

The whole BigKev's Bot Shop structure (roles, categories, channels, and the
permission intent behind each) as plain dataclasses. The planner turns this
into an ordered, idempotent list of Discord actions; the bot applies them.
Editing the server becomes "edit the blueprint, re-run" — reviewable and
repeatable, never a pile of manual clicks.

Permission model (only two toggles, like the setup guide):
  • read_only category  → @everyone: view ✓, send ✗
  • public category     → @everyone: view ✓, send ✓
  • private category    → @everyone: view ✗; each allow-role: view ✓
  • a channel can open send for @everyone (order-here) or hide from specific
    roles (priority-support hides Basic; early-access hides Basic+Pro).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

__all__ = [
    "VIEW",
    "SEND",
    "RoleSpec",
    "ChannelSpec",
    "CategorySpec",
    "ServerBlueprint",
    "shop_blueprint",
    "canon_name",
]


def canon_name(name: str) -> str:
    """Decoration-insensitive identity for roles/categories/channels.

    Kevin decorated his real categories ("🛒 SHOP", "📢 WELCOME") — emoji,
    symbols, case, and spacing are COSMETIC; the words are the identity.
    Without this, the planner/audit would call an existing decorated
    category "missing" and /setup-shop would create a plain-named twin."""
    kept = [ch for ch in str(name or "")
            if unicodedata.category(ch)[0] in ("L", "N") or ch in " -_"]
    return re.sub(r"[\s_-]+", " ", "".join(kept)).strip().casefold()

VIEW = "view_channel"
SEND = "send_messages"

# named colors → Discord integer color
_COLORS = {
    "teal": 0x1ABC9C, "gold": 0xF1C40F, "orange": 0xE67E22, "purple": 0x9B59B6,
    "blue": 0x3498DB, "green": 0x2ECC71, "grey": 0x95A5A6, "default": 0x000000,
}


@dataclass
class RoleSpec:
    name: str
    color: str = "default"
    hoist: bool = True          # show separately in the member list

    @property
    def color_int(self) -> int:
        return _COLORS.get(self.color, 0x000000)


@dataclass
class ChannelSpec:
    name: str
    kind: str = "text"          # text | voice
    topic: str = ""
    allow_send_everyone: bool = False   # open posting for @everyone (order-here)
    hide_from: list[str] = field(default_factory=list)  # role names denied view
    age_restricted: bool = False   # mead-d: Discord native 18+ gate (nsfw flag)
    # subscribe-d (Kevin, 2026-07-25): "members have to subscribe to each
    # channel... so its not so noisy." Independent of the category's own
    # private/read_only setting — a single tracker channel inside an
    # otherwise-public category (TRACKERS/GAMING/…) can be its own private,
    # opt-in island. @everyone loses VIEW; each allow_roles name (the
    # vertical's own subscriber role) gets VIEW back. /subscribe grants the
    # role, /unsubscribe removes it — genuine visibility, not just a mute.
    private: bool = False
    allow_roles: list[str] = field(default_factory=list)


@dataclass
class CategorySpec:
    name: str
    private: bool = False        # hidden from @everyone unless allow_roles
    read_only: bool = True       # public categories: read but not post
    allow_roles: list[str] = field(default_factory=list)  # who can view (private)
    channels: list[ChannelSpec] = field(default_factory=list)


@dataclass
class ServerBlueprint:
    roles: list[RoleSpec] = field(default_factory=list)
    categories: list[CategorySpec] = field(default_factory=list)

    def role_names(self) -> list[str]:
        return [r.name for r in self.roles]

    def channel_names(self) -> list[str]:
        return [c.name for cat in self.categories for c in cat.channels]


def _tracker_channels() -> list["ChannelSpec"]:
    """One channel per ★ priority vertical (from the catalog) + the
    rolling catch-all for the deep long-tail. The Hub links them all.
    Verticals homed in a named category (GAMING/COMPUTERS/…) live THERE.

    subscribe-d: each vertical's own channel is private, gated by its
    ping_role — /subscribe grants it (channel appears), /unsubscribe
    removes it (channel disappears). The catch-all stays public/read-only:
    it carries many long-tail verticals at once, so no single role could
    gate it without also hiding niches a subscriber DIDN'T ask to mute."""
    try:
        from sovereign_agent.verticals import homed_slugs, star_verticals
        homed = homed_slugs()
        chans = [ChannelSpec(v.track_channel,
                             topic=f"{v.emoji} {v.blurb} · /subscribe {v.slug}",
                             private=True, allow_roles=[v.ping_role])
                 for v in star_verticals() if v.slug not in homed]
    except Exception:  # noqa: BLE001 — blueprint must never hard-depend
        chans = []
    chans.append(ChannelSpec(
        "track-everything-else",
        topic="Every other tracked niche rolls through here — "
              "open the Hub (/scout) and ▸ View more to pick yours."))
    return chans


def _category_channels(category: str) -> list["ChannelSpec"]:
    """categories-d: a named category's channels, straight from the
    vertical catalog — blueprint and catalog can never drift apart.
    subscribe-d: same per-vertical private+role gate as _tracker_channels."""
    try:
        from sovereign_agent.verticals import category_verticals
        return [ChannelSpec(v.track_channel,
                            topic=f"{v.emoji} {v.blurb} · /subscribe {v.slug}",
                            private=True, allow_roles=[v.ping_role])
                for v in category_verticals(category)]
    except Exception:  # noqa: BLE001 — blueprint must never hard-depend
        return []


def _school_roles() -> list["RoleSpec"]:
    """panel-d: one subscriber role per ENABLED track, provisioned up front
    like _tracker_roles() does — the planner's permission overwrites need a
    real role to point at, and a permission naming a role that doesn't exist
    fails silently (see the phantom "Staff" incident, 2026-08-04)."""
    try:
        from sovereign_agent.code_school.tracks import enabled_tracks
        return [RoleSpec(tr.ping_role, "grey", hoist=False)
                for tr in enabled_tracks()]
    except Exception:  # noqa: BLE001
        return []


def _tracker_roles() -> list["RoleSpec"]:
    """subscribe-d: every channeled vertical gets its own subscriber role,
    provisioned up front (not lazily on first /subscribe) so the planner's
    permission overwrites always have a real role to point at."""
    try:
        from sovereign_agent.verticals import channeled_verticals
        return [RoleSpec(v.ping_role, "grey", hoist=False)
                for v in channeled_verticals()]
    except Exception:  # noqa: BLE001 — blueprint must never hard-depend
        return []


def _school_categories() -> list["CategorySpec"]:
    """code-school-d (Kevin, 2026-08-04): one private category per ENABLED
    language track, three channels each. Gated to Aria + owner: this is
    Kevin's own learning surface first, and building it private means the
    curriculum proves itself on a real learner before anyone pays for it.

    Driven off tracks.ENABLED, so a track stays a draft until it's an
    explicit decision — the KEEP-list discipline that verticals.py learned
    the hard way."""
    try:
        from sovereign_agent.code_school.tracks import enabled_tracks
    except Exception:  # noqa: BLE001 — blueprint must never hard-depend
        return []
    out = []
    for tr in enabled_tracks():
        # panel-d (Kevin, 2026-08-04): gated by the track's own subscriber
        # role as well as Aria, so the /my-panel toggle actually grants
        # something. Without this the picker row would flip on and off and
        # change nothing visible — a dead control is worse than no control.
        out.append(CategorySpec(
            tr.name, private=True,
            allow_roles=["Aria", tr.ping_role], read_only=False,
            channels=[
                ChannelSpec(tr.lessons_channel,
                            topic=f"{tr.emoji} {tr.blurb}"[:1020]),
                ChannelSpec(tr.drills_channel, allow_send_everyone=True,
                            topic="🧪 /drill for the next exercise, "
                                  "/submit to have your code run and graded."),
                ChannelSpec(tr.review_channel, allow_send_everyone=True,
                            topic="💬 Ask anything — Aria answers here."),
            ]))
    return out


def shop_blueprint() -> ServerBlueprint:
    """BigKev's Bot Shop — matches DISCORD_SERVER_SETUP.md exactly."""
    return ServerBlueprint(
        roles=[
            RoleSpec("Aria", "teal"),
            # staff-d (Kevin, 2026-07-17): the Support/employee role —
            # Camden (Discord "Theodore") gets this. Spectator + helps
            # invite people + drives sales; NO admin/structure/vault access.
            # Recommended Discord perms to grant it (Server Settings → Roles
            # → Support): View Channels, Create Invite, Read Message History,
            # Send Messages, Add Reactions — nothing under Management.
            # Real mod powers arrive with the MODERATION round's role ladder
            # (owner > support, never vault/structure).
            RoleSpec("Support", "gold"),
            # mead-d (Kevin, 2026-07-17): self-attest 21+ role — /mead-access
            # grants it after a 21+ confirmation; it unlocks the (also
            # Discord-native-18+-restricted) Mead Lounge. Hybrid gate.
            RoleSpec("Mead-Head", "orange"),
            RoleSpec("Veteran", "orange"),
            RoleSpec("Subscriber-VIP", "purple"),
            RoleSpec("Subscriber-Pro", "blue"),
            RoleSpec("Subscriber-Basic", "green"),
            RoleSpec("Customer", "grey", hoist=False),
            # passes-d (Kevin, 2026-07-26): "24 hour pass... week pass, month
            # pass, year pass" — one shared all-access role, sold by
            # duration only (see shop.seed_pass_products / entitlements.
            # PLAN_ROLES). "special passes... owner pass for me, admin
            # pass, staff pass" — internal, non-purchasable badge roles;
            # staff-pass reuses the existing Support role above instead of
            # a parallel one (see entitlements.PLAN_ROLES["staff-pass"]).
            RoleSpec("Pass-Holder", "green"),
            RoleSpec("Owner-Pass", "red"),
            RoleSpec("Admin-Pass", "orange"),
            *_tracker_roles(),
            *_school_roles(),
        ],
        # reorg-d (Kevin, 2026-08-03): ordered for how a NEW MEMBER reads
        # the server top-to-bottom, with two exceptions pinned above it —
        # ADMIN and BACKEND are private, so they're invisible to everyone
        # who isn't staff and cost a member nothing by sitting first, while
        # putting the owner's working surfaces one scroll from the top.
        #
        # Retired in this pass: TRACKERS (nothing left in it after the
        # focus cut), ORDERS (merged into SHOP — a 3-channel shop beats a
        # shop plus a near-identical orders aisle), STATUS and COMMAND
        # (folded into BACKEND and ADMIN), PAYOUTS (one #referrals channel
        # in the LOUNGE, where the people who'd refer actually hang out).
        categories=[
            # ── staff surface (private — members never see this) ────────
            # consolidate-d (Kevin, 2026-08-04): "admin and backend and a
            # third command category... seems a bit much for one server."
            # COMMAND folded into ADMIN in the previous pass; BACKEND folds
            # in here. One private category, ten channels, gated per-channel.
            #
            # The role is "Support", NOT "Staff". No role named Staff has
            # ever existed, so `allow_roles=["Aria", "Staff"]` granted
            # nothing and `hide_from=["Staff"]` hid nothing — Camden could
            # never open ADMIN despite that being its whole purpose, and the
            # owner-only channels were never actually restricted. Both were
            # silent: a permission that references a missing role just
            # quietly does nothing.
            #
            # Trade-off worth naming: BACKEND used to be Aria-only at the
            # CATEGORY level. Its channels now rely on per-channel hide_from
            # instead, which is one layer of defence rather than two. Kept
            # because Support is one trusted employee and the audit surfaces
            # (payout-log, mod-log) are read-only records, not controls.
            CategorySpec("ADMIN", private=True,
                         allow_roles=["Aria", "Support"], channels=[
                # — shared with Support —
                ChannelSpec("tasks",
                            topic="✅ Shared to-dos between Kevin and Camden."),
                ChannelSpec("planning",
                            topic="🗺 Bigger-picture strategy + what's next."),
                ChannelSpec("staff-room",
                            topic="🛠 Owner + staff + Aria — coordination."),
                ChannelSpec("panels",
                            topic="🎛 Run /admin-panel, /theorules or "
                                  "/my-panel here — replies are private."),
                # — owner + Aria only —
                ChannelSpec("owner-bridge", hide_from=["Support"],
                            topic="👑 Kevin ⇆ Aria — her cockpit work, "
                                  "narrated live. Owner eyes only."),
                ChannelSpec("angel-voice", hide_from=["Support"],
                            topic="⚛ Her non-classical layer speaks. "
                                  "Owner eyes only."),
                ChannelSpec("aria-control", hide_from=["Support"],
                            topic="⚙ Her control channel."),
                ChannelSpec("aria-status", hide_from=["Support"],
                            topic="📊 Uptime + fleet status."),
                ChannelSpec("payout-log", hide_from=["Support"],
                            topic="🧾 Referral payout audit trail."),
                ChannelSpec("mod-log", hide_from=["Support"],
                            topic="🛡 Moderation audit trail."),
            ]),

            # ── the member's path, in order ─────────────────────────────
            CategorySpec("WELCOME", read_only=True, channels=[
                ChannelSpec("welcome",
                            topic="👋 New here? You're auto-greeted and given "
                                  "your member role the moment you join."),
                ChannelSpec("announcements",
                            topic="📣 Server news, first — read-only."),
                # was ORDERS/#setup: the first thing a new member should do,
                # so it belongs in WELCOME rather than three categories down.
                ChannelSpec("start-here", allow_send_everyone=True,
                            topic="⭐ Run /my-panel to pick your alerts, then "
                                  "/buy when you're ready. Ask anything in "
                                  "#ask-aria."),
            ]),
            CategorySpec("SHOP", read_only=True, channels=[
                ChannelSpec("storefront",
                            topic="🛒 What we track and what it costs — "
                                  "/buy for your own checkout link."),
                # ticket-d: /ticket opens a PRIVATE thread (opener + staff +
                # Aria only). Merged here from the old ORDERS category so
                # buying and getting help live in one place.
                ChannelSpec("order-here", allow_send_everyone=True,
                            topic="💳 /buy to subscribe · /ticket for a "
                                  "private support thread · /subscription "
                                  "for your status."),
                ChannelSpec("ask-aria", allow_send_everyone=True,
                            topic="Talk to Aria — ask about the bots, "
                                  "prices, or anything before you buy."),
            ]),
            CategorySpec("LOUNGE", read_only=False, channels=[
                ChannelSpec("general-chat",
                            topic="Hang out! Aria's around too — say her "
                                  "name or @ her and she'll join in 💛"),
                ChannelSpec("wins-and-pulls",
                            topic="Flipped something good off an alert? "
                                  "Post it here 🎉"),
                ChannelSpec("bot-commands",
                            topic="Run /scout, /ask, /ma here — results "
                                  "show only to you."),
                # referral-d, folded in from PAYOUTS: the people who'd refer
                # are the people already chatting.
                ChannelSpec("referrals",
                            topic="✨ /refer for your code, /earnings for "
                                  "your numbers — both private to you."),
            ]),
            CategorySpec("SUBSCRIBERS", private=True,
                         allow_roles=["Subscriber-Basic", "Subscriber-Pro",
                                      "Subscriber-VIP", "Pass-Holder"],
                         channels=[
                             ChannelSpec("subscriber-lounge"),
                             ChannelSpec("priority-support",
                                         hide_from=["Subscriber-Basic"]),
                             ChannelSpec("early-access",
                                         hide_from=["Subscriber-Basic",
                                                    "Subscriber-Pro"])]),
            # mead-d: HYBRID gate — private to Mead-Head (self-attest 21+)
            # AND every channel Discord-native age_restricted.
            CategorySpec("MEAD LOUNGE", private=True,
                         allow_roles=["Mead-Head"], read_only=False,
                         channels=[
                             ChannelSpec("mead-hall", age_restricted=True,
                                         topic="🍯 Mead-heads unite — 21+. "
                                               "/mead-recipe"),
                             ChannelSpec("mead-recipes", age_restricted=True,
                                         topic="Recipes + techniques."),
                             ChannelSpec("mead-deals", age_restricted=True,
                                         topic="🍯 Honey, yeast + brewing-gear "
                                               "deals (the 🍯 tracker feeds "
                                               "here)"),
                             ChannelSpec("mead-showcase", age_restricted=True,
                                         topic="Show off your batches 🍯")]),

            # ── the product ─────────────────────────────────────────────
            CategorySpec("WARFRAME", read_only=True,
                         channels=_category_channels("WARFRAME") + [
                ChannelSpec("item-lookup", allow_send_everyone=True,
                            topic="🔍 /wf-lookup — type or pick an item, "
                                  "see its real buyers ranked by profit."),
            ]),
            CategorySpec("OLD SCHOOL RUNESCAPE", read_only=True,
                         channels=_category_channels("OLD SCHOOL RUNESCAPE")),
            # ── the school (private, Kevin's own) ───────────────────────
            *_school_categories(),
        ],
    )
