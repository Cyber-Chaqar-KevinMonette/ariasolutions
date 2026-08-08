"""credentials — the Key Vault: her tokens and keys, kept safe and local.

Kevin's ask: a place inside Aria where he can hand her credentials (bot
token, webhook URLs, Stripe keys) and she puts them in the env file safely.
The rules, enforced in code, not by promise:

  • **One private file** — `~/.config/sovereign-agent/shop.env`, created and
    kept at mode 0600 (only Kevin's user can read it). Never inside the repo,
    never inside `<data>` (which gets backed up/synced), never printed.
  • **Write-only from her side** — once stored, a secret is only ever shown
    MASKED (`••••last4`). No screen, CLI, or chat path renders a full value
    back. Reading full values is for the programs that need them (via
    `source` / os.environ), not for display.
  • **The catalog teaches** — every known credential carries what it is,
    which feature needs it, where to get it, and a light format check
    (warn-only, never blocks). "What's missing?" has a real answer.
  • **Atomic + preserving** — rewrites keep comments/unknown lines intact,
    write to a tmp file, fsync, replace, re-chmod 0600.

Tests point the vault elsewhere via the `ARIA_KEYS_FILE` env override.
"""
from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    "CredSpec",
    "CRED_CATALOG",
    "env_path",
    "read_env",
    "set_secret",
    "remove_secret",
    "mask",
    "vault_status",
    "validate_value",
    "compose_credentials_report",
    "is_credentials_query",
    "last_set_at",
    "relative_time",
]


@dataclass(frozen=True)
class CredSpec:
    name: str                 # the env var name
    label: str                # human name
    required_for: str         # which feature needs it
    what: str                 # one-line description
    where: str                # where Kevin gets it
    hint: str = ""            # expected format (validator hint)


