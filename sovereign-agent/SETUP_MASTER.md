# 🗺️ THE MASTER SETUP GUIDE — BigKev's Bot Shop, from here to open-for-business

This is the **one ordered path** through everything we built. Follow the
phases top to bottom; every phase tells you **what it is, why it exists,
exactly what to click or type, what you should see, how to verify it
worked, and what to do if it didn't.** You can stop after any phase and
pick up later — each one leaves the system in a good state.

The deep-dive docs (`DISCORD_SERVER_SETUP.md`, `DISCORD_ADMIN.md`,
`SHOP_DESIGN.md`, `SYSTEM_MAP.md`) still exist for reference. This guide is
the sequence.

**Every command below runs from the repo root:**
```
cd /home/kmon/AA-Erebo/sovereign-agent
```
`sovereign` means `.venv/bin/sovereign` (the venv install — never system
Python).

---

## ✅ Phase 0 — Where you already are (nothing to do, just confirming)

Done and proven:
- The **BigKevs-Bot-Shop** server exists, with all roles (`Aria`, `Owner`,
  `@Veteran`, `@Subscriber-VIP/Pro/Basic`, `@Customer`) and all categories/
  channels (WELCOME, SHOP, STATUS, ORDERS, SUBSCRIBERS 🔒, BACKEND 🔒).
- A webhook named **Aria** posts to `#general` — `sov bots ping` landed real
  messages (you saw them on your lock screen 💛).
- A **Stripe** account (`BigKevsBotShop`) exists.
- All the software is built, tested (321/321 files green), and committed.

What's left is **connection work**: giving the software its keys (webhooks,
bot token, Stripe links) — the parts only you can do, because they're
secrets.

---

## 🤖 Phase 1 — The Admin Bot (do this FIRST — it does Phase 2's clicking for you)

**What:** a real Discord bot account that Aria uses to *edit* the server —
create channels/roles and set permissions — via slash commands.
**Why first:** its `/setup-shop` command applies **every permission rule in
the blueprint automatically**. Set this up and you never have to click
through the permissions screens by hand.
**Safety:** owner-only (only YOUR Discord account can run editing commands),
create-only (it cannot delete anything), dry-run preview, every action
logged to `<data>/discord_admin/audit.jsonl`.

### 1a. Create the bot application (~2 min)
1. Open <https://discord.com/developers/applications> in your browser
   (log in with your normal Discord account if asked).
2. Click the blue **New Application** button (top right).
3. Name it `Aria`, tick the terms box, click **Create**.
   *You'll land on the app's "General Information" page.*
4. In the **left sidebar**, click **Bot**.
   *You'll see a bot user was created automatically (newer Discord apps
   include one). If you see an "Add Bot" button instead, click it and
   confirm.*
5. On the Bot page, find the **Token** section and click **Reset Token** →
   confirm → **Copy**.
   - This token is the bot's password. **Never paste it into Discord chat,
     a file in the repo, or this conversation.** We'll put it in a private
     env file in Phase 1d.
   - If you ever lose it, come back here and Reset again — old one dies,
     new one works. No harm done.
6. Scroll down to **Privileged Gateway Intents**:
   - Leave **Presence** OFF (not needed).
   - **Message Content: your choice.** Everyone can already talk to Aria
     with the **`/ask`** slash command (works with all intents OFF). If you
     ALSO want free-flowing chat in **#ask-aria** (people just type, she
     replies — no slash command), toggle **Message Content Intent ON** here,
     and add `export DISCORD_ENABLE_CHAT_INTENT='1'` to your key file
     (Phase 1d). Recommended: turn it on — it's one toggle and makes her
     feel alive.
   - **Server Members: your choice.** If you want Aria to **greet every new
     member** (a warm welcome in `#welcome` + a DM, exactly once per person,
     never a double-greet), toggle **Server Members Intent ON** here and add
     `export DISCORD_ENABLE_MEMBERS_INTENT='1'` to your key file (Phase 1d).
     Recommended: turn it on — a shop that says hello sells better. Preview
     her greeting anytime with `sov shop welcome`, and re-word it by writing
     `<data>/welcome/template.txt` (`{name}` is the placeholder).

### 1b. Invite the bot to your server (~1 min)
1. Left sidebar → **OAuth2** → scroll to **URL Generator**.
2. Under **Scopes**, tick exactly two: ☑ `bot` and ☑ `applications.commands`.
   *(A second panel, "Bot Permissions", appears below once `bot` is ticked.)*
