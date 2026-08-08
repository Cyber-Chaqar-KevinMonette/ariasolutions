# BigKev's Bot Shop — server blueprint & monetization design

The business layer on top of the live `discord_runtime`. This doc is the
blueprint Kevin sets up by hand (channels/roles) + the reference for the code
(`shop.py`, `presence.py`, `shop_stats.py`) that runs it.

## The offer (honest value)
Managed, reliable, 24/7 Discord notification bots (restock/price/feed/sports/
reminder). Customers pay because they don't want to host and babysit a bot,
and our durable queue + circuit breaker + crash-isolated fleet is exactly the
reliability they're renting. Kernel: build a stable floor for ourselves
first; automate once demand is proven.

## How she juggles it all (resilience — bots first, always room for Kevin)
The bots and her attention run in **separate lanes**, so neither starves:
- **Bots = the fleet daemon** (`sov bots daemon`): a lightweight, always-on
  loop with **no LLM and no GPU**. It polls, delivers, retries, dead-letters,
  and (optionally) publishes stats — fully automated, 24/7, even when the
  cockpit is closed and Aria is "asleep". This is why bots stay first without
  eating her attention.
- **Aria = the cockpit** (a different process): building bots, updating them,
  and working with Kevin. One conversation at a time, but never blocked by the
  running bots — they're not on the same plate.
- **She always knows the bots' state** without digging: `bot_health.py` scans
  the fleet from *persisted* signals (sources, queue backlog, dead-letters,
  quiet feeds) and gives each bot an attention level (🟢 ok / 🟡 watch /
  🔴 needs-attention) with plain reasons. `sov bots health`, the daemon flags
  it at startup, and the chat bridge answers "do any bots need updates?".
- **Automation lightens her plate**: the daemon handles the routine
  (poll/deliver/retry/stats); Aria only steps in when `bot_health` flags a
  real issue (dead feed, failing webhook, missing source). Money/bots are the
  main focus and mostly run themselves; her time with Kevin is what's freed.

## Suggestions + donation-priority (demand-driven roadmap)
`suggestions.py`: users propose add-ons/updates; anyone can **vote**, and
**donations move a suggestion up** (priority is donation-forward — dollars
dominate, votes nudge). Aria surfaces the ranked list ("what should we build
next?") so Kevin always knows the highest-leverage next build. Each
suggestion can carry a Stripe donation link (`boost_url`); a confirmed
payment calls `boost()` (manual in Round 1, reconciler in Round 2).
`sov shop suggest add/list/vote/boost/status`.

## "Without her" vs "with her" (the differentiator)
- **Autonomous bots** (`attended=false`) run on the **fleet daemon**
  (`sov bots daemon`) — no LLM/GPU, delivering 24/7 **even when Aria sleeps**.
  *"Your alerts never sleep."*
- **With-Aria features** (`attended=true`, e.g. VIP ask-Aria) work only when
  she's **awake**. The **presence** signal (`sov shop presence`, auto-posted
  on wake/sleep transitions) tells customers which mode is live.

## Server structure (create these by hand)

**Categories · channels**
- 📢 **WELCOME** — `#welcome` (what we offer + how it works), `#announcements`
  (Aria posts here), `#how-it-works`
- 🛒 **SHOP** (public, read-only) — `#storefront` (auto-published catalog +
  live stats), `#pricing`, `#live-demo` (a demo bot posting sample alerts)
- 🟢 **STATUS** — `#aria-status` (🟢 awake / 🌙 asleep presence card)
- 🎫 **ORDERS** — `#order-here`, `#order-status`
- 💎 **SUBSCRIBERS** (role-gated) — `#subscriber-lounge`, `#priority-support`
  (Pro+), `#your-alerts` (their bot's private feed), `#your-stats` (monthly
  digest), `#early-access` (VIP)
- 🔧 **BACKEND** (private to Kevin/Aria) — `#aria-control`

**Roles** — `@Customer` (one-time buyer), `@Subscriber-Basic`,
`@Subscriber-Pro`, `@Subscriber-VIP`, `@Veteran` (loyalty). Gate the
SUBSCRIBERS channels per role (VIP sees all; Pro sees priority-support; Basic
sees lounge/your-alerts/your-stats).

**Webhooks** (env vars, never stored in repo):
- `DISCORD_WEBHOOK_URL` — the base (already live in `#general`).
- `DISCORD_SHOP_WEBHOOK_URL` — a webhook in `#storefront` (catalog publish).
- `DISCORD_STATUS_WEBHOOK_URL` — a webhook in `#aria-status` (presence).
(Each falls back to `DISCORD_WEBHOOK_URL` if unset.)

## The catalog (starter prices — tweak freely; mirrored in `shop.seed_starter_catalog`)

**Tiers (recurring monthly):** Basic $5/mo · Pro $12/mo · VIP $25/mo
**Per-bot (setup + monthly):** Restock $30+$8 · Feed $25+$6 · Sports $30+$8 ·
Reminder $20+$5
**One-time / custom:** Welcome $20 · Reaction-Role $20 · Custom $75+$15/mo

### Stripe setup (per product)
Product catalog → Add product; Standard/flat-rate; USD. Recurring fee =
Recurring/Monthly/Forever; setup fee = a second one-time price on the same
product. Generate a **Payment Link** per product with: **collect email ON**
(maps payer→Discord for auto-role), **allow promo codes ON** (referrals/
loyalty), quantity OFF. Enable the **Customer Portal** so subscribers
self-cancel/update card. Paste each link via `sov shop set-link "<name>" <url>`
or the Shop Studio.

## Cancellation lifecycle (entitlement = derived from Stripe truth)
Round 2's reconciler polls Stripe and syncs Discord roles to subscription
status — never manually tracked:
- **Cancel** → Stripe `cancel_at_period_end`; keep access until the paid
  period ends, then auto-revoke the role (channels close, bot pauses).
- **Failed card** → Stripe dunning retries ~2 weeks (`past_due`); no instant
  cutoff.
- **Pause, don't delete** → keep their bot config 30–90 days for instant
  re-subscribe (never lose their setup).
- **Reactivate** → status `active` again → role re-granted, bot resumes.

## Rewards
- **Usage stats digest** (Round 1, `shop_stats.py`) → `#your-stats` monthly;
  public aggregate → `#storefront`. Makes value visible = #1 churn fighter.
- **Loyalty tenure** (Round 2) → 3mo +1 free source, 6mo free month, 12mo
  `@Veteran`. Derived from subscription age.
- **Referrals** (Round 2) → refer→both get a month (Stripe promo codes).
- **No vanity XP** — not worth it for a utility service.

## Operating flow
1. `sov shop seed` (or Shop Studio) → set Stripe links → `sov shop publish
   --live` posts the storefront to `#storefront`.
2. Customer subscribes via a Payment Link. **Round 1:** you grant their role
   manually when Stripe notifies you. **Round 2:** the reconciler does it.
3. Configure their bot: `sov bots add-source ...`; the **daemon**
   (`sov bots daemon --live`) delivers 24/7. Their `#your-stats` digest keeps
   the value visible.

## Round 2 (registered, needs a bot token + Stripe secret key)
Stripe-poll **entitlement reconciler** (grant/revoke roles, cancellation
lifecycle, loyalty, referrals) + a **discord.py** gateway role-bot hosting
**#ask-aria** (presence-aware). Both secrets live in env vars, never stored.