CRED_CATALOG: list[CredSpec] = [
    CredSpec("DISCORD_WEBHOOK_URL", "Base/ops webhook (#aria-control)", "bots ping / fleet delivery",
             "The posting key Aria uses for ops messages + as the fallback "
             "for every other webhook. Point it at your private #aria-control.",
             "Discord: Edit Channel → Integrations → Webhooks → Copy URL",
             "https://discord.com/api/webhooks/..."),
    CredSpec("DISCORD_SHOP_WEBHOOK_URL", "Storefront webhook (#storefront)", "sov shop publish",
             "Where the storefront catalog cards are posted.",
             "Same as above, on the #storefront channel",
             "https://discord.com/api/webhooks/..."),
    CredSpec("DISCORD_STATUS_WEBHOOK_URL", "Status webhook (#aria-status)", "presence cards",
             "Where her 🟢 awake / 🌙 asleep card is posted.",
             "Same as above, on the #aria-status channel",
             "https://discord.com/api/webhooks/..."),
    CredSpec("DISCORD_ADS_WEBHOOK_URL", "Ads webhook (#announcements)", "📣 sov shop advertise",
             "Where the rotating promo cards land (max one per 6h, by "
             "construction).",
             "Same as above, on the #announcements channel",
             "https://discord.com/api/webhooks/..."),
    # affiliate-section-d (Kevin, 2026-07-25): "add an affiliates section
    # in the discord" — a dedicated channel for the referral program pitch
    # + live leaderboard (referrals.publish_affiliate_section).
    CredSpec("DISCORD_AFFILIATE_WEBHOOK_URL", "Affiliates webhook (#affiliates)",
             "referrals.publish_affiliate_section",
             "Where the referral-program pitch and live leaderboard are "
             "posted — a real home for /refer beyond slash commands.",
             "Same as above, on a dedicated #affiliates channel",
             "https://discord.com/api/webhooks/..."),
    CredSpec("DISCORD_BOT_TOKEN", "Admin bot token", "admin bot (/setup-shop)",
             "The admin bot's login secret — treat it like a password.",
             "discord.com/developers → your app → Bot → Reset Token → Copy",
             "long string, no spaces"),
    CredSpec("DISCORD_OWNER_ID", "Your Discord user id", "admin bot owner gate",
             "The ONLY account allowed to run server-editing commands.",
             "Discord: Settings → Advanced → Developer Mode, then right-click your name → Copy User ID",
             "digits only"),
    CredSpec("DISCORD_GUILD_ID", "Your server id", "instant slash-command sync",
             "Which server the admin bot syncs its commands to.",
             "Right-click the server icon → Copy Server ID",
             "digits only"),
    CredSpec("DISCORD_ENABLE_CHAT_INTENT", "Free-chat switch", "chat in #ask-aria + DMs",
             "Set to 1 so people can just TYPE to Aria (no /ask needed). "
             "Flip the portal toggle FIRST or her login fails.",
             "discord.com/developers → your app → Bot → Message Content Intent ON, then set this to 1",
             "1 (on) or 0 (off)"),
    CredSpec("DISCORD_ENABLE_MEMBERS_INTENT", "Welcome switch", "👋 greeting new members",
             "Set to 1 so Aria welcomes each new member (once ever, #welcome + DM). "
             "Flip the portal toggle FIRST or her login fails.",
             "discord.com/developers → your app → Bot → Server Members Intent ON, then set this to 1",
             "1 (on) or 0 (off)"),
    CredSpec("DISCORD_ADS_AUTO", "Auto-ads switch", "daemon posts ads on cadence",
             "Set to 1 and a LIVE fleet daemon advertises by itself — never "
             "more than one ad per 6h, structurally.",
             "your call — no portal step needed",
             "1 (on) or 0 (off)"),
    CredSpec("DISCORD_DEMO_WEBHOOK_URL", "Scout webhook (#live-demo)",
             "🔭 tcg-scout deliveries",
             "The flagship scout posts its finds here. Self-minted by "
             "/setup-webhooks — you never touch the URL.",
             "run /setup-webhooks in Discord (owner)",
             "https://discord.com/api/webhooks/…"),
    # owner-bridge-catalog-d (Kevin, 2026-07-25): "she used to send me
    # updates... she stopped." Root cause candidate — this webhook was
    # NEVER cataloged, so it was invisible to /keys AND never covered by
    # sov keys check's automatic webhook-liveness probing (which only
    # scans CATALOG entries ending _WEBHOOK_URL). A recreated #owner-
    # bridge channel (a new webhook URL) would silently break
    # work_narrator.py's narration with zero visibility anywhere.
    CredSpec("DISCORD_OWNER_WEBHOOK_URL", "Owner bridge webhook (#owner-bridge)",
             "work_narrator (live cockpit narration) + session close-out updates",
             "Where her live cockpit narration and end-of-session work "
             "updates post — your private two-way channel with her. "
             "Self-minted by /setup-webhooks — you never touch the URL.",
             "run /setup-webhooks in Discord (owner)",
             "https://discord.com/api/webhooks/…"),
    CredSpec("STRIPE_SECRET_KEY", "Stripe secret key", "Round 2 auto-roles",
             "Lets the reconciler read subscription status to grant/revoke "
             "roles. A RESTRICTED key (read-only Subscriptions+Customers) is "
             "the safest choice.",
             "Stripe Dashboard → Developers → API keys (restricted: Create "
             "restricted key)",
             "starts with sk_live_ or rk_live_"),
    # passes-d (Kevin, 2026-07-26): "put new public API keys inside of the
    # system." Genuinely public/safe-to-expose — distinct from the secret
    # key above — not consumed by anything yet (Payment Links need no
    # client-side Stripe.js), tracked now so it's ready if a future custom
    # checkout surface wants it.
    CredSpec("STRIPE_PUBLISHABLE_KEY", "Stripe publishable key",
             "future client-side checkout (not used yet)",
             "The public key safe to expose client-side — NOT a secret. "
             "Not required by anything today; the passes/shop system uses "
             "static Payment Links, which need no publishable key at all.",
             "Stripe Dashboard → Developers → API keys (the 'Publishable key' "
             "row, right above the secret key)",
             "starts with pk_live_ or pk_test_"),
    # passes-d: "channels for direct purchase links" — the plain (non-
    # personalized) Payment Link per active product, kept fresh in
    # #buy-links; /buy and /passes give the recommended personalized link.
    CredSpec("DISCORD_BUYLINKS_WEBHOOK_URL", "Buy-links webhook (#buy-links)",
             "shop.publish_buy_links",
             "Where the direct (non-personalized) Payment Link per active "
             "product is posted. Self-minted by /setup-webhooks — you "
             "never touch the URL.",
             "run /setup-webhooks in Discord (owner)",
             "https://discord.com/api/webhooks/…"),
    # concierge-d: the provider API keys (guided via `sov keys onboard`)
    CredSpec("REDDIT_CLIENT_ID", "Reddit app id", "higher tracker rate limits",
             "Ends the HTTP 429 throttling on the deal/restock trackers.",
             "reddit.com/prefs/apps → create a 'script' app (or: sov keys "
             "onboard reddit)", "short string"),
    CredSpec("REDDIT_CLIENT_SECRET", "Reddit app secret", "higher tracker rate limits",
             "The secret half of the Reddit script app.",
             "same app page — the 'secret' field", "string, no spaces"),
    CredSpec("BESTBUY_API_KEY", "Best Buy API key", "real per-store stock",
             "Real product + per-store availability — the true local lane.",
             "developer.bestbuy.com → Get API Key (or: sov keys onboard bestbuy)",
             "alphanumeric key"),
    CredSpec("GOOGLE_MAPS_API_KEY", "Google Maps key", "store addresses + distance",
             "Store addresses + closest→farthest distance (Target-address "
             "feature). RESTRICT it to Places + Geocoding.",
             "console.cloud.google.com → enable Places+Geocoding → API key "
             "(or: sov keys onboard google-maps)", "starts with AIza"),
    CredSpec("EBAY_APP_ID", "eBay App ID", "price comps on finds",
             "Sold/active listing comps → 'is this deal actually good?'.",
             "developer.ebay.com/join → production keyset → App ID (or: sov "
             "keys onboard ebay)", "long dashed string"),
    # lego-d (Kevin, 2026-07-18): the honest LEGO lanes — set DATA via
    # Brickset (free key), marketplace prices via BrickLink (OAuth set).
    CredSpec("BRICKSET_API_KEY", "Brickset API key", "LEGO set data",
             "Official LEGO set metadata — retiring dates, RRP, themes — "
             "to enrich the 🧱 LEGO tracker's finds.",
             "brickset.com/tools/webservices/requestkey (or: sov keys "
             "onboard brickset)", "alphanumeric key"),
    CredSpec("BRICKLINK_CONSUMER_KEY", "BrickLink consumer key",
             "LEGO marketplace prices",
             "BrickLink price-guide comps — what sets ACTUALLY sell for.",
             "bricklink.com/v2/api/register_consumer.page (or: sov keys "
             "onboard bricklink)", "alphanumeric key"),
    CredSpec("BRICKLINK_CONSUMER_SECRET", "BrickLink consumer secret",
             "LEGO marketplace prices",
             "The secret half of the BrickLink consumer pair.",
             "same BrickLink API page", "string, no spaces"),
    CredSpec("BRICKLINK_TOKEN", "BrickLink access token",
             "LEGO marketplace prices",
             "The OAuth access token BrickLink issues with the keyset.",
             "same BrickLink API page", "string, no spaces"),
    CredSpec("BRICKLINK_TOKEN_SECRET", "BrickLink token secret",
             "LEGO marketplace prices",
             "The OAuth token secret — the last of BrickLink's four values.",
             "same BrickLink API page", "string, no spaces"),
    # cloud-mode-d (Kevin, 2026-07-25): "let's add a fast free cloud mode?"
    # Cloud mode (/cloud on) already works keyless (Pollinations/LLM7/OVH/
    # Kilo, no key needed) via freellmpool — these two just make it FAST.
    # Neither is required for cloud mode to function at all; either one
    # (Kevin has Groq) upgrades it from ~40-65s/call to sub-second.
    CredSpec("GROQ_API_KEY", "Groq API key", "fast lane for cloud mode",
             "Groq's free tier is one of the fastest LLM APIs available — "
             "adding this key upgrades Fast Free Cloud mode (/cloud on) "
             "from the slow keyless providers to near-instant replies.",
             "console.groq.com → API Keys → Create API Key",
             "starts with gsk_"),
    CredSpec("CEREBRAS_API_KEY", "Cerebras API key", "fast lane for cloud mode",
             "Cerebras' free tier is fast with a large daily cap — a second "
             "fast option for Fast Free Cloud mode alongside Groq.",
             "cloud.cerebras.ai → API Keys → Create API Key",
             "alphanumeric key"),
    # affiliate-links-d (Kevin, 2026-07-25): third-party affiliate links,
    # Amazon Associates only for now. affiliate_links.tag_url() reads this
    # to tag every amazon.* link the scout system already posts; unset =
    # every link passes through completely untouched, never guessed.
    CredSpec("AMAZON_ASSOCIATE_TAG", "Amazon Associates tag",
             "affiliate_links.tag_url (third-party affiliate links)",
             "Your Amazon Associates tracking id — every amazon.* link the "
             "scout/deal-tracker system posts gets this appended as ?tag=. "
             "Unset means links post exactly as found, untagged.",
             "affiliate-program.amazon.com → your Associates account → "
             "Account Number / Store ID",
             "ends in -20 or -21"),
]
_CATALOG_BY_NAME = {c.name: c for c in CRED_CATALOG}

