# STRIPE_LOCKIN.md — ✅ COMPLETED 2026-07-17

> **DONE.** Kevin created all 10 Payment Links; the catalog was synced to
> the FINAL live pricing (simpler than the original draft — no setup
> fees): Basic $5 · Pro $12 · VIP $25 · Restock $30/mo · News Feed
> $20/mo · Sports $30/mo · Reminder $20/mo · Welcome $30 once ·
> Reaction-Role $20 once · Custom Bot $50/mo. Storefront republished
> LIVE with buy buttons. Remaining niceties: the $5 self-purchase proof
> (Part 5) and rotating the Stripe key (the closing move). The original
> walkthrough stays below for reference / future products.

> **Where you are:** Discord is DONE. The shop catalog is loaded (10
> products, verified live). The storefront is published. **The single
> missing piece between you and money is: 10 Stripe Payment Links.**
> This doc is everything, verbose, in order. Budget ~45–60 minutes.
>
> **Golden rule:** make sure the Stripe dashboard toggle (top-right) says
> **LIVE mode**, not Test mode, before creating anything. A Test-mode
> Payment Link looks identical but can never charge a real card.

---

## Part 0 — one-time account checks (5 min)

1. Log in at https://dashboard.stripe.com → account **BigKevsBotShop**.
2. Top-right toggle: **Live mode ON** (orange "Test mode" banner = wrong).
3. If Stripe still asks for business verification (bank account, SSN/EIN,
   address), finish that FIRST — Payment Links won't pay out without it.
   Settings → Business → Bank accounts and scheduling.
4. **Turn on the Customer Portal** (lets subscribers cancel/update cards
   themselves — this feeds our cancellation lifecycle cleanly):
   Settings → Billing → Customer portal → **Activate**. Defaults are fine.
5. Optional but recommended: Settings → Tax → enable **Stripe Tax** (it
   adds sales tax automatically where required).

## Part 1 — create the 10 products (one recipe, repeated)

Dashboard → **Product catalog** → **+ Add product**. For each product
below: fill the name EXACTLY as written (the shop matches by name),
pricing model **Standard pricing**, currency **USD**.

- A **monthly price** = select **Recurring**, billing period **Monthly**.
- A **setup fee** = after saving the monthly price, open the product and
  **+ Add another price** → **One-off**. (Two prices on ONE product.)
- A **one-time product** = just one **One-off** price.

| # | Product name (exact) | Recurring price | One-off price |
|---|---|---|---|
| 1 | `Basic` | $5.00 / month | — |
| 2 | `Pro` | $12.00 / month | — |
| 3 | `VIP` | $25.00 / month | — |
| 4 | `Restock Alert Bot` | $8.00 / month | $30.00 setup |
| 5 | `News / Release Feed Bot` | $6.00 / month | $25.00 setup |
| 6 | `Sports Score Bot` | $8.00 / month | $30.00 setup |
| 7 | `Reminder / Schedule Bot` | $5.00 / month | $20.00 setup |
| 8 | `Welcome / Onboarding Bot` | — | $20.00 |
| 9 | `Reaction-Role Bot` | — | $20.00 |
| 10 | `Custom Bot (VIP build)` | $15.00 / month | $75.00 setup |

Blurbs (paste into the product Description if you like — optional,
customers see them on the checkout page):
- Basic/Pro/VIP: "Managed 24/7 Discord alert bots — hosted, watched, and
  kept alive for you."
- Per-bot plans: "Your own managed alert bot — setup + monthly hosting."
- Custom Bot: "A bot built to your spec with Aria — setup + hosting."

## Part 2 — create a Payment Link per product (the key part)

For EACH of the 10 products: open the product → its price → **Create
payment link** (or Payment Links → + New → pick the product).

For products WITH a setup fee (4, 5, 6, 7, 10): when creating the link,
**add BOTH prices** of that product to the same link (the monthly one and
the one-off setup) — one link, one checkout, charges setup + first month
together, then renews monthly on its own.