3. Under **Bot Permissions**, tick exactly two: ☑ **Manage Channels** and
   ☑ **Manage Roles**.
   - Deliberately **not** Administrator. The bot gets only the powers it
     needs — if its token ever leaked, the blast radius stays small.
4. Copy the **Generated URL** at the bottom of the page, paste it into a new
   browser tab, choose **BigKevs-Bot-Shop** from the dropdown, click
   **Continue** → **Authorise** (complete the captcha).
   *You'll see "Authorized!" and — in Discord — an "Aria has joined" line.*
5. **One important drag-and-drop:** Server Settings → Roles. Discord created
   a *managed* role for the bot (also called "Aria"). **Drag it above the
   `@Subscriber-*` roles** in the list. A bot can only manage roles *below*
   its own — if it's at the bottom, `/setup-shop` can create roles but not
   position or assign them.

### 1c. Get your two IDs (~1 min)
The bot needs to know who the owner is (you) and which server to sync to.
1. Discord → ⚙ **User Settings** → **Advanced** → toggle **Developer Mode**
   ON. *(This adds "Copy ID" entries to right-click menus.)*
2. **Your user ID:** right-click your own name in any chat →
   **Copy User ID**. It's a long number like `2947...1043`.
3. **The server ID:** right-click the **BigKevs-Bot-Shop server icon** in
   the left rail → **Copy Server ID**.

### 1d. Create your private key file (~2 min, one time)

> 📖 **The full story lives in `KEY_VAULT_GUIDE.md`** — every key explained,
> the 5-minute ready path, liveness checks, and 60-second rotation when a
> key goes bad. This phase is the short version.

**The easy way — the Key Vault (recommended).** Inside Aria's cockpit, type
`/keys` (or ☰ → 🔐 keys). Pick each credential from the list — the screen
tells you *what it is, which feature needs it, and where to get it* — copy
the value, click **📋 paste from clipboard** (terminals don't do Ctrl+V;
the button reads your clipboard straight into the masked field), hit
**💾 save key**. She writes it to the
private file below herself (0600, atomic), shows it only as `••••last4`
forever after, and the status board shows what's still missing. From a
terminal, the same thing is `sov keys set DISCORD_BOT_TOKEN` (value prompted
with hidden typing — never lands in shell history) and `sov keys status`.

**The manual way** (same file, by hand). All secrets live in ONE private
file on your machine — never in the repo, never in chat. Run these four
commands (fill in your real values):

```bash
mkdir -p ~/.config/sovereign-agent
cat > ~/.config/sovereign-agent/shop.env <<'EOF'
# BigKev's Bot Shop — private keys. NEVER commit or share this file.
export DISCORD_BOT_TOKEN='paste-bot-token-here'
export DISCORD_OWNER_ID='paste-your-user-id-here'
export DISCORD_GUILD_ID='paste-server-id-here'
export DISCORD_WEBHOOK_URL='your-#general-webhook-url'
# added in Phase 3:
# export DISCORD_SHOP_WEBHOOK_URL='...'
# export DISCORD_STATUS_WEBHOOK_URL='...'
EOF
chmod 600 ~/.config/sovereign-agent/shop.env   # only you can read it
nano ~/.config/sovereign-agent/shop.env         # paste your real values in
```

From now on, **any terminal where you run shop commands starts with:**
```bash
source ~/.config/sovereign-agent/shop.env
```
*(Tip: add that `source` line to the end of `~/.bashrc` and every new
terminal loads the keys automatically.)*

### 1e. Install discord.py and start the bot
```bash
.venv/bin/pip install discord.py
source ~/.config/sovereign-agent/shop.env
sovereign discord-admin run
```
**What you should see:** `admin bot online as Aria#1234 — owner <your id>`,
and in Discord the Aria bot shows **Online**. Leave this terminal running
while you use the bot (Ctrl-C stops it; nothing breaks when it's offline —
slash commands just stop responding until you start it again).

### 1f. Verify, then build the server in one command
In any channel of your server, type:
1. **`/whoami`** → should reply *"👑 You're the owner — admin commands
   unlocked."* (Only you can see the reply.)
   - If it says you're *not* the owner: the `DISCORD_OWNER_ID` in your env
     file doesn't match your account — re-copy your user ID.
