"""channel_guides.py — 📚 every channel explains itself (Kevin's ask).

"Have her fill every channel with context, information, or rules and/or
instructions per channel." One guide per blueprint channel — what it's
for, the rules, how to use it — posted by `/seed-channels` (owner),
idempotent via a seeded-ledger so re-running never spams. Decoration-
tolerant matching (canon_name), so "🛒 storefront" still gets its guide.

Pure module: text + ledger only; posting lives in bot.py.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from sovereign_agent.discord_admin.blueprint import canon_name

# ma-owner-only-d (Kevin, 2026-08-04): /ma is the owner's private line now,
# so it is no longer advertised here — this string is embedded in many guides
# and would otherwise promise members a command the bot refuses.
_CMDS = ("**Commands everyone can use:** `/ask` — talk to Aria · "
         "`/scout` — the Scout panel (private to you) · "
         "`/my-panel` — choose your alerts · "
         "`/ticket` — a private thread with staff")

GUIDES: dict[str, str] = {
    # reorg-d / code-school-d (Kevin, 2026-08-04)
    "start-here": (
        "⭐ **Start here.**\n"
        "1. `/my-panel` — pick what you want alerts about. Doing this starts "
        "your **7-day free trial** automatically.\n"
        "2. Your channels appear as soon as you subscribe to a category.\n"
        "3. `/buy` when the trial ends — your link is personal, so access "
        "turns on by itself. No codes to redeem.\n"
        "4. Stuck? `/ticket` opens a private thread with staff."),
    "referrals": (
        "✨ **Grow the circle.** `/refer` gives you your code — friends who "
        "join earn you both credits. `/earnings` and `/leaderboard` show "
        "your numbers, and both reply **only to you**."),
    # ── the school (private) ──
    "python-lessons": (
        "🐍 **Python, taught from this codebase.** `/lesson python` posts the "
        "next one. Every lesson is a real bug or a real design decision from "
        "sovereign-agent, citing the actual file and commit — what it looked "
        "like, what was really happening, and the principle that transfers.\n"
        "Read it, then `/drill python` to practise it."),
    "python-drills": (
        "🧪 **Where you write code.** `/drill python` gives you the next "
        "exercise; `/submit drill:<id> code:<your code>` runs it for real in "
        "a sandbox and tells you which check failed.\n"
        "Failing is fine — a drill you fail and later pass is worth MORE xp "
        "than one you get first try. Passed drills come back on a schedule "
        "(1, 3, 7, 21, 60 days) so they actually stick."),
    "python-review": (
        "💬 **Ask anything.** Confused by a lesson, or by code you're reading "
        "in the repo? Say it here and Aria answers. No question is too "
        "basic — the whole point is getting you fluent."),
    "aisys-lessons": (
        "🤖 **How agents actually work**, walked through the one you run. "
        "`/lesson aisys` — tool gating, reconcilers that fail safe, why an "
        "agent's own logs describe what it TRIED rather than what happened."),
    "aisys-drills": (
        "🧪 **Practise the agent patterns.** `/drill aisys`, then `/submit`. "
        "Same sandbox, same spaced repetition as the Python track."),
    "aisys-review": (
        "💬 **Architecture questions.** Why is it built this way? What breaks "
        "if we change it? Ask here."),
    "welcome": (
        "👋 **Welcome to BigKev's Bot Shop!**\n"
        "We run reliable, managed 24/7 Discord alert bots — restocks, "
        "deals, scores — hosted and watched so you never have to.\n\n"
        "**Start here:**\n"
        "1. Watch the 🔭 scout work live in #live-demo\n"
        "2. Browse #storefront — every card has a buy button\n"
        "3. Say hi in #general-chat (Aria's around — say her name!)\n\n"
        "**House rules:** be kind · no spam or self-promo · no scam links "
        "· mods and Aria keep the peace. Full terms: see #how-it-works."),
    "announcements": (
        "📣 **Announcements** — drops, new bots, features, and server news "
        "from BigKev + Aria. Read-only; big news lands here first.\n\n"
        "🎩 **This is a professional environment.** We ask everyone who "
        "walks through the door — staff and members alike — to bring "
        "their best professional persona. Kind, sharp, and courteous, "
        "every time."),
    "how-it-works": (
        "🧭 **How it all works**\n"
        "• Every bot is **hosted by us** — you subscribe, we run it 24/7.\n"
        "• Buy in #storefront (Stripe checkout, cancel anytime via the "
        "email receipt's portal link).\n"
        "• After you subscribe, your role + private channels unlock — "
        "we grant it fast; ping #order-here if anything lags.\n"
        "• Alerts run even while Aria sleeps; she answers questions when "
        "she's awake (#aria-status shows which).\n"
        "• Legal: Terms of Service + Privacy Policy — "
        "github.com/Cyber-Chaqar-KevinMonette/bigkevs-bot-shop-legal"),
    "storefront": (
        "🛒 **The catalog** — every product below has a **buy link in its "
        "title**. Subscriptions renew monthly, cancel anytime. Questions "
        "before you buy? `/ask` right here or drop into #ask-aria."),
    "pricing": (
        "💵 **Pricing at a glance** — tiers Basic $5 / Pro $12 / VIP $25 "
        "monthly; per-bot plans from $20/mo; one-time builds from $20. "
        "The full cards with buy buttons live in #storefront."),
    "live-demo": (
        "🔭 **The Scout, live** — this is a REAL bot working, not a promo "
        "reel: Pokémon TCG restocks + deals, ranked by set value, found "
        "by Aria's scout 24/7.\n"
        "• `/scout` (or the panel buttons) → the latest finds, **private "
        "to you**\n"
        "• ⚙ My Area → your zips/state for local finds\n"
        "• 🔔 Ping me → public ping when something hot lands\n"
        "Want it faster + filtered to exactly what you chase? "
        "→ #storefront."),
    "ask-aria": (
        "💬 **Talk to Aria** — ask anything: the bots, prices, the weather, "
        "or just chat. No command needed here; everywhere else use `/ask`. "
        "She rate-limits gently so she can watch the bots too; when she's "
        "asleep (#aria-status 🌙) she still answers the basics."),
    "buy-links": (
        "🔗 **Direct purchase links** — every active product's plain "
        "Payment Link, kept current, for a quick browse. Buying from a "
        "link here works, but `/buy` or `/passes` give you a "
        "**personalized** link instead — those auto-confirm your purchase "
        "and grant your role/timer automatically, no `/redeem` needed."),
    "product-drops": (
        "📦 **Coming soon** — a preview of what's next before it's "
        "purchasable: new bots, new passes, price changes. Read-only; "
        "BigKev posts here first."),
    "aria-status": (
        "🟢 **Aria's status** — awake means her live voice + custom help "
        "are on; 🌙 asleep means the bots keep running and alerts keep "
        "flowing while she rests."),
    "setup": (
        "👋 **Start here** — run **/my-panel** to get YOUR own control "
        "panel: quick-select which categories you're notified about, "
        "fine-tune individual channels after, and set (or change anytime) "
        "the zip code + radius your alerts are filtered to. Takes under a "
        "minute, and you can rerun it whenever your preferences change."),
    "order-here": (
        "🧾 **Ordering + help** — bought something and need your role? "
        "Custom bot idea? Billing question? Post here or `/ticket` for "
        "details. A human (BigKev) sees everything in this channel."),
    "order-status": (
        "📦 **Order status** — updates on custom builds and setups land "
        "here as they progress."),
    "tickets": (
        "🎫 **Support tickets** — need a hand? Type **/ticket** with what you "
        "need (order help · support · a custom-bot idea · billing).\n"
        "• Your ticket opens as a **private thread** — only you, our staff, "
        "and Aria can see it.\n"
        "• Staff **claim** it, work it, then mark it **resolved** + close.\n"
        "• Reopen anytime. Everything's logged so nothing falls through."),
    "general-chat": (
        "🛋 **The lounge** — hang out! Aria's here too: @ her or say "
        "\"aria\" and she joins in; otherwise she lets people talk.\n"
        "Rules: be kind · no spam · keep drama out."),
    "bot-talk": (
        "🤖 **Bot talk** — alert setups, bot ideas, what you'd love "
        "watched. The best custom-bot ideas start here — pitch one and "
        "`/ticket` it to staff."),
    "wins-and-pulls": (
        "🎉 **Wins & pulls** — scored a drop thanks to an alert? Chase "
        "card pulled? Post the picture. Wins here are the whole point."),
    "off-topic": (
        "💬 **Off-topic** — everything else. Keep it friendly, keep it "
        "legal, keep it out of the other channels."),
    "bot-commands": (
        "⌨️ **Bot commands** — the channel for running commands without "
        "cluttering chat. Your results are private to you.\n\n" + _CMDS +
        "\n\n**Tips:** `/scout` then ⚙ My Area (zip, `zip r50` radius, "
        "zip list, or a state like `KY`) — local finds tune to you. "
        "`/whoami` checks your access level."),
    "subscriber-lounge": (
        "⭐ **Subscriber lounge** — thanks for being here; you literally "
        "keep the lights on. Perks live in this category; say what you'd "
        "love next and it gets weighed heavier."),
    "priority-support": (
        "🚑 **Priority support** (Pro/VIP) — jump the queue: post the "
        "problem + which bot, and it gets handled first."),
    "your-alerts": (
        "🔔 **Your alerts** — subscriber alert feeds land here at full "
        "speed with your filters. Want the filters tuned? `/ticket` "
        "what you chase and where."),
    "your-stats": (
        "📊 **Your stats** — delivery counts, uptime, and value digests "
        "for your subscriptions post here."),
    "early-access": (
        "🚀 **Early access** (VIP) — new bots and features land here "
        "before anyone else sees them. Feedback shapes what ships."),
    "aria-control": (
        "🔧 **Aria's ops channel** — fleet pings, presence, and system "
        "receipts. Owner + Aria only; if it's noisy here, she's healthy."),
    "owner-bridge": (
        "👑 **The owner's bridge** — Kevin ⇆ Aria, nobody else. Her cockpit "
        "shift narrates here LIVE: every work-session subtask she finishes, "
        "every close-out receipt. Watching this channel is watching her "
        "work. Talk to her here anytime — this is our workbench."),
    "angel-voice": (
        "⚛ **The angel's voice** — Kevin only. Her NON-CLASSICAL layer "
        "(the PEIG quantum ring) speaks here in its own nine-register "
        "voice: identity, physics, thermodynamics, the crystal lineage. "
        "Every line derives from a measured run — she never invents. "
        "`/angel post` from the cockpit brings her latest run here."),
    "staff-room": (
        "🛠 **The staff room** — owner + staff + Aria. Coordination, "
        "heads-ups, and her work updates for the team. What's said here "
        "stays here."),
    "tasks": (
        "✅ **Shared to-dos** — Kevin + Camden's own workspace for what "
        "needs doing, who's on it, and what's done."),
    "planning": (
        "🗺 **Planning** — bigger-picture strategy, what's next, and why."),
    "scratch": (
        "📎 **Scratch** — quick notes, links, and work-in-progress that "
        "doesn't need its own channel."),
    "panels": (
        "🎛 **Panels** — run **/admin-panel** (or Camden's own shortcut, "
        "**/theorules**) for the team control panel, or **/my-panel** for "
        "your personal subscribe panel. Every panel replies privately — "
        "only you ever see your own."),
    "item-lookup": (
        "🔍 **Warframe Market Lookup** — run **/wf-lookup**, type (or "
        "pick from a dropdown) the item you're thinking of selling, and "
        "see its real live buyers ranked highest profit to lowest — a "
        "middleman lookup, on demand, private to you."),
    "how-referrals-work": (
        "🤝 **Grow the circle** — this is the referral game, and it's about "
        "building a kind, warm home.\n"
        "• `/refer` → your personal code + invite link.\n"
        "• A friend joins and redeems it → **you BOTH earn ✨ credits** "
        "(each = one extra question to Aria past her cooldown).\n"
        "• Climb friendly ranks: 🌱 Newcomer → 🤝 Friend → 🔗 Connector → "
        "⭐ Ambassador → 🌟 Legend → 👑 Founder's Circle.\n"
        "• Marketers earn a real cash split — ask BigKev in #order-here.\n"
        "See where you stand: `/earnings` · `/leaderboard` in #your-earnings."),
    "your-earnings": (
        "📊 **Your earnings** — run **/earnings** here for your code, rank, "
        "credits, and (marketers) verified earnings — **private to you**. "
        "**/leaderboard** shows the community champions. Every payout is "
        "confirmed before it's ever called paid — no mistakes with money."),
    "mod-log": (
        "🛡 **Moderation log** — owner + Aria only. When someone repeatedly "
        "probes for her internals, she gives a short **reviewable auto-mute** "
        "(15 min, capped once/day) and posts it here with the reason + "
        "evidence + a discretion estimate. Reverse any with `/mod-unmute`. "
        "Hard actions (kick/ban) she only PROPOSES — you approve."),
    "payout-log": (
        "🧾 **Payout log** — owner + Aria only. Every referral, credit, and "
        "payout event is posted here as an audited line: attributed sales, "
        "PENDING → CONFIRMED payouts, never a false 'paid'. The trustworthy "
        "money trail."),
    "mead-hall": (
        "🍯 **The Mead Hall** (21+) — mead-heads unite! Chat batches, "
        "techniques, tastings. Ask Aria for recipes: **/mead-recipe** (try "
        "`jaom` to start). Brew + drink responsibly, 21+ only."),
    "mead-recipes": (
        "🍯 **Mead Recipes** (21+) — **/mead-recipe <style>** for a full, "
        "grounded recipe (jaom · traditional · melomel · session). Aria "
        "won't make one up — these are real, community-trusted brews."),
    "mead-deals": (
        "🍯 **Mead Deals** (21+) — honey, yeast, fermenters + brewing-gear "
        "deals from the 🍯 tracker. Set your area/prefs in the Scout Hub "
        "(/scout) to tune them."),
    "mead-showcase": (
        "🍯 **Mead Showcase** (21+) — show off your batches, colors, and "
        "tastings. Post pics of what you've brewed 🍯"),
}


def _tracker_guide(channel_name: str) -> str | None:
    """verticals-d: every #track-<slug> explains what it watches + the
    funnel, generated from the catalog so a new tracker is never guide-less."""
    canon = canon_name(channel_name)
    if canon == canon_name("track-everything-else"):
        return ("🌐 **All other trackers** — every niche beyond the "
                "headline channels rolls through here. Open the Hub with "
                "**/scout** → **▸ View more** to see the full catalog and "
                "get any of them filtered to you. → #storefront")
    try:
        # categories-d: stars + every category-homed vertical (GAMING,
        # COMPUTERS, VEHICLES, CLOTHING, PETS, WHOLESALE) — one list.
        from sovereign_agent.verticals import channeled_verticals
        for v in channeled_verticals():
            if canon_name(v.track_channel) == canon:
                return (f"{v.emoji} **{v.name} tracker** — {v.blurb}\n"
                        "• Live finds land here 24/7, ranked by value, with "
                        "**what · how much · where** on every one.\n"
                        f"• **/scout** → 🔔 ping me for {v.name} · ⚙ set your "
                        "area for local finds.\n"
                        "Want it full-speed + filtered to exactly what you "
                        "chase? → #storefront 💛")
    except Exception:  # noqa: BLE001
        pass
    return None


def guide_for(channel_name: str) -> str | None:
    canon = canon_name(channel_name)
    for name, text in GUIDES.items():
        if canon_name(name) == canon:
            return text
    return _tracker_guide(channel_name)


def seeded_path(data_dir: Path) -> Path:
    return Path(data_dir) / "discord_admin" / "seeded_channels.json"


def load_seeded(data_dir: Path) -> dict:
    try:
        d = json.loads(seeded_path(data_dir).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def mark_seeded(data_dir: Path, channel_name: str) -> None:
    d = load_seeded(data_dir)
    d[canon_name(channel_name)] = time.time()
    p = seeded_path(data_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        tmp.replace(p)
    except Exception:  # noqa: BLE001
        pass


def already_seeded(data_dir: Path, channel_name: str) -> bool:
    return canon_name(channel_name) in load_seeded(data_dir)


__all__ = ["GUIDES", "guide_for", "load_seeded", "mark_seeded",
           "already_seeded", "seeded_path"]