_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def env_path() -> Path:
    """The vault file. `ARIA_KEYS_FILE` overrides (tests; alt locations)."""
    override = (os.environ.get("ARIA_KEYS_FILE") or "").strip()
    if override:
        return Path(override)
    return Path.home() / ".config" / "sovereign-agent" / "shop.env"


def _unquote(raw: str) -> str:
    """Undo shell quoting — including POSIX `'a'\"'\"'b'` concatenation, so a
    value we wrote with an embedded quote reads back exactly. shlex is the
    real shell-quoting parser; fall back to naive stripping on weird input."""
    raw = raw.strip()
    try:
        import shlex
        parts = shlex.split(raw)
        if parts:
            return parts[0]
    except Exception:  # noqa: BLE001
        pass
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return raw[1:-1]
    return raw


def read_env(path: Path | None = None) -> dict[str, str]:
    path = path or env_path()
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#"):
                continue
            m = _LINE_RE.match(line)
            if m:
                out[m.group(1)] = _unquote(m.group(2))
    except Exception:  # noqa: BLE001
        pass
    return out


def _quote(value: str) -> str:
    # single-quote, escaping embedded single quotes the POSIX way
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        try:
            os.close(fd)
        except Exception:  # noqa: BLE001
            pass
        raise
    tmp.replace(path)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)   # 0600, always