Settings on EVERY link (they're under "Options"/"After payment"):
- ✅ **Collect customers' email addresses** — ON (it's on by default).
  This is how we match a payer to their Discord member for role grants.
- ✅ **Allow promotion codes** — ON. (Referral rewards + giveaway coupons
  ride on this later — turning it on now costs nothing.)
- ❌ **Let customers adjust quantity** — OFF.
- After payment: **Show confirmation page** is fine. In the confirmation
  message, paste your Discord invite link so buyers land back in the
  server. (Later we can upgrade this to a custom redirect.)
- Everything else: leave defaults.

Click **Create link** → **copy the URL** (`https://buy.stripe.com/...`).
Paste each one somewhere temporary (or straight into Part 3 as you go) —
you need all 10.

## Part 3 — hand the links to Aria (2 minutes, copy-paste)

In a terminal, one line per product — paste YOUR real URLs:

```bash
cd /home/kmon/AA-Erebo/sovereign-agent

.venv/bin/sov shop set-link "Basic"                    "https://buy.stripe.com/XXXX"
.venv/bin/sov shop set-link "Pro"                      "https://buy.stripe.com/XXXX"
.venv/bin/sov shop set-link "VIP"                      "https://buy.stripe.com/XXXX"
.venv/bin/sov shop set-link "Restock Alert Bot"        "https://buy.stripe.com/XXXX"
.venv/bin/sov shop set-link "News / Release Feed Bot"  "https://buy.stripe.com/XXXX"
.venv/bin/sov shop set-link "Sports Score Bot"         "https://buy.stripe.com/XXXX"
.venv/bin/sov shop set-link "Reminder / Schedule Bot"  "https://buy.stripe.com/XXXX"
.venv/bin/sov shop set-link "Welcome / Onboarding Bot" "https://buy.stripe.com/XXXX"
.venv/bin/sov shop set-link "Reaction-Role Bot"        "https://buy.stripe.com/XXXX"
.venv/bin/sov shop set-link "Custom Bot (VIP build)"   "https://buy.stripe.com/XXXX"
```

Check they all landed (the `stripe` column stops saying `—`):

```bash
.venv/bin/sov shop list
```

## Part 4 — republish the storefront with buy buttons

```bash
.venv/bin/sov shop publish --live
```

That's it. The #storefront cards now carry real "buy" links. The shop can
take money.

## Part 5 — prove it end-to-end (recommended, 5 min)

1. Open the `Basic` payment link yourself and buy it with a real card
   ($5 — it's your own account; you can refund it right after from
   Dashboard → Payments → ⋯ → Refund, and cancel the subscription in
   Dashboard → Subscriptions).
2. Confirm: payment appears in the dashboard, the confirmation page shows
   your Discord invite, the email lands.
3. Manually grant yourself `Subscriber-Basic` in Discord — that's the
   step Round 2 automates.

## What happens AFTER (so you know it's handled — not your job today)

- **Role grants are manual for now**: buyer pays → you (or Aria on your
  word) assign `Subscriber-*`. The **Round-2 Stripe reconciler**
  (registered in the plan) automates grant/revoke from Stripe truth,
  handles cancellations (access until period end), failed-card grace,
  and reactivation. It will need ONE more thing from you when we build
  it: a **restricted API key** (Dashboard → Developers → API keys →
  Create restricted key, read-only on Subscriptions + Customers) vaulted
  as `STRIPE_SECRET_KEY` via `sov keys set STRIPE_SECRET_KEY`. Not now.
- **Referral/giveaway coupons**: Dashboard → Product catalog → Coupons,
  whenever we ship the referral round — promo codes are already ON.

## If something fights you

- Can't find "Add another price" → open the product page (not the create
  dialog); it's under the Pricing section.
- Link created in Test mode by mistake → recreate it in Live mode (links
  can't be moved across modes); delete the test one.
- `sov shop set-link` says "No such product" → run `.venv/bin/sov shop
  list` and copy the product name EXACTLY (quotes matter — several names
  contain spaces and slashes).
- A payment link 404s → it was deactivated in the dashboard (Payment
  Links page → toggle Active).
