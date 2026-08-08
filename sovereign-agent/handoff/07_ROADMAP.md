# 07 — Roadmap (honest gaps, from GOD_TIER_CRITERIA.md)

## Income surface — Discord Bot Shop (2026-07-12, LIVE)
Shipped & live-proven: the Bot Studio (define), the safe-by-construction
`discord_runtime` (rate-limits as a structural gate, dry-run default,
env-var-only secrets, durable queue + circuit breaker + crash-isolated fleet
manager, RSS/change/JSON fetchers), and the **Bot Shop** (`shop.py` catalog +
tiers/pricing, embed storefront, `presence.py` awake/asleep, `shop_stats.py`
usage digests, `sov shop`/`sov bots daemon`, Shop Studio `/shop`). Connected
to BigKevs-Bot-Shop; `sov bots ping` posts live. Docs: `SHOP_DESIGN.md`,
`DISCORD_SERVER_SETUP.md`, `Plans/NextPlan3/DiscordBotStudio/DESIGN.md`.

**Round 2 (next, needs a Discord bot token + Stripe secret key, env-vars
only):** the Stripe-poll **entitlement reconciler** (derive active subs →
auto grant/revoke roles; cancellation lifecycle; loyalty tenure; referrals) +
a **discord.py** gateway role-bot hosting **#ask-aria** (presence-aware).
Then per-customer `#your-alerts` private delivery. This is the automation
that removes the manual role-grant step.

---


Near: the loose-threads worklist (48 findings at first scan — wire,
retire, or accept each); WorkflowsScreen drafts view; vessel-strip
proving-ground score; named-thread overlay (Ereblo chats schema ready,
deliberately unwired until wanted); LLM-refined scope matching.

Medium: memory/consistency hardening round (planned — see the plan
file's FABLE II section); live proving-ground expansion; dream_runner/
interrupts resume unification; driver consolidation (mode_controller vs
bridge); revisit the 8B tool-use model (its 8192 window is her tightest
physical constraint).

Far: the Cloud Horizon — one sovereign vessel per subscriber, headless
FastAPI seam over the session bridge, per-vessel isolation audit BEFORE
any paying user.