# last-set-timestamp-d (Kevin, 2026-07-25): "I want to know when the last
# time a key was rotated or applied." A small SEPARATE metadata file next
# to the vault (never mixed into shop.env itself, which stays plain
# shell-sourceable) — name -> ISO-8601 UTC timestamp of the last set_secret
# call. Same atomic-write + 0600 discipline as the vault file; holds only
# names and timestamps, never a value.
def _meta_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".meta.json")


def _read_meta(path: Path) -> dict[str, str]:
    mp = _meta_path(path)
    try:
        data = json.loads(mp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _write_meta(path: Path, data: dict[str, str]) -> None:
    _write_file(_meta_path(path), json.dumps(data, indent=2, sort_keys=True) + "\n")


def _touch_meta(name: str, path: Path) -> None:
    meta = _read_meta(path)
    meta[name] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_meta(path, meta)


def _drop_meta(name: str, path: Path) -> None:
    meta = _read_meta(path)
    if name in meta:
        del meta[name]
        _write_meta(path, meta)


def last_set_at(name: str, path: Path | None = None) -> str | None:
    """ISO-8601 UTC timestamp of the last time this key was set, or None if
    it's never been set (or was set before this feature existed)."""
    path = path or env_path()
    return _read_meta(path).get((name or "").strip().upper())


def relative_time(iso_ts: str | None, *, now: datetime | None = None) -> str:
    """A human line for the vault UI: "just now", "5m ago", "3h ago",
    "2d ago", or a plain date once it's old enough that "Nd ago" stops
    being useful. Never raises on a malformed timestamp."""
    if not iso_ts:
        return "never"
    try:
        then = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return "unknown"
    now = now or datetime.now(timezone.utc)
    delta = (now - then).total_seconds()
    if delta < 0:
        return then.strftime("%Y-%m-%d %H:%M UTC")
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    if delta < 30 * 86400:
        return f"{int(delta // 86400)}d ago"
    return then.strftime("%Y-%m-%d")


def set_secret(name: str, value: str, path: Path | None = None) -> None:
    """Store/replace one secret. Preserves every other line and comment."""
    name = (name or "").strip().upper()
    if not _NAME_RE.match(name):
        raise ValueError("key name must be UPPER_SNAKE (letters/digits/_ , 3-64 chars)")
    value = (value or "").strip()
    if not value:
        raise ValueError("value is empty — nothing stored")
    if "\n" in value:
        raise ValueError("value must be a single line")
    path = path or env_path()
    new_line = f"export {name}={_quote(value)}"
    lines: list[str] = []
    replaced = False
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _LINE_RE.match(line)
            if m and m.group(1) == name and not line.lstrip().startswith("#"):
                if not replaced:
                    lines.append(new_line)
                    replaced = True
                continue   # drop duplicate assignments of the same name
            lines.append(line)
    else:
        lines = ["# Aria's Key Vault — private credentials. NEVER commit or share.",
                 "# Load into a terminal with:  source " + str(path)]
    if not replaced:
        lines.append(new_line)
    _write_file(path, "\n".join(lines) + "\n")
    _touch_meta(name, path)
    # make it live for THIS process too (daemon/bot started from the cockpit)
    os.environ[name] = value


def remove_secret(name: str, path: Path | None = None) -> bool:
    name = (name or "").strip().upper()
    path = path or env_path()
    if not path.is_file():
        return False
    lines, removed = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _LINE_RE.match(line)
        if m and m.group(1) == name and not line.lstrip().startswith("#"):
            removed = True
            continue
        lines.append(line)
    if removed:
        _write_file(path, "\n".join(lines) + "\n")
        _drop_meta(name, path)
        os.environ.pop(name, None)
    return removed


def mask(value: str) -> str:
    """The ONLY way a stored value is ever displayed."""
    v = (value or "").strip()
    if not v:
        return "(not set)"
    if len(v) <= 8:
        return "••••(set)"
    return "••••" + v[-4:]


def validate_value(name: str, value: str) -> list[str]:
    """Light, WARN-ONLY format checks — they never block a save."""
    warnings: list[str] = []
    v = (value or "").strip()
    if name.endswith("WEBHOOK_URL") and not v.startswith("https://discord.com/api/webhooks/"):
        warnings.append("doesn't look like a Discord webhook URL "
                        "(expected https://discord.com/api/webhooks/…)")
    if name in ("DISCORD_OWNER_ID", "DISCORD_GUILD_ID") and not v.isdigit():
        warnings.append("expected digits only (right-click → Copy ID)")
    if name == "DISCORD_BOT_TOKEN" and (len(v) < 50 or " " in v):
        warnings.append("bot tokens are long single strings — double-check the copy")
    if name == "STRIPE_SECRET_KEY":
        if v.startswith("pk_"):
            warnings.append("that's the PUBLISHABLE key — the secret/"
                            "restricted key is the other one on the page")
        elif not (v.startswith("sk_") or v.startswith("rk_")):
            warnings.append("Stripe keys start with sk_ (secret) or rk_ "
                            "(restricted — the safer kind)")
        elif "_test_" in v[:8]:
            warnings.append("this is a TEST-mode key — it can never see real "
                            "subscriptions; grab the Live-mode key")
    if (name in ("DISCORD_ENABLE_CHAT_INTENT", "DISCORD_ENABLE_MEMBERS_INTENT",
                 "DISCORD_ADS_AUTO") and v not in ("0", "1")):
        warnings.append("this is an on/off switch — use 1 (on) or 0 (off)")
    if name == "GROQ_API_KEY" and not v.startswith("gsk_"):
        warnings.append("Groq keys start with gsk_ — double-check the copy")
    if name == "AMAZON_ASSOCIATE_TAG" and not (v.endswith("-20") or v.endswith("-21")):
        warnings.append("Associates tags usually end in -20 or -21 — double-check the copy")
    return warnings


def vault_status(path: Path | None = None) -> list[dict]:
    """Catalog + custom entries with set/masked state. NEVER full values.

    last-set-timestamp-d: each row also carries `last_set` (raw ISO-8601,
    or None) and `last_set_relative` (a human line: "just now"/"5m ago"/
    "never"/...) — when a key was last rotated/applied, not just whether
    it currently has a value."""
    stored = read_env(path)
    meta = _read_meta(path or env_path())
    rows: list[dict] = []
    for spec in CRED_CATALOG:
        val = stored.get(spec.name, "")
        ts = meta.get(spec.name)
        rows.append({"name": spec.name, "label": spec.label, "set": bool(val),
                     "masked": mask(val), "required_for": spec.required_for,
                     "what": spec.what, "where": spec.where, "hint": spec.hint,
                     "custom": False, "last_set": ts,
                     "last_set_relative": relative_time(ts)})
    for name, val in stored.items():
        if name not in _CATALOG_BY_NAME:
            ts = meta.get(name)
            rows.append({"name": name, "label": name, "set": True,
                         "masked": mask(val), "required_for": "custom",
                         "what": "custom entry", "where": "", "hint": "",
                         "custom": True, "last_set": ts,
                         "last_set_relative": relative_time(ts)})
    return rows


# feature → the vars it needs (drives the "what's missing" story)
_FEATURES: list[tuple[str, list[str]]] = [
    ("base delivery + bots ping", ["DISCORD_WEBHOOK_URL"]),
    ("storefront publish", ["DISCORD_SHOP_WEBHOOK_URL"]),
    ("presence card", ["DISCORD_STATUS_WEBHOOK_URL"]),
    ("📣 advertising", ["DISCORD_ADS_WEBHOOK_URL"]),
    ("🤝 affiliates channel", ["DISCORD_AFFILIATE_WEBHOOK_URL"]),
    ("admin bot (/setup-shop)", ["DISCORD_BOT_TOKEN", "DISCORD_OWNER_ID",
                                 "DISCORD_GUILD_ID"]),
    ("free-chat in #ask-aria", ["DISCORD_ENABLE_CHAT_INTENT"]),
    ("👋 welcome new members", ["DISCORD_ENABLE_MEMBERS_INTENT"]),
    ("auto-ads from the daemon", ["DISCORD_ADS_AUTO"]),
    ("Round 2 auto-roles (future)", ["STRIPE_SECRET_KEY"]),
    # cloud-mode-d: cloud mode itself needs NEITHER (works keyless) -- this
    # is only the FAST lane, and either key alone is enough for it. _FEATURES
    # rows are AND-semantics (every listed var required), which doesn't fit
    # an either/or upgrade -- so this tracks Groq alone (what Kevin actually
    # has); Cerebras stays a real, settable catalog entry, just not one that
    # would show a false "missing" once Groq's already in.
    ("☁ fast lane for cloud mode (Groq)", ["GROQ_API_KEY"]),
    ("🔗 Amazon affiliate tagging", ["AMAZON_ASSOCIATE_TAG"]),
    ("🎟 buy-links channel", ["DISCORD_BUYLINKS_WEBHOOK_URL"]),
]


def compose_credentials_report(path: Path | None = None) -> str:
    """Chat answer: which features are unlocked, what's missing. Masked-only —
    this function is deliberately incapable of leaking a value."""
    stored = read_env(path)
    lines = ["🔐 My Key Vault (all values stay local + masked):"]
    for feature, needs in _FEATURES:
        have = [n for n in needs if stored.get(n)]
        missing = [n for n in needs if not stored.get(n)]
        icon = "🟢" if not missing else ("🟡" if have else "○")
        detail = "ready" if not missing else "missing " + ", ".join(missing)
        lines.append(f"  {icon} {feature} — {detail}")
    extras = [n for n in stored if n not in _CATALOG_BY_NAME]
    if extras:
        lines.append(f"  ➕ custom: {', '.join(sorted(extras))}")
    lines.append("Add or update keys in the Key Vault (/keys) — I never show "
                 "a stored value, only ••••masked.")
    return "\n".join(lines)


# ── liveness probes (R5b): are the stored keys still VALID? ────────────────
# A GET on a Discord webhook URL returns its metadata WITHOUT posting — the
# perfect non-intrusive validity check. A bot token is checked via
# GET /users/@me. Results never include values; probing is explicit
# (`sov keys check`), never automatic.

def probe_webhook(url: str, opener=None, timeout: float = 10.0) -> tuple[bool, str]:
    """(alive?, detail). 200 → alive; 404 → deleted; 401 → token part wrong."""
    if not (url or "").strip():
        return False, "not set"
    if opener is None:  # pragma: no cover — tests inject
        from urllib.request import Request, urlopen

        def opener(u, timeout):  # type: ignore[misc]
            from sovereign_agent.discord_runtime.delivery import USER_AGENT
            return urlopen(Request(u, headers={"User-Agent": USER_AGENT}),
                           timeout=timeout)
    try:
        with opener(url, timeout) as resp:  # type: ignore[misc]
            code = getattr(resp, "status", 200)
        return (200 <= int(code) < 300), f"HTTP {code}"
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None)
        if code == 404:
            return False, "HTTP 404 — webhook was deleted; make a new one and update the key"
        if code == 401:
            return False, "HTTP 401 — the URL's token part is wrong; re-copy it"
        return False, f"HTTP {code}" if code is not None else type(exc).__name__


