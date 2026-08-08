# KEY_GATHERING.md — gather your API keys, one at a time

> **You don't need any of these to run the shop today.** The scout, the
> trackers, weather, and the storefront all work right now on free,
> keyless public data. These keys UNLOCK the next tier: real per-store
> stock, store addresses + distance, price comps, and higher rate limits.
> Grab them whenever you want, in any order.
>
> **The honest part:** a program can't legitimately fetch these for you —
> every provider makes a human sign up and accept their terms (auto-signup
> would break their rules, which we never do). So Aria is your *concierge*:
> she gives you the exact link, steps, and safest scope, then **validates
> the key live and vaults it** the moment you paste it. Everything below is
> a real, free, ToS-compliant developer program.

**How to vault any key** (after you copy it from the provider):
```bash
sov keys onboard <slug>      # walks you through it + validates + stores
# or in the cockpit: /keys → 📋 paste (Ctrl+V works) → 💾
```
Keys are stored at `~/.config/sovereign-agent/shop.env` (chmod 0600,
masked on screen, never in the repo or chat). Check any key anytime with
`sov keys check`.

---

## ✅ Already working — nothing to gather (keyless / public)
- **Weather** — Open-Meteo. Free, no key, no account. Live in `/ask`, `/ma`.
- **Deal + restock feeds** — Slickdeals + Reddit RSS. Free, keyless. Powers
  all 32 trackers today. (The Reddit key below just *raises the limit* —
  it's not required.)

---

## 1. Reddit API  ·  slug: `reddit`  ·  free, ~5 min
**Unlocks:** higher rate limits for the trackers — ends the HTTP 429
throttling we hit polling many niches; more legitimate than plain RSS.

1. Log in to Reddit, open **https://www.reddit.com/prefs/apps**
2. Scroll down → **"are you a developer? create an app…"**
3. Name: `BigKevsBotShop-Scout` · type: **script**
4. redirect uri: `http://localhost:8080` (unused, but the form requires one)
5. **Create app.** The string *under the app name* is your **CLIENT ID**;
   the **secret** field is your **CLIENT SECRET**
6. `sov keys onboard reddit` → paste the id, then the secret

**Scope:** none (a "script" app is read-only by design). Safe.

---

## 2. Best Buy Developer API  ·  slug: `bestbuy`  ·  free, ~5–10 min
**Unlocks:** real product availability + **per-store stock** — the true
local lane (is it in stock at *your* store, pickup vs ship).

1. Open **https://developer.bestbuy.com/** → **Get API Key**
2. Sign up (email + basic info), confirm your email
3. Your API key appears on the dashboard immediately
4. `sov keys onboard bestbuy` → paste it

**Scope:** Products + Stores, read-only (the default). Rate limit 5/sec,
50k/day — plenty. This is the single biggest unlock for local finds.

---

## 3. Google Places / Geocoding API  ·  slug: `google-maps`  ·  free tier, ~15 min
**Unlocks:** store **addresses** + **closest→farthest distance** from a
member's zip — the "which Targets near me, nearest first, with addresses"
feature you asked for.

1. Open **https://console.cloud.google.com/** → create a project
2. **APIs & Services → Enable APIs** → enable **Places API** + **Geocoding
   API**
3. Add a **billing account** (the free monthly credit covers scout use;
   **set a budget cap of $1** so it can never actually charge you)
4. **Credentials → Create credentials → API key** → copy it
5. **RESTRICT the key** (API restrictions → Places + Geocoding only) so a
   leak is harmless
6. `sov keys onboard google-maps` → paste it

**Scope:** restrict to Places + Geocoding only. The billing step is the
only slow part; the budget cap keeps it free.

---

## 4. eBay Developer API  ·  slug: `ebay`  ·  free, ~10 min
**Unlocks:** sold/active listing comps → "is this deal actually good?"
pricing intelligence beside each find.

1. Open **https://developer.ebay.com/join** → create a developer account
2. **Application Keys** → create a **PRODUCTION** keyset
3. Copy the **App ID (Client ID)**
4. `sov keys onboard ebay` → paste it

**Scope:** Browse API (public data — no user login needed). Safe.

---

## 5. Stripe restricted key  ·  slug: `stripe`  ·  free, ~5 min
**Unlocks:** Round-2 auto-roles — buyers get their Subscriber/Tracker role
automatically; cancellations handled. (Not needed for Payment Links, which
already work.)

1. **Stripe Dashboard → Developers → API keys**
2. **Create restricted key** → read-only on **Subscriptions + Customers**
3. Copy it (starts with `rk_live_`)
4. `sov keys onboard stripe` → paste it

**Scope:** restricted, read-only. A restricted key can't move money even if
leaked — always prefer it over the full secret key.

---

## After you gather some
- `sov keys onboard` (no argument) — shows what's **unlocked vs waiting**.
- `sov keys check` — probes every stored key live (✓ alive / ✗ re-issue).
- Each key auto-lights its feature; I'll wire the deferred lanes (real
  local stock, Target addresses/distance, price comps, no-429 Reddit) to
  read these keys the moment they're vaulted.

*Priority if you only grab a couple:* **Best Buy** (real local stock) and
**Reddit** (kills the rate-limit throttling) give the most immediately
visible improvement. Google Maps is the one that delivers the exact
"nearest Targets with addresses" ask. 💛
