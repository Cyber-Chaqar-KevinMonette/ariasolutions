# BigKev's Bot Shop — complete Discord server build guide

> **Start here instead:** `SETUP_MASTER.md` is the one ordered path through
> everything (and its Phase 1 admin bot can apply this file's permissions
> automatically via `/setup-shop`). This file stays as the deep reference
> for the server structure and the by-hand permission steps.

A click-by-click blueprint for the whole server: roles first, then channels,
then permissions, then the webhooks that connect Aria. Follow top to bottom.
Immersive but professional — a real storefront, not a clutter of channels.

---

## Step 1 — Roles (Server Settings → Roles → Create Role)

Create these **in this order** (Discord applies the top role's permissions
first; keep staff on top). For each, set a color so they read at a glance.

| Role | Color | Who | Purpose |
|---|---|---|---|
| `Aria` | teal | the webhook/bot | her identity in the server |
| `Owner` | gold | you | full admin |
| `@Veteran` | orange | 12mo+ subscribers | loyalty status (Round 2 auto) |
| `@Subscriber-VIP` | purple | VIP tier | all subscriber channels + ask-Aria |
| `@Subscriber-Pro` | blue | Pro tier | + priority support |
| `@Subscriber-Basic` | green | Basic tier | lounge + your-alerts + your-stats |
| `@Customer` | grey | one-time buyers | order + their delivery channel |
| `@everyone` | default | the public | welcome + shop only |

> Keep the subscriber roles **exactly** matching the `access_role` values in
> the shop catalog: `Subscriber-Basic` / `Subscriber-Pro` / `Subscriber-VIP`.
> Round 2's reconciler grants/revokes these automatically.

---

## Step 2 — Categories & channels (create categories, then channels inside)

### 📢 WELCOME  *(public, read-only except where noted)*
- `#welcome` — what the shop is, the "how it works" in 3 lines, a jump-link
  to `#storefront`.
- `#announcements` — Aria posts here (news, new bots). Read-only for public.
- `#how-it-works` — pick a bot → subscribe via Stripe → you're set up → alerts
  flow 24/7. One screen, no wall of text.

### 🛒 SHOP  *(public, read-only)*
- `#storefront` — **auto-published catalog + live stats** (Aria posts embeds
  here). Read-only for public. ← webhook target.
- `#pricing` — the tiers table + what each includes.
- `#live-demo` — a real demo bot posting sample alerts, so buyers *see* it work.

### 🟢 STATUS  *(public, read-only)*
- `#aria-status` — 🟢 awake / 🌙 asleep presence card. ← webhook target.

### 🎫 ORDERS  *(public can see, post allowed)*
- `#order-here` — how to order + a pinned message with the Payment Links.
- `#order-status` — you post confirmations; read-only for public.

### 💎 SUBSCRIBERS  *(role-gated — see the matrix in Step 3)*
- `#subscriber-lounge` — Basic+ community.
- `#priority-support` — Pro+ faster help.
- `#your-alerts` — their bot's private feed (Round 2: one webhook per customer).
- `#your-stats` — monthly usage digest (from `shop_stats.py`).
- `#early-access` — VIP only: previews, ask-Aria.

### 🔧 BACKEND  *(private — Owner + Aria only)*
- `#aria-control` — status, audit trail, your ops notes.

*(Optional later: a 🔊 Voice category with a "Support VC".)*

---

## Step 3 — Permissions, the simple way (no matrix, just clicks)