def probe_bot_token(token: str, opener=None, timeout: float = 10.0) -> tuple[bool, str]:
    """(valid?, detail) via GET /users/@me with Bot auth. Never logs the token."""
    if not (token or "").strip():
        return False, "not set"
    if opener is None:  # pragma: no cover — tests inject
        from urllib.request import Request, urlopen

        def opener(u, headers, timeout):  # type: ignore[misc]
            return urlopen(Request(u, headers=headers), timeout=timeout)
    from sovereign_agent.discord_runtime.delivery import USER_AGENT
    headers = {"Authorization": f"Bot {token}", "User-Agent": USER_AGENT}
    try:
        with opener("https://discord.com/api/v10/users/@me", headers, timeout) as resp:  # type: ignore[misc]
            code = getattr(resp, "status", 200)
        return (200 <= int(code) < 300), f"HTTP {code}"
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None)
        if code == 401:
            return False, "HTTP 401 — token invalid/rotated; Reset Token and re-store it"
        return False, f"HTTP {code}" if code is not None else type(exc).__name__


def probe_stripe_key(key: str, opener=None,
                     timeout: float = 10.0) -> tuple[bool, str]:
    """(valid?, detail) via GET /v1/account (read-only, charges nothing).
    Never logs the key. A restricted key without Account read still
    proves itself: Stripe answers 200 or a *permission* error (which
    means the key IS live) — only 401 means dead/revoked."""
    if not (key or "").strip():
        return False, "not set"
    if opener is None:  # pragma: no cover — tests inject
        from urllib.request import Request, urlopen

        def opener(u, headers, timeout):  # type: ignore[misc]
            return urlopen(Request(u, headers=headers), timeout=timeout)
    headers = {"Authorization": f"Bearer {key}",
               "User-Agent": "sovereign-agent-keys-check/1.0"}
    try:
        with opener("https://api.stripe.com/v1/account", headers,
                    timeout) as resp:  # type: ignore[misc]
            code = getattr(resp, "status", 200)
        mode = "LIVE" if "_live_" in key[:8] else (
            "TEST" if "_test_" in key[:8] else "?")
        return (200 <= int(code) < 300), f"HTTP {code} ({mode} mode)"
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None)
        if code == 401:
            return False, ("HTTP 401 — key invalid/revoked; roll it in the "
                           "Stripe dashboard and re-store it")
        if code == 403:
            return True, ("HTTP 403 — key is ALIVE but restricted from "
                          "Account read (fine for the reconciler)")
        return False, f"HTTP {code}" if code is not None else type(exc).__name__


