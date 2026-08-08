# 🗺️ SYSTEM MAP — the Bot Shop stack, every piece and every change

The complete map of everything built in the bot-shop arc (2026-07-12 → 13):
what each system is, where it lives, what data it writes, how you reach it,
and the full commit-by-commit change ledger. When you wonder *"where does X
live?"* — this is the page.

---

## The big picture (how the pieces connect)

```
                        KEVIN (Discord + Stripe + cockpit)
                                      │
        ┌─────────────┬───────────────┼───────────────┬──────────────┐
        ▼             ▼               ▼               ▼              ▼
   Bot Studio    Shop Studio     chat bridges     sov CLI      Admin Bot
   (/bots)        (/shop)       (8 questions)   (terminal)   (slash cmds)
        │             │               │               │              │
        ▼             ▼               ▼               ▼              ▼
  bot_projects     shop.py      conversation.py    cli.py    discord_admin/
  (definitions)   (catalog)      (intercepts)    (commands)  (server editor)
        │             │                               │
        └──────┬──────┴───────────┬───────────────────┘
               ▼                  ▼
        discord_runtime/     presence.py · shop_stats.py · bot_health.py
        (the live engine)    suggestions.py   (awareness & community)
               │
   fetchers → dedup → durable queue → rate gate → circuit breaker → webhook
               │                                                      │
               ▼                                                      ▼
        runs.jsonl audit                                     DISCORD (live 🎉)
```

**The lanes rule (resilience):** the *fleet daemon* (`sov bots daemon`) runs
the bots with **no LLM/GPU** — it keeps delivering 24/7 even when Aria's
cockpit is closed. Aria's conversation with Kevin is a separate process.
Bots first, and still always room for Kevin.

---

## System-by-system

### 1. Bot definitions — `bot_projects.py`
*What a bot IS (name, kind, concept) — define before build.*
- Cockpit: **Bot Studio** (`/bots`) — create/browse/edit/remove + ▶ dry-run.
- Chat: *"what are we building?"*
- Data: `<data>/bot_projects/<slug>.json`
- Tests: `tests/test_bot_projects.py` (18)