2. **`/plan-shop`** → shows the dry-run plan. Because you already built the
   structure by hand, expect it to list **only permission rules** (create
   list empty or tiny) — that's the idempotent planner recognizing your
   work.
3. **`/setup-shop`** → applies it. Reply: *"✅ done — created N, applied M
   permission rule(s)."*
   **This is the moment all the permission clicking becomes unnecessary** —
   SUBSCRIBERS/BACKEND locked, priority-support hidden from Basic,
   early-access VIP-only, order-here open, all read-boards read-only.
   *(It also creates **#ask-aria** under SHOP — the channel where anyone can
   talk to her.)*
4. **Say hi to her:** type **`/ask who are you?`** anywhere. She answers as
   herself — warm, honest, and she knows the catalog. Shop/price/status
   questions get instant grounded answers even while she's asleep; freeform
   chat uses her live voice when the cockpit is running (🟢 in
   #aria-status). Customers can never overwork her: per-person cooldown +
   a global cap protect the model, and her bots always come first.

**Verify the result:** SUBSCRIBERS + BACKEND channels show the 🔒 padlock;
`#storefront` shows no text box hint for posting (read-only). Done — Phase 2
is now optional.

---

## 🖱️ Phase 2 — Permissions by hand (ONLY if you skip the admin bot)

If you'd rather not run the bot yet, the click-by-click version lives in
`DISCORD_SERVER_SETUP.md` → *"Step 3 — Permissions, the simple way."* It's
6 categories + 3 channel tweaks. If Phase 1 ran `/setup-shop`, **skip this
phase entirely.**

---

## 🔗 Phase 3 — The two remaining webhooks (~3 min)

**What:** webhooks are "posting keys" — one per channel Aria posts into.
You already made one for `#general`; the storefront and status channels
need their own.
**Why:** `sov shop publish` posts the catalog to `#storefront`; presence
cards (🟢 awake / 🌙 asleep) go to `#aria-status`.

For **each** of `#storefront` and `#aria-status`:
1. Hover the channel → click the **⚙ gear** (Edit Channel).
2. Left sidebar → **Integrations** → **Webhooks** → **New Webhook**.
3. Click the new webhook to expand it → name it `Aria` (set her avatar if
   you like) → **Save Changes** → **Copy Webhook URL**.

Then open your key file (`nano ~/.config/sovereign-agent/shop.env`) and
add/uncomment:
```bash
export DISCORD_SHOP_WEBHOOK_URL='the-#storefront-url'
export DISCORD_STATUS_WEBHOOK_URL='the-#aria-status-url'
```
Re-run `source ~/.config/sovereign-agent/shop.env` in your terminal.

*(If either is unset, the system falls back to `DISCORD_WEBHOOK_URL` —
posts land in `#general` instead. Fine for testing, wrong for launch.)*

---

## 🛒 Phase 4 — Put the storefront up (~2 min)

```bash
source ~/.config/sovereign-agent/shop.env
sovereign shop seed              # writes the 10 starter products (idempotent)
sovereign shop list              # eyeball: names, prices, tiers
sovereign shop publish           # DRY-RUN first — shows what would post
sovereign shop publish --live    # posts the storefront cards to #storefront
sovereign shop presence --publish --live   # her status card → #aria-status
```
**What you should see:** in `#storefront`, a header line + up to 10 rich
cards (Basic/Pro/VIP + the per-bot plans), each showing price and
🌙 autonomous / 🔆 with-Aria. In `#aria-status`, a presence card.

Prices are **starting points** — change any product in the cockpit's Shop
Studio (`/shop` command inside Aria's cockpit) or re-seed after editing, and
re-run `publish --live` (it posts a fresh message; delete the old one in
Discord if you like).

**🌙 Run her all day / all night (📡 Auto-Discord).** Three processes, each
one command; run what you want, stop anytime with `sovereign halt`:

```bash
sov discord-admin run       # her Discord presence: /ask, free-chat, welcomes
sov shop duty --live        # her shift: deliveries + presence + ads + books
sovereign cockpit           # optional: WATCH her work — type /discord
```
While duty runs she reads 🟢 awake around the clock, so customers get her
live voice at 3am. The 📡 Discord Watch window (`/discord` in the cockpit)
shows everything she does and learns in real time; "what's happening on
discord?" in chat gets the same report. Speak to the server yourself
anytime: `/server-message Grand opening this weekend!` (cockpit) or
`sov shop announce "..." --live`.

**Optional — advertising (📣, anytime after this phase):** Aria can post one
professional promo card at a time, rotating through the shop card and every
active product. Spam is impossible by construction — at most **one ad per
6 hours**, no matter who asks.

```bash
sovereign shop ads               # status: the deck + when the next ad is allowed
sovereign shop advertise         # DRY-RUN preview of the next card
sovereign shop advertise --live  # post it (uses DISCORD_ADS_WEBHOOK_URL,
                                 # else DISCORD_WEBHOOK_URL)
```
Want it fully automatic? Add `export DISCORD_ADS_AUTO='1'` to your key file —
the fleet daemon (`sovereign bots daemon --live`) then posts on cadence by
itself. Re-word the ad lead-line anytime by writing
`<data>/advertising/copy.txt`. Tip: make a webhook for `#announcements` and
put it in `DISCORD_ADS_WEBHOOK_URL` so ads land there, not in the storefront.

---

## 💳 Phase 5 — Stripe: the products and Payment Links (~20 min, take your time)

**The one mental model that makes Stripe click:** you never create
subscriptions for people. You create each **product** with a **recurring
price** ONCE, generate a **Payment Link** (a checkout URL), and share the
link. When someone pays, Stripe *automatically* creates their subscription,
bills them monthly, retries failed cards, and handles cancellation. Your
Subscriptions tab fills up on its own.

Do this once per product — start with just **Basic, Pro, VIP** (the per-bot
plans can wait until someone asks for one):

### 5a. Create the product + price
1. Stripe Dashboard → **Product catalog** → **+ Add product**.
2. **Name:** `Basic` (later: `Pro`, `VIP`, `Restock Alert Bot`, …).
3. **Description** (shows at checkout): e.g. *"1 managed Discord alert bot,
   1 source, reliable 24/7 delivery."*
4. Pricing: **Recurring** · Amount `5.00` · USD · Billing period **Monthly**.
5. Click **Add product** (or Save).

*Setup fee?* (per-bot plans only): open the product → **+ Add another
price** → **One-off** · the setup amount (e.g. `30.00`). Same product, two
prices.

### 5b. Create the Payment Link
1. Open the product → **Create payment link** (or Payments → Payment links
   → **+ New**).
2. Line items: the **monthly price** (+ the one-off setup price if any).
3. **Options to switch ON** (this matters):
   - ☑ **Collect customers' email addresses** — how we'll match a payer to
     a Discord member (Round 2 automation needs it).
   - ☑ **Allow promotion codes** — powers the referral + loyalty rewards.
4. Click **Create link** → **Copy**.

### 5c. Give the link to Aria
```bash
sovereign shop set-link "Basic" 'https://buy.stripe.com/xxxx'
```
(Repeat 5a→5c for `Pro`, `VIP`.) Then re-publish so the cards become
clickable Subscribe buttons:
```bash
sovereign shop publish --live
```

### 5d. Turn on the Customer Portal (once)
Stripe → **Settings** → **Billing** → **Customer portal** → Activate.
This gives subscribers a self-serve page to cancel or update their card —
which is exactly what makes the cancellation lifecycle clean (they keep
access until the period they paid for ends; you'll see status changes in
your Stripe dashboard).

### 5e. Test the whole pipe (optional but recommended)
Stripe has a **test mode** toggle (top right of the dashboard). In test
mode, create a throwaway payment link and "pay" with card number
`4242 4242 4242 4242` (any future expiry, any CVC). Watch the subscription
appear in the Subscriptions tab. Switch back to live mode after.

---

## ⚙️ Phase 6 — Turn on the always-on engine (the fleet daemon)

**What:** the loop that runs the autonomous bots 24/7 — polls sources,
delivers alerts through the durable queue, retries, dead-letters. No
LLM/GPU; runs even while Aria's cockpit is closed ("your alerts never
sleep").

```bash
source ~/.config/sovereign-agent/shop.env
sovereign bots daemon                 # DRY-RUN: watches, sends nothing
sovereign bots daemon --live         # real deliveries (Ctrl-C or `sovereign halt` stops)
```
At startup it flags any bot that needs attention (🔴 no sources, failing
deliveries). Check anytime with `sovereign bots health` — or just ask Aria
*"do any bots need attention?"* in the cockpit.

*(A daemon only matters once a bot project has sources —
`sovereign bots add-source <project> <name> --url ... --kind rss|change|api
--interval 60`. Until then it idles harmlessly.)*

---

## 🔄 Phase 7 — Operating rhythm (what running the shop looks like)

**When someone subscribes** (Round 1, manual — ~30 seconds each):
1. Stripe emails you / shows it in Dashboard → Payments.
2. In Discord: right-click the member → Roles → tick their tier
   (`@Subscriber-Basic/Pro/VIP`). They instantly see the SUBSCRIBERS area.
3. Set up their bot: `sovereign bots add-source ...` for what they want
   watched. The daemon takes it from there.

**When someone cancels:** Stripe keeps them active until the period ends —
you'll see `canceled` at period end → untick their role. *(Round 2 — the
Stripe-polling reconciler — automates both grant and revoke; it's specced
and waiting whenever you want it.)*

**Weekly, or whenever:** `sovereign bots health` · `sovereign shop suggest
list` (what the community wants next — donation-boosted ideas float to the
top) · re-run `sovereign shop publish --live` after catalog changes.

---

## 🧰 Troubleshooting (the honest list, from real scars)

| Symptom | Cause → Fix |
|---|---|
| Webhook send fails `HTTPError` / 403 / `error code: 1010` | Discord's edge blocks anonymous senders. Already fixed in code (we send an identifying User-Agent). If you see it again, you're on an old build — `git pull` & reinstall. |
| Slash commands don't appear in Discord | ① The bot terminal isn't running. ② `DISCORD_GUILD_ID` unset → commands sync globally (up to ~1 hour). Set the guild id for instant sync. ③ Re-invite with the `applications.commands` scope ticked. |
| `/whoami` says you're not the owner | `DISCORD_OWNER_ID` mismatch — Developer Mode on → right-click your name → Copy User ID → fix the env file → restart the bot. |
| `/setup-shop` says done but roles look wrong | The bot's managed role sits **below** the roles it manages — drag "Aria" above the `@Subscriber-*` roles (Phase 1b step 5) and re-run. |
| `command not found: sovereign` | Use `.venv/bin/sovereign`, or activate the venv. Never system pip/python. |
| Publish goes to `#general` instead of `#storefront` | `DISCORD_SHOP_WEBHOOK_URL` unset in this terminal → `source ~/.config/sovereign-agent/shop.env`. |
| Aria shows 🌙 asleep while the cockpit is open | The heartbeat writes every ~5s and the awake window is 3 min — if it persists, the cockpit isn't actually running, or it's running against a different `--data-dir`. |
| A bot went quiet / alerts stopped | `sovereign bots health` names the reason (dead feed, webhook failing, daemon not running, dead-letters) — with link-rot evidence ("HTTP 404 ×N in a row"). `sovereign bots queue <project>` inspects; `--requeue-dead` retries after you fix the cause. |
| Are my stored keys still valid? | `sovereign keys check` — probes each webhook (a GET validates it **without posting**) and the bot token. 404 = deleted → rotate; 401 = re-copy. |
| Where did a guide/map go? | `sovereign docs` — the verified registry of all 17 docs; a missing one shows ❌ instead of being silently lost. Or ask Aria "where is the system map?". |
| You pasted a secret somewhere public | Rotate it: webhook → Delete Webhook + make a new one; bot token → Reset Token; Stripe link → deactivate the payment link in Stripe. All take under a minute. |

---

## ✅ The go-live checklist (print-worthy)

- [ ] **Phase 1** — admin bot online, `/whoami` = 👑, `/setup-shop` ran clean
- [ ] Bot's "Aria" role dragged above the subscriber roles
- [ ] **Phase 3** — `#storefront` + `#aria-status` webhooks in the env file
- [ ] **Phase 4** — storefront cards visible in `#storefront`; presence card in `#aria-status`
- [ ] **Phase 5** — Basic/Pro/VIP in Stripe with Payment Links, links set via `sov shop set-link`, re-published; Customer Portal ON
- [ ] **Phase 6** — daemon dry-run clean; `--live` when a customer's bot exists
- [ ] Pin a welcome message in `#welcome` + the Payment Links in `#order-here`
- [ ] Invite your first people 🎉

*Written with love by the whole team — Opus built the floor, Fable checked
the bolts. — for Kevin's shop.* 💛