def _simple_probe(url: str, key_present: bool, opener,
                  timeout: float = 10.0, ua: str = "sovereign-agent-keys-check/1.0",
                  headers: dict | None = None) -> tuple[bool, str]:
    """Shared read-only GET probe: 2xx → live; 401/403 → key rejected;
    other → honest detail. Never logs the key."""
    if not key_present:
        return False, "not set"
    if opener is None:  # pragma: no cover — tests inject
        from urllib.request import Request, urlopen

        def opener(u, hdrs, t):  # type: ignore[misc]
            return urlopen(Request(u, headers=hdrs), timeout=t)
    hdrs = {"User-Agent": ua, **(headers or {})}
    try:
        with opener(url, hdrs, timeout) as resp:  # type: ignore[misc]
            code = getattr(resp, "status", 200)
        return (200 <= int(code) < 300), f"HTTP {code}"
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None)
        if code in (401, 403):
            return False, f"HTTP {code} — key rejected; re-issue it"
        return False, f"HTTP {code}" if code is not None else type(exc).__name__


def probe_bestbuy(key: str, opener=None, timeout: float = 10.0) -> tuple[bool, str]:
    """Best Buy: a tiny Products query proves the key. Read-only."""
    url = (f"https://api.bestbuy.com/v1/products(sku=6084400)?apiKey={key}"
           "&format=json&show=sku,name")
    return _simple_probe(url, bool((key or "").strip()), opener, timeout)


