"""discord_runtime — the live layer that RUNS a defined bot project, safely.

The Bot Studio (`bot_projects.py`) is where a project is *defined*. This
package is where a defined project is *run* — but legitimate by
construction, not by trust:

  • **Rate-limits are a structural gate, not a guideline.** A `Source`
    declares the fastest rate it permits; a `RateContract` that tries to
    poll faster than that raises at construction. You cannot build a bot
    that violates a source's allowed rate — the type system refuses it.
  • **Dry-run by default.** Nothing is ever sent to Discord unless the
    runtime is *explicitly* armed with `live=True` AND a delivery target
    resolves from the environment. A default `run()` monitors and reports
    what it WOULD send — it sends nothing.
  • **No secrets are stored.** A project references an environment-variable
    NAME (e.g. `DISCORD_WEBHOOK_URL`); the token/URL itself lives only in
    the operator's environment, never in a JSON file, never in the repo.
  • **Every live send alerts a human** (the `on_live_send` hook) and lands
    in a durable audit trail — transparency, per the review-journal
    doctrine.
  • **Official API only.** Webhook POST (stdlib) or discord.py (optional,
    lazy). No selfbots, no anti-bot evasion, no auto-purchase. A bot built
    this way simply isn't bannable.

This is the honest floor Kevin asked for: build a stable floor for
ourselves first (legitimate income surface), then build floor under others.
"""
from __future__ import annotations

from .breaker import CircuitBreaker
from .contracts import (
    ContractViolation,
    RateContract,
    RateGate,
)
from .delivery import (
    DeliveryResult,
    DryRunDelivery,
    WebhookDelivery,
    build_delivery,
)
from .fetchers import (ChangeFetcher, RedditFetcher, RssFetcher, ScrapeFetcher,
                       WarframeFlipFetcher, fetcher_for)
from .manager import BotManager, BotStatus, FleetTick
from .queue import Job, JobQueue
from .runtime import (
    Alert,
    BotRuntime,
    CycleReport,
    DrainReport,
    build_runtime,
)
from .sources import (
    HttpJsonFetcher,
    NullFetcher,
    Source,
    add_source,
    list_sources,
    remove_source,
)

__all__ = [
    "ContractViolation",
    "RateContract",
    "RateGate",
    "CircuitBreaker",
    "DeliveryResult",
    "DryRunDelivery",
    "WebhookDelivery",
    "build_delivery",
    "ChangeFetcher",
    "RedditFetcher",
    "RssFetcher",
    "ScrapeFetcher",
    "WarframeFlipFetcher",
    "HttpJsonFetcher",
    "fetcher_for",
    "Job",
    "JobQueue",
    "BotManager",
    "BotStatus",
    "FleetTick",
    "Alert",
    "BotRuntime",
    "CycleReport",
    "DrainReport",
    "build_runtime",
    "NullFetcher",
    "Source",
    "add_source",
    "list_sources",
    "remove_source",
]
