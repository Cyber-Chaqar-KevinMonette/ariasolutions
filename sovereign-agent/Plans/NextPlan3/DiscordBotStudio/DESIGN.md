# Discord Bot Studio — design & safety posture

Two layers, both shipped:

1. **Define** — `bot_projects.py` + the cockpit Bot Studio (`/bots`). Name a
   project, name the bot, pick a kind, write the concept + optional details.
   Durable JSON under `<data>/bot_projects/`. (The "define before build"
   floor.)
2. **Run** — `discord_runtime/` + `sov bots`. Monitor sources and deliver
   alerts to Discord — **legitimate by construction**, safe by default.

## The safety posture (non-negotiable, and structural — not a promise)

- **Rate-limits are a gate, not a guideline.** A `Source` declares
  `allowed_min_interval_s` (the fastest it permits); a `RateContract` that
  would poll faster raises `ContractViolation` at construction. There is a
  hard civility floor (`MIN_ALLOWED_INTERVAL_S = 15s`) no source can go
  below. Deliveries are throttled by a rolling-minute `max_sends_per_minute`
  ceiling in the `RateGate`. **You cannot build a bot that hammers a source
  or spams a channel — the types refuse it.**
- **Dry-run by default.** A default runtime uses a `NullFetcher` (reaches
  nothing) and `DryRunDelivery` (sends nothing). `sov bots run <project>`
  monitors and reports what it *would* send. Real sending requires
  `--live` **and** a resolvable delivery target.
- **No secrets are stored.** Delivery references an environment-variable
  NAME (e.g. `DISCORD_WEBHOOK_URL`). The URL/token lives only in the
  operator's environment — never in a JSON file, never in the repo, never
  in `describe()` output.
- **Every live send alerts a human** (`on_live_send`) and lands in a
  durable audit trail (`<data>/bot_projects/<slug>/runs.jsonl`).
- **Official API only.** Webhook POST (stdlib `urllib`, no dependency) for
  notification/alert bots; discord.py (optional, lazy) is the extension
  point for interactive/gateway bots. **No selfbots, no anti-bot evasion,
  no auto-purchase.** A bot built this way simply isn't bannable.

## Components

| File | Role |
|---|---|
| `discord_runtime/contracts.py` | `RateContract` (structural ceiling) + `RateGate` (stateful, injectable clock) |
| `discord_runtime/sources.py` | `Source` (+ civility floor), pluggable `Fetcher` (`NullFetcher` default, opt-in `HttpJsonFetcher`), per-project store |
| `discord_runtime/fetchers.py` | `RssFetcher` (RSS/Atom, stdlib), `ChangeFetcher` (hash → dedup = change detection), `fetcher_for()` factory by `source.kind` |
| `discord_runtime/delivery.py` | `DryRunDelivery` (default), `WebhookDelivery` (env-var-only, armed-only, injectable opener) |
| `discord_runtime/queue.py` | `JobQueue` — durable delivery queue: idempotent enqueue, visibility timeout, exponential backoff, dead-letter |
| `discord_runtime/breaker.py` | `CircuitBreaker` — closed/open/half-open, backs off a failing target |
| `discord_runtime/runtime.py` | `BotRuntime.poll_once` (fetch → dedup → alert → queue/inline) + `.drain` (lease → send → complete/retry/dead-letter, breaker- and rate-guarded) |
| `discord_runtime/manager.py` | `BotManager` — supervises the whole fleet with **crash isolation**; durable + dry-run by default |
| `cli.py` `sov bots` | `list` / `add-source` / `remove-source` / `run` / `fleet` / `queue [--requeue-dead]` (all `--live`-gated) |
| cockpit `bot_studio_screen.py` | "▶ dry-run" button — one safe cycle from the cockpit |

## Reliability & resilience (the managed path)

Highest-leverage patterns, proven at scale, all local and dependency-free:

- **Durable queue (SQS/Sidekiq lineage).** Alerts become durable jobs; a
  crashed worker's leased job is reclaimed after a visibility timeout and
  retried — **no alert is lost to a hiccup or a kill.** Failed sends retry
  with exponential backoff; a poison message dead-letters after
  `max_attempts` (inspect/requeue via `sov bots queue`), so it can never
  block the queue.
- **Circuit breaker (resilience4j/Hystrix lineage).** A target that keeps
  failing trips the breaker → the drain backs off for a cooldown instead of
  hammering it and burning the retry budget; one half-open probe recloses it
  on recovery.
- **Crash isolation (supervisor lineage).** The `BotManager` wraps each
  bot's poll+drain; one misbehaving bot (bad source, parser bug) is caught
  and reported while every other bot keeps running — the fleet stays up.
- **Backpressure.** The `RateGate` leases only as many jobs as the
  per-minute send budget allows, so a burst can't breach the send ceiling.

## What's proven vs. what needs a real token

- **Proven here (23 tests, no network):** contracts refuse illegal rates;
  dry-run default sends nothing; env-var-only secrets; dedup; throttle;
  audit trail; the live webhook path via an injected opener (asserts the
  POST body + human alert fire).
- **Needs a real token to prove end-to-end:** an actual live webhook send
  and, for interactive bots, the discord.py gateway path. Those are opt-in
  and gated; they are honestly *not* validated against Discord's servers in
  this repo.

## Going live (operator steps, when ready)

1. Create a Discord webhook in the target channel (Server Settings →
   Integrations → Webhooks). Export it: `export DISCORD_WEBHOOK_URL=...`.
2. Wire a real fetcher for the source kind (RSS/API) — the `Fetcher`
   protocol; `HttpJsonFetcher` is the starting point for JSON APIs.
3. `sov bots run <project> --live` — watch the audit trail; every send is
   logged and human-flagged.

## Next extensions (registered, not yet built)

- HTML-scrape fetcher (CSS-selector based) behind the same `Fetcher`
  protocol — RSS/JSON/change are shipped.
- discord.py gateway delivery for interactive/community/support bots (the
  webhook path — notifications/alerts — is shipped).
- A long-running daemon that calls `BotManager.tick()` on a real scheduler
  (today `run`/`fleet` do N cycles on a virtual clock; the loop/daemon is
  the caller's job so it stays testable and HALT-able).
- Stripe→role monetization for paid bots (v2).
