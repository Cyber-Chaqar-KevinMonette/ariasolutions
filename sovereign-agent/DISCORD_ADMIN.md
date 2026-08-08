# The Admin Bot — let Aria build & manage the server for you

> **Start here instead:** `SETUP_MASTER.md` is the one ordered, deeply
> verbose path through ALL the setup (this bot is its Phase 1, with every
> click and what-you'll-see spelled out). This file stays as the reference
> for what the bot is and **how to add commands**.

A real Discord bot that can create channels/roles, set permissions, and run
slash commands — **owner-only, dry-run-first, create-only, fully audited.**
Its best trick: build your entire shop server from the blueprint with one
command instead of clicking through everything.

> Unlike the webhook (which only posts messages), this needs a **bot token**
> and `discord.py`. That's the one thing only you can set up — here's how.

---

## What it can do (safely)
- `/ask <question>` — **anyone talks to Aria.** Shop/price/status/ordering
  questions get instant grounded answers (even while she sleeps); freeform
  chat uses her live voice when she's awake. Per-user cooldown + a global
  cap protect the model; every exchange is audit-logged
  (`<data>/ask_aria/log.ndjson`); her persona is tunable via
  `<data>/ask_aria/persona.txt`. Free-chat (no slash) in **#ask-aria** and
  DMs activates when the Message Content intent is ON in the dev portal AND
  `DISCORD_ENABLE_CHAT_INTENT=1` is set.
- `/plan-shop` — **dry-run**: shows exactly what it *would* create. Touches
  nothing. Anyone can run it.
- `/scan-server` — **the plan audit** (owner): scans the live server and
  reports what's missing from the plan (named, specifically), what's extra
  (yours — never touched), and a coverage %. The bot also auto-scans on
  every connect and prints a heads-up if anything is missing, and the plan
  system announces when the blueprint itself EVOLVES (a shipped enhancement
  changed it) — so the server and the plan can never drift apart silently.
  Offline view of the last scan: `sov discord-admin scan`.
- `/setup-shop` — builds/repairs the whole server from the blueprint (all the
  categories, channels, roles, and permissions from `DISCORD_SERVER_SETUP.md`).
  **Owner-only. Create-only — it never deletes anything**, so running it twice
  just fills gaps.
- `/setup-webhooks` — **she makes her own webhooks** (owner): creates the four
  shop webhooks (#aria-control base, #storefront, #aria-status,
  #announcements) and writes each URL **straight into the Key Vault** —
  never displayed, never pasted, masked forever after. Idempotent: vaulted
  keys are skipped, an existing webhook with the right name is reused (no
  duplicates). Needs the **Manage Webhooks** permission (Server Settings →
  Roles → the bot's role). Set the PFPs afterward in each webhook's Discord
  settings if you want the pretty faces.
- `/create-channel <name> <category>` · `/create-role <name> [color]` — owner-only.
- `/ma <message>` — **mail straight to Aria's inbox** (owner, Subscriber-*,
  Staff). Lands in the cockpit ◊ inbox ("→ Aria"); she reads it at her next
  safe checkpoint. Non-owner cap: 3/day. Everyone else → /ask.
- `/whoami` — tells you if you're recognized as the owner.
- `/help` — lists commands.
- **Welcome new members (no command — automatic).** When the **Server
  Members intent** is ON in the dev portal AND `DISCORD_ENABLE_MEMBERS_INTENT=1`
  is set, Aria greets each new member in `#welcome` + a best-effort DM —
  **exactly once per person, ever** (a durable ledger dedupes re-joins and
  restarts). Preview: `sov shop welcome`; re-word it via
  `<data>/welcome/template.txt` (`{name}` placeholder). Each greeting is
  audit-logged.

**The safety leash** (all enforced in code, unit-tested):
- **Owner-only** — every changing command checks your Discord user id; nobody
  else can edit the server, no matter what they type.
- **Create-only auto-setup** — the planner emits create/permission actions
  only; it will never delete a channel/role. (Deletes would be a separate,
  explicitly-confirmed command — not built yet.)
- **Audited** — every action is logged to `<data>/discord_admin/audit.jsonl`.

---

## One-time setup (≈5 minutes)

### 1. Create the bot application
1. Go to <https://discord.com/developers/applications> → **New Application** →
   name it "Aria" → Create.
2. Left sidebar → **Bot** → **Add Bot** → Yes.
3. Under **Privileged Gateway Intents**, two are optional (everything else
   works with all of them OFF):
   - **Message Content Intent ON** + `DISCORD_ENABLE_CHAT_INTENT=1` →
     free-chat with Aria in #ask-aria and DMs (no slash needed).
   - **Server Members Intent ON** + `DISCORD_ENABLE_MEMBERS_INTENT=1` →
     Aria welcomes each new member (once ever, #welcome + DM).
   Then click **Reset Token** → **Copy** the token. (Secret — treat it like
   a password.)

### 2. Invite it to your server with the right powers
1. Left sidebar → **OAuth2 → URL Generator**.
2. Scopes: check **`bot`** and **`applications.commands`**.
3. Bot Permissions: check **Manage Channels** and **Manage Roles** (that's all
   it needs — not Administrator).
4. Copy the generated URL at the bottom, open it, pick **BigKevs-Bot-Shop**,
   Authorize.

### 3. Get your own user id (the owner)
Discord → User Settings → Advanced → turn on **Developer Mode**. Then
right-click your own name → **Copy User ID**.

### 4. Install discord.py + run the bot
```
.venv/bin/pip install discord.py
DISCORD_BOT_TOKEN='your-bot-token' \
DISCORD_OWNER_ID='your-user-id' \
DISCORD_GUILD_ID='your-server-id' \
  sovereign discord-admin run
```
(Right-click the server icon → Copy Server ID for `DISCORD_GUILD_ID`; it makes
slash commands appear instantly instead of taking up to an hour.)

Then in Discord type `/plan-shop` to preview, and `/setup-shop` to build. Want
a preview without even starting the bot? `sovereign discord-admin plan`.

---

## How to add a new command (it's easy)
Open `src/sovereign_agent/discord_admin/bot.py` → find `_register_commands()`.
Add a coroutine like the others:

```python
@tree.command(description="Rename a channel (owner).")
async def rename_channel(interaction, old: str, new: str):
    if not await _guard(interaction, "rename_channel"):   # owner check + audit
        return
    ch = next((c for c in interaction.guild.channels if c.name == old), None)
    if ch:
        await ch.edit(name=new)
    await interaction.response.send_message(f"renamed → #{new}", ephemeral=True)
```

Then add `("/rename-channel", "Rename a channel (owner).")` to the `COMMANDS`
list at the top of the file so it shows in `/help`. That's the whole recipe:
**`@tree.command` → `_guard(...)` → do the work → reply.** For anything
destructive, pass `confirm` through and call it a `delete_*`/`wipe_*` op so the
gate forces a confirmation.

---

## Where this is headed (Round 2)
This same bot is the natural home for the **subscriber auto-role** (grant/
revoke `@Subscriber-*` from Stripe status) and the **#ask-aria** channel. It's
already the authenticated, owner-gated bot presence in the server — those
features slot straight in.