### Three things that make this easy
1. **You already see everything.** As the server **Owner** you bypass all
   permissions — you never add yourself anywhere. Ignore the `Owner` and
   `Aria` roles in every screen below. (Aria posts through webhooks, which
   don't need role permissions.)
2. **Only two toggles matter:** **View Channel** (can they see it) and
   **Send Messages** (can they type). Leave everything else on the grey `/`
   (neutral). Each toggle has three states — click to cycle:
   `✓` green = allow · `/` grey = neutral · `✗` red = deny.
3. **Categories flow downhill.** A permission set on a *category* is inherited
   by every channel inside it. So you configure **6 categories**, and only
   **3 channels** need a small tweak. That's the whole job.

To edit a category: right-click it → **Edit Category → Permissions**.
To add a role to the list: click **Add members or roles** and pick it.

---

### A) The public read-boards — WELCOME, SHOP, STATUS
*(everyone can read; only you post)*
Do this for **each** of the three categories:
- Edit Category → Permissions → click **`@everyone`** →
  - **View Channel → ✓ (green)**
  - **Send Messages → ✗ (red)**

That's it. The public can read every channel inside; nobody but you can post
(Aria's webhooks still post fine).

### B) ORDERS
*(readable by all; people can ask to order in one channel)*
- Edit Category → Permissions → **`@everyone`**: **View ✓**, **Send ✗**.
- Then open the **#order-here** channel → Edit Channel → Permissions →
  **`@everyone`**: **Send Messages → ✓**.
- (`#order-status` stays read-only automatically — leave it alone.)

### C) SUBSCRIBERS  — the private, paid area (the important one)
1. Edit Category → Permissions → **`@everyone`**: **View Channel → ✗ (red)**.
   → The whole category vanishes for the public.
2. Still in the category's Permissions, **Add members or roles** and add all
   three: **@Subscriber-Basic**, **@Subscriber-Pro**, **@Subscriber-VIP**.
   For **each** of them set **View Channel → ✓**.
   → Now every paying subscriber can see the subscriber channels.
3. Two channels get tightened (open the channel → Edit Channel → Permissions):
   - **#priority-support** → add **@Subscriber-Basic** → **View Channel → ✗**.
     (Hides it from Basic; Pro + VIP still see it.)
   - **#early-access** → add **@Subscriber-Basic** *and* **@Subscriber-Pro** →
     **View Channel → ✗** on both. (Only VIP sees it.)

### D) BACKEND  — just you
- Edit Category → Permissions → **`@everyone`**: **View Channel → ✗**.
- Done. You're the Owner, so you still see it. (No need to add yourself.)

---

### What each role ends up seeing (the reassuring recap)
| Role | Can see | Can post |
|---|---|---|
| **@everyone / public** | WELCOME · SHOP · STATUS · ORDERS | only `#order-here` |
| **@Customer** | same as public (their bot delivers to their own channel) | `#order-here` |
| **@Subscriber-Basic** | + lounge · your-alerts · your-stats | lounge |
| **@Subscriber-Pro** | Basic + **priority-support** | lounge, priority-support |
| **@Subscriber-VIP** | Pro + **early-access** (everything) | all subscriber ch. |
| **@Veteran** | loyalty badge — give it VIP-level access, or leave cosmetic | — |
| **Owner (you) · Aria** | everything (owner bypass; Aria = webhooks) | everything |

> You never touch `@Customer` or `@Veteran` in the permission screens for
> Round 1 — `@Customer` rides on public access, and `@Veteran` is just a
> badge until Round 2. The real work is **6 categories + 3 channel tweaks.**

---

## Step 4 — Webhooks (connect Aria; keep URLs in env vars, never in files)

For each channel below: **Edit Channel → Integrations → Webhooks → New
Webhook → name it "Aria" → Copy URL**, then set the env var.

| Channel | Env var | Used by |
|---|---|---|
| `#general` (done) | `DISCORD_WEBHOOK_URL` | base / `sov bots ping` |
| `#storefront` | `DISCORD_SHOP_WEBHOOK_URL` | `sov shop publish` |
| `#aria-status` | `DISCORD_STATUS_WEBHOOK_URL` | presence cards |

Each falls back to `DISCORD_WEBHOOK_URL` if unset. Set them the safe way
(they never touch the repo):
```
export DISCORD_SHOP_WEBHOOK_URL='...'
export DISCORD_STATUS_WEBHOOK_URL='...'
sov shop seed && sov shop publish --live        # storefront goes up
sov shop presence --publish --live               # her status card goes up
```

---

## Step 5 — Stripe subscriptions, in plain English (you found this confusing — here's the simple path)

You do **not** create subscriptions one-by-one for each customer. You create
**products with recurring prices once**, generate a **Payment Link** for each,
and share the link. Stripe does all the billing. Steps:

1. **Stripe → Product catalog → Add product.**
   - Name: `Basic` (repeat later for Pro, VIP, each bot).
   - Under **Pricing**: amount `5.00`, currency `USD`, **Recurring**, billing
     period **Monthly**. Save.
   - *(Setup fee?)* Add a **second price** on the same product: amount `30.00`,
     **One-time**. (Only for bots that have a setup fee.)
2. **Create a Payment Link** (Product catalog → the product → "Create payment
   link", or Payments → Payment Links → New).
   - Add the recurring price (and the one-time setup price if any) as line items.
   - Turn **ON: "Collect customer email"** and **"Allow promotion codes."**
   - Leave quantity fixed. Create → **Copy link.**
3. **Give Aria the link:** `sov shop set-link "Basic" 'https://buy.stripe.com/...'`
   (or paste it in the Shop Studio). Repeat per product.
4. **Turn on the Customer Portal** (Stripe → Settings → Billing → Customer
   portal → activate). This lets subscribers cancel/update their card
   themselves — which is what makes the cancellation flow clean.

That's it. A "subscription" in Stripe's Subscriptions tab gets created
**automatically** the moment someone pays through your Payment Link — you
don't hand-create them. (The screen you saw is for manually billing a
specific customer; you won't usually use it.)

---

## Step 6 — Go-live checklist
- [ ] Roles created (subscriber names match the catalog exactly)
- [ ] Categories + channels created, SUBSCRIBERS + BACKEND private
- [ ] Permissions matrix applied; `#priority-support`/`#early-access` tightened
- [ ] Webhooks created + env vars exported
- [ ] `sov shop seed` → set Stripe links → `sov shop publish --live`
- [ ] Stripe products + Payment Links live, Customer Portal on
- [ ] A test subscribe → you grant the role (Round 1) → they see SUBSCRIBERS

When Round 2 lands, the role-grant/revoke becomes automatic (Stripe-poll
reconciler + discord.py bot). Until then it's one manual click per new
subscriber — a fine floor to start on.