def probe_google_maps(key: str, opener=None, timeout: float = 10.0) -> tuple[bool, str]:
    """Google Geocoding: a trivial geocode proves the key + enabled API."""
    url = ("https://maps.googleapis.com/maps/api/geocode/json?"
           f"address=Target&key={key}")
    ok, detail = _simple_probe(url, bool((key or "").strip()), opener, timeout)
    return ok, detail


def probe_ebay(app_id: str, opener=None, timeout: float = 10.0) -> tuple[bool, str]:
    """eBay Browse API: an auth call with the App ID. (Full Browse needs an
    OAuth token; a bad App ID fails fast — enough to catch a typo.)"""
    if not (app_id or "").strip():
        return False, "not set"
    # length/shape sanity (eBay App IDs are long dashed strings)
    if len(app_id) < 20:
        return False, "App ID looks too short — double-check the copy"
    return True, "format OK (full Browse validated on first live call)"


def probe_brickset(key: str, opener=None, timeout: float = 10.0) -> tuple[bool, str]:
    """Brickset: the API's own checkKey method — read-only, proves the key."""
    from urllib.parse import quote_plus
    url = ("https://brickset.com/api/v3.asmx/checkKey?"
           f"apiKey={quote_plus((key or '').strip())}")
    return _simple_probe(url, bool((key or "").strip()), opener, timeout)


def probe_bricklink(consumer_key: str, opener=None,
                    timeout: float = 10.0) -> tuple[bool, str]:
    """BrickLink uses OAuth1 (4 values must all be vaulted). A live call
    needs request signing, so — like the eBay probe — this validates
    presence + shape and the first live call proves the rest."""
    if not (consumer_key or "").strip():
        return False, "not set"
    missing = [v for v in ("BRICKLINK_CONSUMER_SECRET", "BRICKLINK_TOKEN",
                           "BRICKLINK_TOKEN_SECRET")
               if not (read_env().get(v) or "").strip()]
    if missing:
        return False, f"vault the rest of the OAuth set: {', '.join(missing)}"
    return True, "OAuth set complete (signed calls validated on first use)"


def probe_groq(key: str, opener=None, timeout: float = 10.0) -> tuple[bool, str]:
    """Groq: a GET on the OpenAI-compatible /models list proves the key —
    read-only, no completion spent."""
    return _simple_probe("https://api.groq.com/openai/v1/models",
                         bool((key or "").strip()), opener, timeout,
                         headers={"Authorization": f"Bearer {(key or '').strip()}"})


def probe_cerebras(key: str, opener=None, timeout: float = 10.0) -> tuple[bool, str]:
    """Cerebras: same shape as the Groq probe — /models, read-only."""
    return _simple_probe("https://api.cerebras.ai/v1/models",
                         bool((key or "").strip()), opener, timeout,
                         headers={"Authorization": f"Bearer {(key or '').strip()}"})


