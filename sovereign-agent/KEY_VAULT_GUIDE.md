# 🔐 The Key Vault Guide — every secret, safe, in one place

> The Key Vault is where Aria keeps her credentials — webhook URLs, the bot
> token, IDs, and any key a future bot needs. This guide is the whole story:
> what it is, why it's safe, exactly how to use it, and what to do when a
> key goes bad. Written for Kevin; no prior knowledge assumed.

---

## The one mental model

**A secret goes in ONCE, through a hidden prompt, and after that you only
ever see it masked** (`••••last4`). Everything in the system asks the vault
by NAME (`DISCORD_BOT_TOKEN`), never by value — so secrets never appear in
the repo, in chat, in logs, in Discord, or on your screen.

Where it physically lives: **one file, on this machine only** —

```
~/.config/sovereign-agent/shop.env      (permissions 0600 = only you can read it)
```

It's a plain env file, so you can also `source` it in a terminal before
running the bot. Nothing syncs it anywhere. Deleting a line from it removes
the secret. (Advanced: `ARIA_KEYS_FILE=/path` points the vault somewhere
else — you won't need this.)

---

## The two doors (pick either — same vault)

### Door 1 — inside Aria's cockpit: `/keys`
Launch the cockpit (`sovereign cockpit`), type **`/keys`** (or find
**🔐 Key Vault** in the ☰ menu). You get the status board: every key the
system knows about, what feature it unlocks, whether it's set (masked), and
an input to add/update one. Esc or ✕ closes it.

**Getting the value in:** copy the secret wherever it lives, then click
**📋 paste from clipboard** — it lands straight in the masked field (you'll
see a "pasted N characters" note, never the value). Keyboard paste works
too, but terminals are quirky about it: it's usually **Ctrl+Shift+V** or
**right-click**, not Ctrl+V. The 📋 button sidesteps all of that.

### Door 2 — the terminal: `sov keys …`

```bash
sov keys status              # the board: what's set (masked) + what each unlocks
sov keys set DISCORD_BOT_TOKEN    # prompts for the value with HIDDEN typing
sov keys unset OLD_KEY_NAME       # remove one
sov keys check               # liveness probe: are the stored keys still VALID?
```

**`sov keys set` is the important one.** It prompts — you paste the secret,
the typing is invisible, nothing lands in your shell history. It validates
the shape (a webhook must look like a webhook, a bot token like a token) and
warns you if something looks off. Then it's stored, `0600`, done.

---

## The keys the shop uses (the catalog)

| Key | What it is | Where you get it | Unlocks |
|---|---|---|---|
| `DISCORD_WEBHOOK_URL` | base webhook (#general) | channel ⚙ → Integrations → Webhooks | `bots ping`, fleet delivery, fallback for everything |
| `DISCORD_SHOP_WEBHOOK_URL` | #storefront webhook | same, on #storefront | `sov shop publish` |
| `DISCORD_STATUS_WEBHOOK_URL` | #aria-status webhook | same, on #aria-status | presence cards 🟢/🌙 |
| `DISCORD_ADS_WEBHOOK_URL` | ads webhook (suggest #announcements) | same, on that channel | 📣 `sov shop advertise` |
| `DISCORD_BOT_TOKEN` | the admin bot's password | dev portal → Bot → Reset Token | the whole admin bot: `/setup-shop`, `/ask`, welcome, scans |
| `DISCORD_OWNER_ID` | YOUR Discord user id | Discord → Settings → Advanced → Developer Mode ON → right-click your name → Copy User ID | the owner gate (only you can admin) |
| `DISCORD_GUILD_ID` | the server's id | right-click the server icon → Copy Server ID | instant slash-command sync |
| `STRIPE_SECRET_KEY` | Stripe API key | Stripe dashboard → Developers → API keys | Round 2 auto-roles (not needed yet) |

**Custom keys for future bots:** any name works (`sov keys set MY_API_KEY`).
Convention for per-bot keys: **`BOT_<SLUG>_<WHAT>`**, e.g.
`BOT_POKEMON_RESTOCK_API_KEY` — the vault scales to thousands of keys
without slowing (proven in tests at 2,000).

---

## Getting YOU ready (the 5-minute path, in order)

```bash
# 1. See where you stand — which keys are set, which features are waiting
sov keys status

# 2. Store the bot token (from the dev portal → Bot → Reset Token → Copy)
sov keys set DISCORD_BOT_TOKEN

# 3. Store your identity + the server
sov keys set DISCORD_OWNER_ID
sov keys set DISCORD_GUILD_ID

# 4. Store the webhooks you've made so far (each channel ⚙ → Integrations)
sov keys set DISCORD_WEBHOOK_URL
sov keys set DISCORD_SHOP_WEBHOOK_URL       # when you make #storefront's
sov keys set DISCORD_STATUS_WEBHOOK_URL     # when you make #aria-status's

# 5. Prove they're alive (no posts are made — a webhook is validated by a
#    read-only GET; the token via Discord's "who am I" endpoint)
sov keys check

# 6. Load them into a terminal and start the bot
source ~/.config/sovereign-agent/shop.env
sov discord-admin run
```

The two intent switches also live in this file — add them once, with the
matching portal toggles ON (dev portal → Bot → Privileged Gateway Intents):

```bash
echo "export DISCORD_ENABLE_CHAT_INTENT='1'"    >> ~/.config/sovereign-agent/shop.env
echo "export DISCORD_ENABLE_MEMBERS_INTENT='1'" >> ~/.config/sovereign-agent/shop.env
```

---

## When a key goes bad (rotation — 60 seconds)

`sov keys check` says ✗, or a bot's health report says "credentials need
updating"? That's the system catching it for you. The fix is always:

1. **Make the replacement** at the source (Discord: delete the old webhook,
   create a new one · dev portal: Reset Token — the old one dies instantly).
2. **`sov keys set <NAME>`** → paste the new value.
3. **`sov keys check`** → ✓ alive. Done — nothing else to update, because
   everything reads by name.

Rotate immediately if a value was ever pasted somewhere visible (chat, a
screenshot, a stream). Rotation is cheap; treat it as routine, not an
emergency.

---

## The safety properties (why you can trust this)

- **Hidden input** — `sov keys set` prompts; values skip your shell history.
- **Masked always** — every display shows `••••last4`, never the value.
  Even Aria's customer chat scrubs real vault values from replies (▮▮▮).
- **Local only, 0600** — one file, your user, this machine. No cloud, no sync.
- **Read by name** — code and configs reference `$NAMES`; the repo contains
  zero secrets, so `git push` can never leak one.
- **Liveness without exposure** — `sov keys check` validates a webhook with
  a GET (posts nothing) and the token with a "who am I" call; values go to
  Discord only, over HTTPS.
- **She tells you when something's wrong** — dead webhooks/tokens surface in
  `sov keys check`, in `sov bots health`, and in her chat ("which keys are
  missing?").

## Troubleshooting

| Symptom | Fix |
|---|---|
| `sov keys check` → ✗ webhook 404 | webhook deleted in Discord → make a new one, `sov keys set` |
| `✗ DISCORD_BOT_TOKEN — 401` | token reset/expired → dev portal Reset Token, `sov keys set` |
| bot says "No bot token in $DISCORD_BOT_TOKEN" | you didn't `source ~/.config/sovereign-agent/shop.env` in THIS terminal |
| a warning at `set` time ("doesn't look like…") | you probably pasted the wrong thing (a channel URL isn't a webhook URL) |
| key shows in `status` but a feature can't see it | same `source` issue — the vault file must be loaded into the terminal that runs the feature |