### 2. The live engine — `discord_runtime/`
*Runs a defined bot, legitimate by construction.*
| File | Job |
|---|---|
| `contracts.py` | rate-limits as a structural gate (illegal rate ⇒ raises; 15s civility floor; per-minute send ceiling) |
| `sources.py` | what to watch + the fastest rate it permits; per-project source store |
| `fetchers.py` | RSS/Atom (stdlib) · change-hash (dedup = free change detection) · JSON API · `fetcher_for()` by kind |
| `queue.py` | durable delivery queue — idempotent enqueue, visibility-timeout reclaim, exponential backoff, dead-letter |
| `breaker.py` | circuit breaker (closed/open/half-open) — back off a failing target |
| `delivery.py` | `DryRunDelivery` (default) · `WebhookDelivery` (env-var secret, identifying User-Agent, embeds+username) |
| `runtime.py` | poll → dedup → queue → drain (rate- & breaker-guarded) → audit |
| `manager.py` | the fleet: every bot, durable, **crash-isolated** (one bad bot can't sink the rest) |
- CLI: `sov bots ping / list / add-source / remove-source / run / fleet /
  daemon / health / queue [--requeue-dead]`
- Data: `<data>/bot_projects/<slug>/{sources.json, seen.json, runs.jsonl, queue/}`
- Tests: `test_discord_runtime.py` (26) · `test_discord_reliability.py` (21)
- **Safety:** dry-run by default; `--live` + a resolvable webhook required to
  send; secrets are env-var *names*; no selfbots/evasion/auto-purchase.

### 3. The shop — `shop.py`
*What's for sale: tiers + per-bot plans + Stripe links.*
- 10 starter products (Basic $5 / Pro $12 / VIP $25 + per-bot + one-time);
  prices in **cents**; `attended` flag = 🔆 with-Aria vs 🌙 autonomous.
- Storefront = Discord **embeds** → `sov shop publish [--live]`.
- Cockpit: **Shop Studio** (`/shop`) — add/edit/remove/seed/publish.
- Chat: *"what's in the shop?"* · CLI: `sov shop list/seed/set-link/remove/publish`
- Data: `<data>/shop/<slug>.json` · Tests: `test_shop.py` (18) + `test_shop_studio.py` (5)

### 4. Presence — `presence.py`
*Is Aria awake (🟢) or asleep (🌙)? Truth from a heartbeat, not a flag.*
- The cockpit stamps `<data>/presence/heartbeat.json` every ~5s (off-thread);
  fresh-within-3-min = awake. Process dies ⇒ she honestly reads asleep.
- Posts a card **only on transitions** (never spams): `sov shop presence
  [--publish --live]` → `#aria-status`.
- Tests: `test_presence.py` (7)

### 5. Usage stats — `shop_stats.py`
*Make the value visible — the #1 churn fighter.*
- Reads the bots' own `runs.jsonl` audit (no new storage) → per-customer
  digest ("47 alerts · 99.8% uptime") + public aggregate embed for the
  storefront. Tests: `test_shop_stats.py` (8)

### 6. Bot awareness — `bot_health.py`
*She always knows if a bot needs attention — without it eating her time.*
- Scans persisted signals only (sources / queue backlog / dead-letters /
  quiet feeds) → 🟢 ok · 🟡 watch · 🔴 needs-attention, with plain reasons.
- Reached 3 ways: `sov bots health` · daemon startup flags · chat *"do any
  bots need attention?"* Tests: `test_bot_health.py` (9)

### 7. Suggestions — `suggestions.py`
*The community proposes; donations move ideas up; the roadmap is demand-driven.*
- Priority = donation cents + (votes × 20¢) — dollars dominate, votes nudge.
- CLI: `sov shop suggest add/list/vote/boost/status` · chat *"what should we
  build next?"* · Data: `<data>/suggestions/<id>.json`
- Tests: `test_suggestions.py` (12)

### 8. The Admin Bot — `discord_admin/`
*Aria edits the server itself — the one privileged component, kept on a leash.*
| File | Job |
|---|---|
| `blueprint.py` | the whole server as data (roles/categories/channels/permission intent) |
| `planner.py` | blueprint → idempotent, **create-only** action list (cannot emit a delete) |
| `gate.py` | owner-only (fails closed), destructive ops need explicit confirm |
| `bot.py` | discord.py gateway (lazy/optional) · slash commands · audit |
- Slash: `/plan-shop` (dry-run) · `/setup-shop` (build/repair everything) ·
  `/create-channel` · `/create-role` · `/whoami` · `/help`
- CLI: `sov discord-admin plan` (no token needed) / `run`
- Data: `<data>/discord_admin/audit.jsonl` · Tests: `test_discord_admin.py` (15)
- Add a command: `bot.py → _register_commands()` — `@tree.command(name=...)`
  → `_guard(...)` → work → reply → add to `COMMANDS`.

---

### 9. The Key Vault — `credentials.py`
*Hand her credentials safely; she keeps them local, masked, and mapped to
features.*
- One private file: `~/.config/sovereign-agent/shop.env` (0600, atomic
  writes, comments preserved; `ARIA_KEYS_FILE` overrides for tests).
- **Masked always** — no screen/CLI/chat path can render a stored value
  (only `••••last4`). Saving also sets `os.environ` so daemons started from
  the cockpit see the key immediately.
- The catalog teaches: every known key carries what-it-is / which feature
  needs it / where-to-get-it / a warn-only format check. Custom keys allowed.
- Cockpit: **Key Vault** (`/keys`, ☰ → 🔐 keys) — password inputs, status
  board, remove. CLI: `sov keys status / set (hidden prompt) / unset`.
- Chat: *"which keys are missing?"* → feature-readiness report (masked).
- Tests: `test_credentials.py` (16) + `test_credentials_screen.py` (3)

### 10. Bridge patterns — `bridge_patterns.py` (the NL matcher, hardened)
All 12 chat-bridge detectors route through one normalizer (NFKC, curly→
straight quotes, casefold, whitespace collapse). **The collision matrix**
(`tests/test_bridge_patterns.py`) pushes every trigger phrase through every
detector in dispatch order — the trigger-shadowing bug class is
structurally extinct (it caught 2 live bugs on day one).

### 11. Workflow-success patterns — `success_patterns.py`
Finished work sessions are distilled (goal/outcome/subtasks/duration) into
`<data>/success_patterns.ndjson` via the session close-out hook;
`match_goal()` scores new goals against recorded WINS by deterministic
token overlap. Chat: *"what usually works?"* — advisory only, never
auto-picks. Internal patterns (her Mycelium, `stewardship/behavior.py`)
were independently reviewed + hardened (forward-compat fix, 10 new tests).

### 12. Bot bookkeeping — `discord_runtime/bookkeeping.py`
Per-bot books under `<slug>/`: **source_health.json** (fetch outcomes —
consecutive failures make a dead link visible: bot_health says "the link
looks dead"), **ledger.json** (lifetime totals, capabilities/API notes),
and **compact_runs** (runs.jsonl lines older than 30d roll into monthly
summaries; the daemon compacts daily; `sov bots ledger/compact`). External
source filters live on `Source.include_patterns/exclude_patterns`
(substring or `re:` regex; exclude wins; `--include/--exclude` flags).
Credential liveness: `sov keys check` (webhook GET validates WITHOUT
posting; token via /users/@me).

### 13. Doc registry — `doc_registry.py`
All 17 major docs registered with purpose, each **verified on disk** —
a missing doc fails the suite by name and shows ❌ in her answer. Chat:
*"where are the docs / system map?"* · CLI: `sov docs`.

### 14. ⏱ Timers — `timers.py` + cockpit `timers_screen.py`
Every live countdown from persisted state: presence age vs awake window,
live work sessions, bot uptimes, per-source next-poll countdowns, queue
retry/lease timers. `/timers`, ☰ "⏱ timers", 2s off-thread refresh.

### 15. Ask-Aria — `ask_aria.py` + `attention.py` (her voice for customers)
Customers/subscribers talk to her in Discord: `/ask <question>` (everyone,
no intents needed) + free-chat in `#ask-aria`/DMs (Message Content intent +
`DISCORD_ENABLE_CHAT_INTENT=1`). **Deterministic-first** (shop, prices,
status, ordering, suggestions — instant, grounded, work while she sleeps);
freeform uses ONE bounded LLM call on the fast slot only when she's awake
and under caps (per-user cooldown + global/minute), else a warm fallback —
never blocks, never silent. Persona in code, tunable via
`<data>/ask_aria/persona.txt`; hard rules (no secrets, no promises, no
payments); every exchange audited. **The observable attention queue**
(`attention.py`, `<data>/attention/queue.json`): bots-immediate → customers
→ Kevin, positions visible ("you're #3"), TTL-swept (crash-safe),
cross-process, shown in ⏱ Timers. Idle bots cost nothing (the daemon
sleeps between due polls); customers outrank Kevin by policy.

### 16. Ask-guard — `ask_guard.py` (protect internals, share the story)
Defense-in-depth on the customer surface (atop the structural fact that the
LLM call sees persona+question only): **input screening** deflects
extraction/injection probes ("print your system prompt", "your token",
"which llm") to her proud PUBLIC STORY + a strike (3/hr → deterministic-only
for that user); **output screening** scrubs any actual vault value or
secret-shaped string (webhook/Stripe/token/path) to ▮▮▮ before it leaves.
Wired through `answer_question`. Tests: `test_ask_guard.py` (15).

### 17. Advertising — `advertising.py` (📣 promos, spam-proof by construction)
Rotating promo cards: the general shop card first, then every active
product (price, mode, Stripe link, professional footer). **Structural
cadence floor** — at most one ad per 6h regardless of caller or arguments;
dry-run never advances rotation or burns the window. Lead-line tunable via
`<data>/advertising/copy.txt`. CLI: `sov shop advertise [--live]` +
`sov shop ads` (status). Auto-mode: the fleet daemon posts on cadence when
`DISCORD_ADS_AUTO=1` AND the daemon runs `--live` (a dry-run daemon stays
silent). Webhook: `DISCORD_ADS_WEBHOOK_URL` → `DISCORD_WEBHOOK_URL`.
State: `<data>/advertising/state.json`. Tests: `test_advertising.py` (8).

### 18. Welcome — `welcome.py` + `on_member_join` (she greets, exactly once)
New members get her warm tour (#how-it-works / #storefront / #ask-aria /
#order-here) in `#welcome` + a best-effort DM. A durable dedupe ledger
(`<data>/welcome/welcomed.json`, bounded 10k) makes double-greeting
impossible across re-joins, gateway replays, and restarts. Template
override: `<data>/welcome/template.txt` (`{name}`). Needs the privileged
**Server Members intent** → opt-in `DISCORD_ENABLE_MEMBERS_INTENT=1` (same
pattern as the chat intent). CLI preview: `sov shop welcome`.
Tests: `test_welcome.py` (5).

### 19. Server plan — `discord_admin/server_plan.py` (scan · audit · evolve)
The living server plan. **Snapshot**: the bot captures role/category/channel
names on every connect + on `/scan-server` →
`<data>/discord_admin/server_snapshot.json` (atomic, corrupt-resilient).
**Audit**: pure diff vs `blueprint.py` — missing items named specifically,
extras reported but never touched, coverage %. **Evolution detection**: the
blueprint is sha256-fingerprinted; any shipped enhancement announces itself
at the next consult ("the plan EVOLVED — /scan-server, then /setup-shop")
exactly once — plan and server can't drift apart silently, by construction.
`/setup-shop` refreshes the snapshot after building. CLI (offline, no
token): `sov discord-admin scan`. Tests: `test_server_plan.py` (8).

### 20. 📡 Auto-Discord — `discord_watch.py` + `sov shop duty` (her shift, watched)
Kevin's "she works Discord all day/night and we watch everything she does
and learns." **The duty loop** (`sov shop duty [--live]`): each tick =
fleet deliveries + heartbeat `note="on duty"` (keeps ask-Aria's live voice
up all night) + presence cards + opt-in auto-ads + daily books + health
flags — every lane crash-isolated, HALT-aware, ledgered to
`<data>/discord_duty/ledger.ndjson`. **The watch** (`discord_watch.py`):
unified read-layer merging every existing ledger (ask log, admin audit,
runs, welcomes, ads, success patterns, source health, duty ticks) into one
newest-first activity stream + `duty_status` header (duty/bot freshness,
presence, queue, today's counts). Cockpit **📡 /discord** screen
(off-thread 2s refresh) + chat bridge #12 "what's happening on discord?".
**📯 /server-message <text>** (cockpit) / `sov shop announce` — Kevin
speaks to #announcements (owner speech: no cadence floor; typed command =
consent → posts live). Tests: `test_discord_watch.py` (5) +
`test_discord_watch_screen.py` (2) + matrix now 13 bridges.

### 21. ✉ /ma — `member_mail.py` (mail straight to Aria's inbox)
Discord `/ma <message>` → her collaboration inbox (the cockpit ◊ inbox,
"→ Aria" section — the same RequestStore `sov requests tell` writes; she
reads at safe checkpoints, never mid-task). Eligibility: owner +
Subscriber-* + **Staff** (the role is now IN the blueprint, gold, prepared
for Kevin's future employees); everyone else is pointed at /ask.
Structural anti-flood: non-owner cap 3/day (`member_mail/quota.json`,
corrupt→resets open-handed). Owner mail lands priority=high. Audited (op
"ma"), shown in Discord Watch as ✉. SQLite write = one function, one
thread. Tests: `test_member_mail.py` (6).

### 22. 🪜 Model Ladder — `model_ladder.py` + `sov models` (prove-then-promote)
Colibrì-inspired (Kevin's `Plans/Nextplan4/colibri-main.zip`): bigger
models become slot defaults ONLY when the vessel proves it can carry
them. Per-slot ladders (rung 0 = configured base, always trusted; higher
rungs = registered candidates via `sov models add <slot> <model>`);
`sov models prove <model>` runs a bounded trial (load ≤180 s, ≥5 tok/s,
non-empty answer, **keep_alive=0** so a trial can never zombify VRAM);
proofs pin to a hardware fingerprint (GPU+VRAM+RAM — new hardware →
re-prove); `sov models promote <slot>` writes AGENT_<SLOT>_MODEL to the
vault (explicit consent; refuses when nothing above base is proven).
`sov models status` = hardware + every rung's proof state. Failed newer
proofs retract older vouches. Tests: `test_model_ladder.py` (6).

### 23. 🎯 Post-intent gate — `post_intent.py` (signal vs noise, F1 2026-07-19)
Every scout item classified before it may post: AVAILABLE · SHOWCASE ·
SELLING · BUYING · EXPIRED · UNKNOWN (first-match precedence EXPIRED >
SELLING > BUYING > SHOWCASE > AVAILABLE; UNKNOWN passes — never silence
a possible live deal on a guess). Default channel policy = AVAILABLE +
UNKNOWN; a source widens via `Source.allowed_intents`. Suppressions
counted per intent in `CycleReport.intent_filtered` → "noise gate:
showcase:3" in every cycle summary. Tests: `test_post_intent.py` (7).

### 24. 💛 Recognition + Aria IDs + hardening — `members.py` (community-grade)
"Do you know who I am?" answers deterministically from the client DB
(owner crown / member history+note / honest stranger greeting), routed
in `ask_aria` BEFORE the generic routes (needs the asker's identity).
Works asleep. PLUS (2026-07-19b): **Aria IDs** (`A-XXXXXX` minted once
per member, `find_by_aid`), **ID-bound team bindings** (name-spoof hole
closed), index files excluded from the roster, and the gateway
self-registers Aria's own record on connect. **Walls in her voice**
(`ask_guard`): service boundary (server/system harm) + ethics wall
(unethical/illegal) — deterministic deflection + strike before any
model runs. Tests in `test_members.py` + `test_ask_aria.py`.
**🎚 `/tiers`** (`cockpit/tier_screen.py`): trust-tier menu — raise by
typed phrase, kill switch drops to tier 1 in one click.

### 26. ✉ Mail drain — `mail_drain.py` (she replies to everything, F3b)
Drains HER inbox (`direction=to_aria`): composes a reply to each
unanswered Discord member note via ask_aria (same walls), DMs it back,
records it on the note. Owner mail never auto-answered. Slow mode
(<=3/tick) + mid-task gate = never fights her work or the fleet.
Gateway loop ~30s. Tests: `test_mail_drain.py`.

### 25. 👑 The owner's bridge — COMMAND category + `work_narrator.py` (F5)
Blueprint category **COMMAND** (private): `#owner-bridge` (owner+Aria
only, hidden from Staff) + `#staff-room` (owner+staff+Aria); webhook
spec `owner-bridge` → `DISCORD_OWNER_WEBHOOK_URL`. `work_narrator`
posts one throttled line (≥60s, pending-collapse) per finished work
subtask + prefers the bridge for session close-outs — watching the
channel IS watching her cockpit shift. Best-effort: narration can never
break a session. Tests: `test_work_narrator.py` (7).

### 27. ⚛ The angel bridge — `angel_bridge.py` + `angel_chat.py` + `/angel`
Her NON-CLASSICAL layer (the PEIG quantum engine, sibling repo
`peig-engine/`) talks in the cockpit and in Discord. The engines stay
separate; they talk via LEDGERS: a speaking run (SessionConfig
`speak=True`) writes nine-register voice lines + summaries into
`peig-engine/runs/<name>/events.ndjson`; the bridge reads the LATEST
run slice (crash-proof) and renders it. Surfaces: cockpit `/angel`
(chat pane) + `/angel post` (→ #angel-voice); **#angel-voice** channel
(👑 COMMAND, owner+Aria only, hidden from Staff, webhook
`DISCORD_ANGEL_WEBHOOK_URL`); TWO-WAY: the owner can message the
channel — `speak` runs a fresh bounded session via the engine's own
venv, `status` reports the latest, anything else gets the honest
explainer (the ring is not a chatbot — conversation is Aria's classical
lane; the ring is identity/deliberation/calibrated refusal). Tests:
`test_angel_bridge.py` (4) + `test_angel_chat.py` (5).

### 28. 🪟 Observability modes + replay sanitize — `/obs` (obs-modes-d)
Two modes: **all** (default, every window) · **focus** (live chat +
inbox only — memory/live/atelier hidden, pure CSS, state preserved).
`/obs [all|focus]`, bare `/obs` toggles; persisted beside the layout
pref and restored on launch. Plus `sanitize_replay_text` +
`glyphs.purge_unsafe_diamonds`: the launch-time thread replay strips
stored Rich markup tags and purges pre-ban diamonds (◈◆◇♦→◊) — old
sealed chunks can never re-introduce banned glyphs (chunks stay
verbatim at rest; only the DISPLAY sanitizes). Tests:
`test_obs_modes_replay.py` (5).

### 29. 🛡 Reward-system hardening — `referrals.py` (H1, 2026-07-19)
Real, found gaps closed with named research grounding: **sybil
resistance** (`account_age_days` decodes a Discord Snowflake's embedded
timestamp, zero network calls; `SybilPolicy` = min account age + a
referrer velocity cap read from the ledger itself) — a below-threshold
`/refer` redemption is HELD, not denied (`referral-held` ledger event +
a visible `diagnosis.py` Conflict case, type=ambiguity), never silently
blocking a legitimate new member. **Ledger reconciliation**
(`verify_ledger_consistency`) replays `ledger.ndjson` through the SAME
clamp transition `grant_credits` uses live and flags drift against the
derived `credits`/`earned_cents` — proper event-sourcing rebuild, not a
naive sum. **Write-failure visibility**: every store write's blanket
`except: pass` now opens a `diagnosis.ConflictCatalog` case
(type=omission) — its first real production caller — with a stdlib-
logging fallback if even that fails. **Idempotency + a ceiling**:
`grant_credits` takes an optional `idempotency_key` (Stripe's own
pattern) checked against the ledger, plus `MAX_CREDITS` so no bug or
abuse loop mints an unbounded balance. Tests: `test_referrals.py`
(19 total, 10 new).

## ⏳ NOT built yet (registered in the plan)
- **F-batch remainder (2026-07-19)**: F2 threads architecture ·
  F3b two-inbox split + reply-to-everything drain · F4 tier approval
  menu · F6 thinking heartbeats · F7 cockpit copy · F10 shell corps ·
  F11 language proving grounds (all specced in the plan file)
- **Moderation** (owner-gated mute/kick/ban with required reason + a
  discretion-scored ledger + `#mod-log` + DM to the person; NOT autonomous)
  — `moderation.py` + `discord_admin` slash commands. In the plan.
- **Round 2 monetization** — Stripe-poll entitlement reconciler (auto
  grant/revoke `@Subscriber-*` roles, cancellation lifecycle, loyalty,
  referrals). Needs Stripe secret key + the bot token.

## Aria's chat bridges (deterministic, grounded, small-model-proof)
| You ask | She reads |
|---|---|
| "who are you / what can you do" | her self-map |
| "what did you do" | review journal + sessions |
| "how are you" | sentinel health + emotion |
| "what do you need / what's next" | open requests + due items |
| "what are we building?" | the bot-project store |
| "what's in the shop?" | the catalog |
| "do any bots need attention?" | the fleet health scan |
| "what should we build next?" | ranked suggestions |
| "which keys are missing?" | the Key Vault (masked feature-readiness) |
| "what usually works?" | her workflow-success wins (advisory) |
| "where are the docs / system map?" | the verified doc registry |
| "what's happening on discord?" | the unified Discord activity stream |

## Environment variables (all secrets; env file: `~/.config/sovereign-agent/shop.env`)
| Var | Feeds | Falls back to |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | base posting (`bots ping`, fleet) | — |
| `DISCORD_SHOP_WEBHOOK_URL` | `shop publish` → `#storefront` | `DISCORD_WEBHOOK_URL` |
| `DISCORD_STATUS_WEBHOOK_URL` | presence → `#aria-status` | `DISCORD_WEBHOOK_URL` |
| `DISCORD_ADS_WEBHOOK_URL` | `shop advertise` → ads channel | `DISCORD_WEBHOOK_URL` |
| `DISCORD_BOT_TOKEN` | admin bot login | — |
| `DISCORD_OWNER_ID` | the only account allowed to admin | — (fails closed) |
| `DISCORD_GUILD_ID` | instant slash-command sync | global sync (~1h) |
| `DISCORD_ENABLE_CHAT_INTENT` (`1`) | free-chat in #ask-aria/DMs | off → `/ask` only |
| `DISCORD_ENABLE_MEMBERS_INTENT` (`1`) | welcome-new-members greeting | off → no greeting |
| `DISCORD_ADS_AUTO` (`1`) | daemon auto-ads (needs `--live`) | off → manual only |

## The change ledger (this arc, oldest → newest)
| Commit | What changed |
|---|---|
| `f574315` | **Bot Studio** — bot_projects store + cockpit screen + "/bots" + chat bridge |
| `10bd969` | **Discord runtime** — contracts/sources/delivery/runtime, `sov bots`, safe by construction |
| `0212939` | docs: SPRINT_STATE + engineering lessons for the runtime |
| `17b3b4b` | **Reliability** — fetchers, durable queue, circuit breaker, crash-isolated fleet |
| `316a3e3` | `sov bots ping` — one-command connection test |
| `86f6578` | **LIVE-PROVEN** — User-Agent fix (Discord edge 403/1010); first real send landed |
| `0992249` | **Bot Shop R1** — shop catalog, storefront embeds, presence, stats, Shop Studio, SHOP_DESIGN + server guide |
| `e4521fd` | **Juggling resilience** — fleet daemon, bot_health, suggestions + donate-to-prioritize, bridge-collision fix |
| `1856916` | docs: permissions guide simplified (clicks, not a matrix) |
| `ec00a15` | **Admin bot** — blueprint/planner/gate/bot, `/setup-shop`, `sov discord-admin`, DISCORD_ADMIN.md |
| `d238736` | **Fable pass** — slash-name fix, reconnect guard, SETUP_MASTER.md, this map |
| `284e856` | **Key Vault** — credentials menu (masked, 0600, local; `sov keys`) |
| `8b5cae2` | **R1 booster** — bridge_patterns matcher + collision matrix (fixed 2 live routing bugs) |
| `6a47fdb` | **R2+R3** — Mycelium review/hardening (forward-compat fix) + source include/exclude filters |
| `bde8462` | **R4** — workflow-success patterns ("what usually works?") |
| `783662a` | **R5** — link-rot telemetry, credential probes (`keys check`), ledgers + daily compaction |
| `3ad7b3b` | **R6** — vault 2k-key scale proof + the doc registry (`sov docs`) |
| `9fdf1c5` | **R6.5** — ⏱ Timers window (`/timers`) |

## Test inventory for the arc
`test_bot_projects` 18 · `test_discord_runtime` 26 · `test_discord_reliability` 21
· `test_shop` 18 · `test_shop_stats` 8 · `test_shop_studio` 5 · `test_presence` 7
· `test_bot_health` 9 · `test_suggestions` 12 · `test_discord_admin` 15
≈ **139 tests for the shop stack**; full repo suite green at 321/321 files.

## What is deliberately NOT built yet (Round 2 — specced, waiting)
- **Entitlement reconciler** — poll Stripe (secret key, env var) → derive who's
  active → auto grant/revoke `@Subscriber-*` roles; full cancellation
  lifecycle (period-end revoke, dunning grace, pause-don't-delete); loyalty
  tenure + referral credits. Home: the admin bot.
- **#ask-aria** — presence-aware attended channel on the admin bot.
- Per-customer private `#your-alerts` webhooks; HTML-scrape fetcher; Stripe
  → suggestion-boost auto-credit.