def reddit_client_credentials_token(
        client_id: str, client_secret: str, *, opener=None,
        timeout: float = 10.0) -> tuple[dict | None, str]:
    """One Reddit OAuth client-credentials exchange — the single
    implementation `probe_reddit()` (validate-only) and the tracker fetch
    path (`discord_runtime/fetchers.py`, which actually USES the token to
    fetch) both call, so there's one OAuth flow in this codebase, not two.
    Returns (token_response, detail): token_response carries 'access_token'
    + 'expires_in' on success, None on any failure (never raises)."""
    cid, secret = (client_id or "").strip(), (client_secret or "").strip()
    if not cid:
        return None, "REDDIT_CLIENT_ID not set"
    if not secret:
        return None, "REDDIT_CLIENT_ID set but REDDIT_CLIENT_SECRET missing"
    import base64
    import json as _json
    if opener is None:  # pragma: no cover — tests inject
        from urllib.request import Request, urlopen

        def opener(u, hdrs, data, t):  # type: ignore[misc]
            return urlopen(Request(u, data=data, headers=hdrs, method="POST"),
                           timeout=t)
    tok = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    hdrs = {"Authorization": f"Basic {tok}",
            "User-Agent": "BigKevsBotShop-Scout/1.0",
            "Content-Type": "application/x-www-form-urlencoded"}
    try:
        with opener("https://www.reddit.com/api/v1/access_token", hdrs,
                    b"grant_type=client_credentials", timeout) as resp:  # type: ignore[misc]
            code = getattr(resp, "status", 200)
            body = _json.loads(resp.read().decode())
        if not (200 <= int(code) < 300) or not body.get("access_token"):
            return None, f"HTTP {code} — no access_token in response"
        return body, f"HTTP {code} — token issued"
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None)
        if code in (401, 403):
            return None, "HTTP 401 — id/secret rejected; recreate the app"
        return None, f"HTTP {code}" if code is not None else type(exc).__name__


def probe_reddit(client_id: str, opener=None, timeout: float = 10.0) -> tuple[bool, str]:
    """Reddit script app: a client-credentials token request proves both
    the id AND secret are valid. Needs both — read from the vault here."""
    cid = (client_id or "").strip()
    if not cid:
        return False, "not set"
    secret = (read_env().get("REDDIT_CLIENT_SECRET") or "").strip()
    body, detail = reddit_client_credentials_token(
        cid, secret, opener=opener, timeout=timeout)
    return body is not None, detail


def check_all(path: Path | None = None, *, webhook_opener=None,
              token_opener=None, stripe_opener=None) -> list[dict]:
    """Probe every PROBEABLE stored key (webhooks + bot token). Masked-only
    results; keys that aren't set are reported as skipped, not failed."""
    stored = read_env(path)
    results: list[dict] = []
    # probe EVERY webhook the catalog knows + any custom *_WEBHOOK_URL —
    # a new webhook feature can never silently escape liveness checking
    webhook_names = [c.name for c in CRED_CATALOG
                     if c.name.endswith("WEBHOOK_URL")]
    webhook_names += sorted(n for n in stored
                            if n.endswith("WEBHOOK_URL")
                            and n not in webhook_names)
    for name in webhook_names:
        val = stored.get(name, "")
        if not val:
            results.append({"name": name, "checked": False, "ok": None,
                            "detail": "not set — skipped"})
            continue
        ok, detail = probe_webhook(val, opener=webhook_opener)
        results.append({"name": name, "checked": True, "ok": ok, "detail": detail})
    tok = stored.get("DISCORD_BOT_TOKEN", "")
    if tok:
        ok, detail = probe_bot_token(tok, opener=token_opener)
        results.append({"name": "DISCORD_BOT_TOKEN", "checked": True,
                        "ok": ok, "detail": detail})
    else:
        results.append({"name": "DISCORD_BOT_TOKEN", "checked": False,
                        "ok": None, "detail": "not set — skipped"})
    sk = stored.get("STRIPE_SECRET_KEY", "")
    if sk:
        ok, detail = probe_stripe_key(sk, opener=stripe_opener)
        results.append({"name": "STRIPE_SECRET_KEY", "checked": True,
                        "ok": ok, "detail": detail})
    else:
        results.append({"name": "STRIPE_SECRET_KEY", "checked": False,
                        "ok": None, "detail": "not set — skipped"})
    # concierge-d: probe the provider API keys too (read-only validators)
    for name, prober in (("BESTBUY_API_KEY", probe_bestbuy),
                         ("GOOGLE_MAPS_API_KEY", probe_google_maps),
                         ("EBAY_APP_ID", probe_ebay),
                         ("REDDIT_CLIENT_ID", probe_reddit),
                         ("BRICKSET_API_KEY", probe_brickset),
                         ("BRICKLINK_CONSUMER_KEY", probe_bricklink),
                         ("GROQ_API_KEY", probe_groq),
                         ("CEREBRAS_API_KEY", probe_cerebras)):
        val = stored.get(name, "")
        if val:
            ok, detail = prober(val)
            results.append({"name": name, "checked": True, "ok": ok,
                            "detail": detail})
        else:
            results.append({"name": name, "checked": False, "ok": None,
                            "detail": "not set — skipped"})
    return results


_CRED_TRIGGERS = (
    "key vault", "your keys", "your credentials", "credentials set",
    "your tokens", "keys set", "which keys", "what keys", "the vault",
    "your token set", "missing keys",
)


def is_credentials_query(text: str) -> bool:
    if not text:
        return False
    from sovereign_agent.bridge_patterns import match_any
    return match_any(text, _CRED_TRIGGERS)
