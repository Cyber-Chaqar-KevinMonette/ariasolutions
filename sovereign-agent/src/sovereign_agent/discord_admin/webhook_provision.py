"""webhook_provision — she makes her own webhooks and vaults them herself.

Kevin's ask: can she create webhooks and copy the URLs into her Key Vault
safely? Yes — and it's SAFER than the manual path: the URL goes from
Discord's API straight into the vault file (0600, masked forever after)
without ever being displayed, pasted, or sent through a chat surface.
No clipboard, no screen, nothing to mis-save.

This module is the pure, tested half (what's needed, how it's recorded,
how results render — always masked). The live half is the owner-gated
`/setup-webhooks` command in bot.py, which needs the bot to have the
**Manage Webhooks** permission.

Growth story: these specs mirror the blueprint. When the server plan
evolves and a new channel needs a webhook, its spec is added HERE — the
plan-evolution announcement plus `/setup-webhooks` (idempotent: it only
creates what's missing, and reuses an existing webhook on the channel if
one matches by name) make scaling a two-command act.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "WEBHOOK_SPECS",
    "WebhookSpec",
    "provision_plan",
    "store_webhook_url",
    "render_results",
]


@dataclass(frozen=True)
class WebhookSpec:
    channel: str          # blueprint channel name (matched canonically)
    env_name: str         # the vault key the URL lands in
    display_name: str     # the webhook's name in Discord


# one spec per webhook the shop stack uses — mirrors the vault catalog
WEBHOOK_SPECS: list[WebhookSpec] = [
    WebhookSpec("aria-control", "DISCORD_WEBHOOK_URL", "Aria"),
    WebhookSpec("storefront", "DISCORD_SHOP_WEBHOOK_URL", "BigKev's Bot Shop"),
    WebhookSpec("aria-status", "DISCORD_STATUS_WEBHOOK_URL", "Aria"),
    WebhookSpec("announcements", "DISCORD_ADS_WEBHOOK_URL", "Aria"),
    # scout-d: the flagship's stage — finds land in #live-demo
    WebhookSpec("live-demo", "DISCORD_DEMO_WEBHOOK_URL", "Aria's TCG Scout"),
    # command-d (F5, Kevin 2026-07-19): her cockpit shift, narrated live
    # to the owner's private bridge
    WebhookSpec("owner-bridge", "DISCORD_OWNER_WEBHOOK_URL",
                "Aria — at the cockpit"),
    WebhookSpec("angel-voice", "DISCORD_ANGEL_WEBHOOK_URL",
                "⚛ The Angel — her own voice"),
    # passes-d (Kevin, 2026-07-26): "channels for direct purchase links"
    WebhookSpec("buy-links", "DISCORD_BUYLINKS_WEBHOOK_URL",
                "BigKev's Bot Shop"),
]


def _tracker_specs() -> list[WebhookSpec]:
    """verticals-d: one webhook per ★ tracker channel + the catch-all, so
    each niche's finds post to its own channel. Env name matches the
    scout project's webhook_env (DISCORD_TRACK_<SLUG>_WEBHOOK_URL)."""
    def _env(v):
        return f"DISCORD_TRACK_{v.slug.upper().replace('-', '_')}_WEBHOOK_URL"
    try:
        # categories-d: every vertical that owns a channel — the ★ stars +
        # all category-homed niches (GAMING/COMPUTERS/VEHICLES/CLOTHING/
        # PETS/WHOLESALE) — gets its own channel webhook. channeled_verticals
        # is already deduped by slug (so by env too).
        from sovereign_agent.verticals import channeled_verticals
        specs = [WebhookSpec(v.track_channel, _env(v), f"{v.name} Scout")
                 for v in channeled_verticals()]
    except Exception:  # noqa: BLE001
        specs = []
    specs.append(WebhookSpec("track-everything-else",
                             "DISCORD_TRACK_EVERYTHING_WEBHOOK_URL",
                             "Aria's Scout"))
    # mead-d: honey/yeast/gear deals land in the 21+ Mead Lounge
    specs.append(WebhookSpec("mead-deals", "DISCORD_MEAD_DEALS_WEBHOOK_URL",
                             "Mead Scout"))
    return specs


# the full provisioning set = core + per-tracker (built once at import)
WEBHOOK_SPECS = WEBHOOK_SPECS + _tracker_specs()


def provision_plan(stored: dict[str, str] | None = None,
                   *, refresh: bool = False) -> list[WebhookSpec]:
    """Which webhooks still need making. Idempotent by construction:
    a key already in the vault is skipped (unless refresh)."""
    if refresh:
        return list(WEBHOOK_SPECS)
    stored = stored or {}
    return [s for s in WEBHOOK_SPECS if not (stored.get(s.env_name) or "").strip()]


def store_webhook_url(env_name: str, url: str) -> str:
    """Vault the URL (0600, atomic) and return ONLY the masked form —
    the caller never needs (and never gets) the raw value back."""
    from sovereign_agent.credentials import mask, set_secret
    set_secret(env_name, url)
    return mask(url)


def render_results(results: list[tuple[str, str, str, str]]) -> str:
    """(channel, env_name, outcome, masked) → the ephemeral reply.
    NO raw URL can appear here — only masked tails."""
    if not results:
        return ("✅ every webhook is already in the vault — nothing to make.\n"
                "Probe them anytime: `sov keys check`")
    lines = ["🪝 Webhooks provisioned (URLs went STRAIGHT into the vault — "
             "never displayed):"]
    for channel, env_name, outcome, masked in results:
        icon = {"created": "＋", "reused": "↺", "failed": "✗",
                "no-channel": "?", "rehomed": "⌂"}.get(outcome, "•")
        note = {"created": "new webhook", "reused": "existing webhook reused",
                "failed": "FAILED — check my Manage Webhooks permission",
                "no-channel": "channel not found on this server",
                "rehomed": "webhook moved to its new home channel"}[outcome]
        tail = f" → {env_name} = {masked}" if masked else ""
        lines.append(f"  {icon} #{channel}: {note}{tail}")
    lines.append("Verify liveness: `sov keys check` · storefront up: "
                 "`sov shop publish --live`")
    return "\n".join(lines)
