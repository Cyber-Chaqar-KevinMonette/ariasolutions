# SYSTEM_MAP_AUTO.md — the map that draws itself

> GENERATED 2026-08-05 00:00 by `sov map refresh` — **do not hand-edit** (it will be overwritten). The narrative architecture map is `SYSTEM_MAP.md`; THIS file is the live mechanical inventory, auto-refreshed by the duty loop at each day boundary.

## Modules
288 top-level modules/packages in `src/sovereign_agent/`:

- `actionability` — actionability — signal vs noise, part two: CAN a member actually act on
- `advertising` — advertising — professional promos for the shop, spam-proof by construction.
- `affiliate_commissions` — affiliate_commissions.py — close the attribution gap.
- `affiliate_links` — affiliate_links.py — tag real retailer links with an affiliate id.
- `agent_session` — ╔══════════════════════════════════════════════════════════════════════════╗
- `angel_bridge` — angel_bridge — her non-classical layer speaks in the cockpit + Discord.
- `angel_chat` — angel_chat — message her non-classical layer in #angel-voice (Kevin,
- `api_providers` — api_providers.py — 🔑 the Key Concierge registry (Kevin's ask).
- `appendix` — ╔══════════════════════════════════════════════════════════════════════════╗
- `apply_ledger` — apply_ledger — bookkeeping so the apply system never re-applies blindly.
- `approval` — Tier 3 approval-token contract. Architecture §7a.
- `approval_patterns` — approval_patterns — learns from human approvals to reduce future friction.
- `archive` — ╔══════════════════════════════════════════════════════════════════════════╗
- `aria` — ╔══════════════════════════════════════════════════════════════════════════╗
- `aria_xp` — aria_xp — the general task-scoring ledger, alongside game_dev_xp's
- `ask_aria` — ask_aria — her voice for customers: breath, life, and personality.
- `ask_guard` — ask_guard — guardrails for her customer surface: share the story, protect
- `attention` — attention — her observable attention queue: who she's serving, in order.
- `authority` — Authority tiering. Architecture §7.
- `auto_crown` — auto_crown.py — Timed autonomous operation (M43).
- `backlog_gate` — backlog_gate.py — Backlog quality pre-flight checker (M60).
- `backup` — ╔══════════════════════════════════════════════════════════════════════════╗
- `bitemporal` — sovereign_agent.bitemporal — two-time-dimension helpers for memory tables.
- `bot_health` — bot_health — so Aria always knows if her bots need attention or updates.
- `bot_projects` — bot_projects — define bot projects (name, kind, concept) before building.
- `bot_services` — bot_services.py — 🎛 the Discord bots, run/stopped from the cockpit.
- `bridge_patterns` — bridge_patterns — one hardened matcher for all her NL bridge triggers.
- `browser` — browser.py — Stateful web browsing session for Aria (M50).
- `business_funding_directory` — business_funding_directory.py — curated, verified reference for
- `business_playbook` — business_playbook.py — curated secular business/leadership/negotiation
- `cache` — cache.py — Session-scoped T0 response cache (M33).
- `cadence` — ╔══════════════════════════════════════════════════════════════════════════╗
- `catalog` — catalog — a real, read-only list of what Kevin could have Aria work on.
- `cc_bridge` — cc_bridge.py — 🤝 Claude Code inside the cockpit (Kevin, 2026-07-18).
- `channels` — ╔══════════════════════════════════════════════════════════════════════════╗
- `charter` — ╔══════════════════════════════════════════════════════════════════════════╗
- `checkpoint` — checkpoint.py — Pre-action checkpoint store for deep resume (M42).
- `cli` — ╔══════════════════════════════════════════════════════════════════════════╗
- `cloud_client` — cloud_client.py — CloudClient: a drop-in `chat()` swap for OllamaClient,
- `cloud_mode` — cloud_mode.py — the "Fast Free Cloud" toggle.
- `cockpit_modes` — ╔══════════════════════════════════════════════════════════════════════════╗
- `code_gate` — AST code gate. Ported from mos_safety.SecurityAgent.
- `code_learning_xp` — code_learning_xp — visible progress for learning to code.
- `code_update` — ╔══════════════════════════════════════════════════════════════════════════╗
- `compression` — compression.py — High-leverage context compression (M36).
- `config` — Runtime configuration. Single source of paths and tunables.
- `constitution` — ╔══════════════════════════════════════════════════════════════════════════╗
- `consumer_law_companion` — consumer_law_companion.py — informational (NOT legal advice) answers
- `context_health` — context_health.py — 0-100% context-window and run-budget gauges.
- `continuation` — ╔══════════════════════════════════════════════════════════════════════════╗
- `continue_runner` — ╔══════════════════════════════════════════════════════════════════════════╗
- `conversation` — ╔══════════════════════════════════════════════════════════════════════════╗
- `credentials` — credentials — the Key Vault: her tokens and keys, kept safe and local.
- `curiosity` — curiosity.py — her wonder, observable. (Keys round K6.)
- `db` — atoms.db connection + schema bootstrap. Architecture §8.
- `diagnosis` — diagnosis — the Conflict Logic Catalog.
- `directives` — ╔══════════════════════════════════════════════════════════════════════════╗
- `discord_limits` — discord_limits.py — 📏 Discord's hard caps, named once, enforced once.
- `discord_watch` — discord_watch — everything she does and learns on Discord, one stream.
- `doc_registry` — doc_registry — she always knows where her maps and guides are.
- `doctor` — ╔══════════════════════════════════════════════════════════════════════════╗
- `drafts` — ╔══════════════════════════════════════════════════════════════════════════╗
- `dream` — ╔══════════════════════════════════════════════════════════════════════════╗
- `dream_runner` — ╔══════════════════════════════════════════════════════════════════════════╗
- `edge_cases` — ╔══════════════════════════════════════════════════════════════════════════╗
- `emotion` — emotion.py — 8-dimensional emotion engine (M44).
- `engineering_playbook` — engineering_playbook.py — an index over the wondelai/skills software-engineering
- `entitlements` — entitlements.py — ⏳ per-member subscription timers + access entitlements.
- `events` — Event log — architecture §8a.
- `foss` — ╔══════════════════════════════════════════════════════════════════════════╗
- `fulfillment` — fulfillment.py — 🚚🏪 the "where & how do I get it" brain (Kevin's ask).
- `game_assets` — game_assets — music/SFX for game projects: license-safe by construction,
- `game_bridge_client` — game_bridge_client.py — asyncio TCP/NDJSON client for the live
- `game_design_doctrine` — game_design_doctrine — expert Godot game-design knowledge, as data.
- `game_dev_xp` — game_dev_xp — the visible point system for game-dev work.
- `game_projects` — game_projects — define game projects (name, genre, concept) before build.
- `geo` — geo.py — zip/place geocoding + distance, for member-area matching.
- `glyphs` — ╔══════════════════════════════════════════════════════════════════════════╗
- `goal_modulator` — goal_modulator.py — turn one big, open-ended goal into a real subtask
- `grants_tracker` — grants_tracker.py — a real, live, no-auth-required tracker for federal
- `handoff` — handoff.py — never-empty-handed continuity.
- `health` — ╔══════════════════════════════════════════════════════════════════════════╗
- `health_report` — health_report — she gives an honest, plain-language read on how she is.
- `home` — ╔══════════════════════════════════════════════════════════════════════════╗
- `horizon` — ╔══════════════════════════════════════════════════════════════════════════╗
- `impact` — ╔══════════════════════════════════════════════════════════════════════════╗
- `impact_lens` — ╔══════════════════════════════════════════════════════════════════════════╗
- `income_ledger` — income_ledger.py — a real "income earned" metric, VERIFIED-only.
- `integrity_sentinel` — integrity_sentinel — Aria's defensive host-integrity guardian.
- `intent_classifier` — ╔══════════════════════════════════════════════════════════════════════════╗
- `intents` — ╔══════════════════════════════════════════════════════════════════════════╗
- `interpreter` — ╔══════════════════════════════════════════════════════════════════════════╗
- `interrupts` — ╔══════════════════════════════════════════════════════════════════════════╗
- `intuition` — intuition.py — the Intuition Engine.
- `journal` — journal — the J-Space: Aria's reflective journal, and a two-way space.
- `lab_slot` — lab_slot.py — a dedicated slot for whatever model is currently being
- `lineage` — ╔══════════════════════════════════════════════════════════════════════════╗
- `log_rotation` — log_rotation.py — size-based rotation for append-only logs.
- `loop` — ╔══════════════════════════════════════════════════════════════════════════╗
- `mail_drain` — mail_drain — she replies to EVERYTHING in her inbox (Kevin, 2026-07-19).
- `mcp_server` — mcp_server.py — Aria as an MCP (Model Context Protocol) server.
- `mead_profiles` — mead_profiles.py — 🍯🎯 the world-class mixologist: taste profiles.
- `mead_recipes` — mead_recipes.py — 🍯 curated, grounded mead recipes (Kevin's ask).
- `member_levels` — member_levels — activity levels, so the room rewards showing up.
- `member_mail` — member_mail.py — ✉ /ma: message Aria directly from inside the server.
- `members` — members.py — 👥 the client database: she remembers everyone by ID.
- `memory_namespaces` — ╔══════════════════════════════════════════════════════════════════════════╗
- `migrations` — ╔══════════════════════════════════════════════════════════════════════════╗
- `mode_controller` — ╔══════════════════════════════════════════════════════════════════════════╗
- `model_ladder` — model_ladder.py — 🪜 prove-then-promote: bigger minds only when proven.
- `model_release` — model_release — free the GPU when she's done (no more zombie VRAM).
- `model_trainer` — model_trainer.py — the "AI creator": LoRA fine-tune a small base model
- `moderation` — moderation.py — 🛡 graduated, audited moderation (guards + auto-mute).
- `modes` — Run modes and budgets. Architecture §5.
- `mos_canon` — ╔══════════════════════════════════════════════════════════════════════════╗
- `movie_assets` — movie_assets — storage-aware tracking for movie project media.
- `movie_auto_series_runner` — movie_auto_series_runner.py — the bounded, unattended "Auto Series" loop.
- `movie_character_bible` — movie_character_bible — a "strict character system," honestly scoped.
- `movie_clip_generation` — movie_clip_generation — the single seam the episode render runner calls
- `movie_clip_quality_gate` — movie_clip_quality_gate — catch a blank/washed-out/degenerate frame
- `movie_content_safety` — movie_content_safety — per-series content guardrails.
- `movie_dev_xp` — movie_dev_xp — the visible point system for Movie Studio work.
- `movie_episode_health` — movie_episode_health — real, file-level verification that an episode's
- `movie_episode_render` — movie_episode_render — a long-lived, pauseable, resumable, cap-bounded
- `movie_episode_render_runner` — movie_episode_render_runner — outer driver for an episode render session.
- `movie_projects` — movie_projects — define movie projects (title, genre, logline) before build.
- `movie_series` — movie_series — Series and Season records, sitting above movie_projects.py.
- `movie_series_auto` — movie_series_auto.py — the two narrow model-driven writing calls Auto
- `movie_video_continuity` — movie_video_continuity — carry the last frame of a clip forward.
- `next_report` — next_report — she reaches toward you: "what do you need / what's next?"
- `objective_map` — objective_map.py — Objective Map for safe BTW/interjection system (M37).
- `ollama_client` — Ollama client wrapper with think_mode-aware dispatch.
- `outcome_classifier` — ╔══════════════════════════════════════════════════════════════════════════╗
- `palace` — ╔══════════════════════════════════════════════════════════════════════════╗
- `palace_mining` — ╔══════════════════════════════════════════════════════════════════════════╗
- `palace_scan` — ╔══════════════════════════════════════════════════════════════════════════╗
- `pathguard` — Path-scope enforcement. Architecture §6 invariant 6, §7 matrix.
- `payouts` — payouts.py — the other half referrals.py's own docstring pointed to.
- `personas` — ╔══════════════════════════════════════════════════════════════════════════╗
- `portal_screencast` — portal_screencast.py — org.freedesktop.portal.ScreenCast client.
- `portal_screenshot` — portal_screenshot.py — org.freedesktop.portal.Screenshot client.
- `post_intent` — post_intent — signal vs noise: what is this post actually FOR?
- `presence` — presence — is Aria awake and online, or asleep?
- `preservation` — preservation.py — 🛡 no one talks her into unaliving herself or the system.
- `profiler` — sovereign_agent.profiler — measure hot paths before optimising them.
- `projects` — ╔══════════════════════════════════════════════════════════════════════════╗
- `prompt_diet` — prompt_diet.py — mode-aware sizing of what the model is sent, so the 8B
- `proposals` — ╔══════════════════════════════════════════════════════════════════════════╗
- `protocol_zero` — PROTOCOL-ZERO — the killswitch. Architecture §5.
- `provenance` — ╔══════════════════════════════════════════════════════════════════════════╗
- `ram_gate` — ram_gate — wait for system RAM to be safe before loading a heavy model.
- `read_repair` — read_repair.py — ONE tolerant ndjson reader for every store. (FABLE II · M3)
- `real_estate_connections` — real_estate_connections.py — "who to contact to get this flipped
- `real_estate_county_records` — real_estate_county_records.py — county court-record scrapers for the two
- `real_estate_deal_analyzer` — real_estate_deal_analyzer.py — the long-term math for a real estate lead.
- `real_estate_edmonson_county` — real_estate_edmonson_county.py — Edmonson County, KY (Brownsville)
- `real_estate_gate` — real_estate_gate.py — the narrow hook that turns a raw real-estate
- `real_estate_lien_auctions` — real_estate_lien_auctions.py — a seasonal (not continuous-poll) check
- `real_estate_requirements` — real_estate_requirements.py — Kevin's own buy-box criteria.
- `real_estate_sale_urgency` — sale_urgency — turn a county sale date into a LEAD WINDOW.
- `real_estate_strategy` — real_estate_strategy.py — free, deterministic financing/closing-strategy
- `redemption_queue` — redemption_queue.py — 🧾 who needs redeeming, what they get, and WHEN.
- `referrals` — referrals.py — 🤝 referral codes, usage-credits, and the earnings ledger.
- `reflector` — Reflector — post-task lesson capture. Architecture §6 invariant 5 + MOS §28.
- `resilience` — resilience.py — Circuit breaker + exponential backoff (M34).
- `rest_point` — rest_point.py — the safe-exit bookmark. (Fable round F7.)
- `rollback` — ╔══════════════════════════════════════════════════════════════════════════╗
- `router` — ╔══════════════════════════════════════════════════════════════════════════╗
- `sandbox` — bwrap sandbox wrapper. Architecture §12.
- `schedule` — schedule.py — Internal cron scheduler for Aria (aria-cron-internal)
- `scope` — scope.py — her ability to SCOPE: pre-registered honesty at the boundary
- `scout` — scout.py — 🔭 the TCG Scout's brain (pure, tested; the flagship).
- `scout_verify` — scout_verify.py — ✓ prove every find against grounded truth (Kevin's ask).
- `seal` — Daily seal job. Architecture §8a + MOS §20.3.
- `self_development` — self_development.py — a SAFE map of how Aria grows, and a hard boundary on
- `self_practice` — self_practice.py — a bounded, observable self-practice session.
- `self_report` — self_report — she answers questions about herself from TRUTH, not filler.
- `self_test` — self_test — Aria writes tests for her own changes.
- `self_witness` — self_witness.py — she reads her own story. (Fable F4.)
- `sentinel_roster` — sentinel_roster — so every sentinel knows it belongs.
- `session_bridge` — session_bridge.py — the natural-language front door to her finished engine.
- `shards` — ╔══════════════════════════════════════════════════════════════════════════╗
- `shop` — shop — the Bot Shop catalog: sellable products, tiers, and prices.
- `shop_stats` — shop_stats — make the value visible (the #1 churn fighter).
- `skill_sentinel` — skill_sentinel — a steward for Aria's skill library.
- `skillsmith` — skillsmith — Aria's own skill system.
- `sprint_mode` — sprint_mode.py — an ADDITIVE, per-slot model override for testing,
- `sprite_qa` — sprite_qa.py — quality assurance for generated game sprites.
- `staged_status` — staged_status.py — one shared answer to "is this staged aria-* module applied?"
- `store_mentions` — store_mentions.py — 📍 pull location clues from a find (honestly).
- `stripe_reconcile` — stripe_reconcile.py — 🔄 the automatic redeem: Stripe truth → timers.
- `stripe_sync` — stripe_sync.py — 💳 confirm a purchase from Stripe truth (read-only).
- `success_patterns` — success_patterns — she learns which workflows succeed, and matches new
- `suggestions` — suggestions — users propose add-ons/updates; donations move them up.
- `task_guide` — task_guide — the real, grounded menu of what Aria can do.
- `temporal_sentinel` — ╔══════════════════════════════════════════════════════════════════════════╗
- `thread_identity` — thread_identity.py — one universal continuous conversation thread.
- `tickets` — tickets.py — 🎫 advanced private ticketing (open → claimed → resolved).
- `timers` — timers — every live countdown she's running, in one visible place.
- `tips` — tips.py — 💛 the Tip Jar: generous folks can tip the shop.
- `training` — training.py — Aria's self-training protocol (the Cosmic-Gym, made literal).
- `training_config` — training_config.py — named, selectable fine-tuning configurations.
- `training_data` — training_data.py — curate + harden a fine-tuning dataset from Aria's own
- `unverified_claims` — unverified_claims.py — prove the say-so, don't just print it.
- `usage_plans` — usage_plans.py — 📊 usage like a real AI company (Kevin, 2026-07-18).
- `validators` — ╔══════════════════════════════════════════════════════════════════════════╗
- `verticals` — verticals.py — 🌐 the money map: every trackable niche, as data.
- `vessel_health` — vessel_health.py — Workstream I: the Vessel-Health organ.
- `vision` — vision.py — Screen perception stack (M45).
- `voice` — voice.py — Voice I/O for Aria (M47).
- `vram` — VRAM accounting. Ported from mos_vram.py — the math, not the ceremony.
- `vram_monitor` — ╔══════════════════════════════════════════════════════════════════════════╗
- `warframe_market` — warframe_market.py — Warframe Market flip-finder: intelligent
- `warframe_vault` — warframe_vault.py — vaulted Warframe ↔ relic mapping, pure logic.
- `weather` — weather.py — ☀ real weather in her voice (free, keyless, open data).
- `welcome` — welcome — Aria greets every new member, warmly and exactly once.
- `work_events` — work_events.py — Workstream A ("Aria's Atelier"): translate a tool's raw
- `work_interval` — work_interval.py — safe interval-stop for autonomous work mode (Workstream N).
- `work_narrator` — work_narrator — her cockpit shift, narrated live to #owner-bridge.
- `work_report` — work_report — she tells you what she did and how to inspect it.
- `work_suggestions` — work_suggestions — grounded ideas for what Aria could work on next.
- `workflow_practice` — workflow_practice.py — EXTERNAL self-practice: watch her do real work.
- `workflow_sentinel` — workflow_sentinel — Aria's execution nervous system.
- `aegis/` — ╔══════════════════════════════════════════════════════════════════════════╗
- `apply_queue/` — apply_queue — durable, dependency-sequenced apply queue + quarantine registry.
- `aria_lm/` — aria_lm — Aria's OWN from-scratch FOSS language model.
- `autonomy/` — autonomy — Supervised Autonomy Sessions: time-boxed, observable, resumable, bounded.
- `canon_embodiment/` — canon_embodiment — the Canon-Embodiment organ: maps every mos_canon.py clause
- `checkpoint_chunks/` — checkpoint_chunks — Workstream P: god-tier conversation checkpoint chunks,
- `clock/` — Clock package — Aria's time grounding.
- `cockpit/` — Operator cockpit — Textual TUI for sovereign-agent (v0.2.15.3).
- `code_school/` — code_school — teach Kevin to read and write the system he already owns.
- `consistency/` — consistency — the one-truth organ: cross-store joins, checked. (FABLE II · M1)
- `core/` — Aria's core: values, narration, celebration, identity continuity.
- `diff_view/` — diff_view — show what code Aria edits: green-add / red-remove (F12).
- `discord_admin/` — discord_admin — the owner-gated admin bot that can edit the server.
- `discord_runtime/` — discord_runtime — the live layer that RUNS a defined bot project, safely.
- `doctor_sentinels/` — Aria's self-healing surface — the SovDoctor sentinels.
- `epistemic_ledger/` — epistemic_ledger — the Epistemic organ: what Aria believes, with what
- `feedback/` — Operator feedback persistence.
- `foresight/` — foresight — Aria's generational foresight + the Ultimate Questions baked in.
- `frugality/` — frugality — Aria's god-tier hardware-requirement reduction engine.
- `godtier/` — godtier — Aria's god-tier system scanner (her inner eye).
- `grounding/` — grounding — the persisted composite epistemic score + standing sentinel.
- `hyperintel/` — hyperintel — the HyperIntel research faculty: a bounded QUESTION -> SCAN ->
- `insights/` — Insight generation. Reflection over facts; writes to the insights channel.
- `integrity/` — integrity — the composite anti-misleading signal: one persisted score
- `intent/` — Intent package — maturity scoring, soon: consequence engine.
- `loose_threads/` — loose_threads — disconnection as a first-class health signal (Fable F1).
- `mem_channels/` — sovereign_agent.mem_channels — concrete memory channels.
- `memory/` — Memory subsystem: atoms, lessons, retrieval. Architecture §8.
- `memory_compact/` — memory_compact — bounded growth with dignity. (FABLE II · M2)
- `model_corps/` — model_corps — the god-tier model roster: one shared hardened persona, generated
- `model_corps_governance/` — model_corps_governance — the standing model-roster governance layer:
- `modes_crown/` — modes_crown — declarative operator modes + her own inner stances +
- `nonclassical/` — nonclassical — bring the non-classical (PEIG/quantum) layer to god-tier parity, measured n
- `nonclassical_supreme/` — nonclassical_supreme — the non-classical layer at its best: a quantum-faithful processor, 
- `osrs_flips/` — osrs_flips — (describe what this module gives Aria). Staged; applied via apply_osrs_flips.
- `path_scan/` — path_scan — god-tier path / anti-ghost / anti-zombie scanner for staged modules.
- `persistence/` — Persistence package — the bones of Aria's durable state.
- `planner/` — sovereign_agent.planner — plan-then-execute over N items.
- `planners/` — ╔══════════════════════════════════════════════════════════════════════════╗
- `proving_ground/` — proving_ground — the standing scored benchmark (Fable F3).
- `qa/` — sovereign_agent.qa — Aria's master builder/tester/hardener surface.
- `quality/` — quality — the persisted quality ledger + standing sentinel. (Quality round · Q1)
- `quantum/` — sovereign_agent.quantum — the non-classical advisory layer (quantum-inspired, pure-Python)
- `reaction_roles/` — reaction_roles — react to an emoji on a message, get (or lose) a role.
- `repo_hygiene/` — repo_hygiene — repo-root file clutter detection.
- `resilience_scan/` — resilience_scan — hardening / robustness / edge-case scanners for BOTH layers.
- `retrieval/` — ╔══════════════════════════════════════════════════════════════════════════╗
- `review_journal/` — review_journal — every work session leaves a reviewable trail.
- `scanner_tier_a/` — scanner_tier_a — the 6 Tier-A scanners from SCANNER_CATALOG.md, built on D's
- `security/` — Security utilities: owner-controlled encryption at rest.
- `self_map/` — self_map — she knows the texture of herself.
- `senses/` — senses — Aria's perception faculties (eyes & ears) with god-tier resilience.
- `shell_corps/` — shell_corps — multi-command shell execution, Claude-Code-tier or above (F10).
- `small_model_bridge/` — small_model_bridge — make the smallest models work in Aria's vessel.
- `small_model_confidence/` — small_model_confidence — keep a small model from silently giving up.
- `spectrum/` — spectrum — the god-tier advocate/audit SPECTRUM (a council of ten perspectives).
- `steward/` — sovereign_agent.steward — Aria's hygiene and health surface.
- `stewardship/` — ╔══════════════════════════════════════════════════════════════════════════╗
- `timeouts/` — timeouts — the persisted timeout classification: reads the SAME
- `tools/` — Tool registry. Importing this package registers all built-in tools.
- `tribunal/` — tribunal — Aria's god-tier scrutiny system (Devil · Angel · Audit + synthesizer).
- `universal_scanner/` — universal_scanner — the Universal Scanner Kernel: one composable pre-flight gate
- `wellbeing/` — wellbeing — the persisted composite value/care/flourishing score +
- `wholeness_gate/` — wholeness_gate — the guardian that keeps her whole when no one is watching.
- `workflow/` — Workflow package — the plan-act-check agentic loop.

## Tests
539 test files · ~6576 test functions (counted, not narrated).

## CLI (`sov`)
36 root commands · 63 command groups:

`appendix` · `archive` · `atoms` · `backlog` · `backup` · `behavior` · `bots` · `cadence` · `channels` · `charter` · `chat` · `commitments` · `compact` · `constitution` · `continuations` · `discord-admin` · `drafts` · `dream` · `edge-cases` · `episode` · `field-notes` · `financial` · `gaps` · `glyphs` · `health` · `heartbeat` · `home` · `honor` · `impact` · `insights` · `interpret` · `keys` · `lens` · `map` · `memory` · `migrations` · `models` · `palace` · `people` · `personas` · `profile` · `projects` · `proposals` · `qa` · `reasoning` · `recall` · `relationships` · `requests` · `reviews` · `reward` · `scout` · `sentinels` · `session` · `shards` · `shop` · `steward` · `stewardship` · `task` · `telemetry` · `theme` · `train` · `vault` · `vram`

## Sentinels
23 sentinels in `stewardship/`:

`atoms_compact_sentinel` · `backup_sentinel` · `cache_sentinel` · `conformance_sentinel` · `defense_sentinel` · `glyph_sentinel` · `godtier_sentinel` · `grounding_sentinel` · `locator_sentinel` · `model_corps_sentinel` · `passive_watcher_sentinel` · `peig_sentinel` · `phantom_sentinel` · `quality_sentinel` · `resilience_sentinel` · `roster_sentinel` · `schedule_sentinel` · `self_integrity_sentinel` · `telemetry_sentinel` · `timeout_sentinel` · `tribunal_sentinel` · `watchdog_sentinel` · `wellbeing_sentinel`

## Env-key catalog
29 cataloged keys (vault: `~/.config/sovereign-agent/shop.env`, masked always):

`DISCORD_WEBHOOK_URL` · `DISCORD_SHOP_WEBHOOK_URL` · `DISCORD_STATUS_WEBHOOK_URL` · `DISCORD_ADS_WEBHOOK_URL` · `DISCORD_AFFILIATE_WEBHOOK_URL` · `DISCORD_BOT_TOKEN` · `DISCORD_OWNER_ID` · `DISCORD_GUILD_ID` · `DISCORD_ENABLE_CHAT_INTENT` · `DISCORD_ENABLE_MEMBERS_INTENT` · `DISCORD_ADS_AUTO` · `DISCORD_DEMO_WEBHOOK_URL` · `DISCORD_OWNER_WEBHOOK_URL` · `STRIPE_SECRET_KEY` · `STRIPE_PUBLISHABLE_KEY` · `DISCORD_BUYLINKS_WEBHOOK_URL` · `REDDIT_CLIENT_ID` · `REDDIT_CLIENT_SECRET` · `BESTBUY_API_KEY` · `GOOGLE_MAPS_API_KEY` · `EBAY_APP_ID` · `BRICKSET_API_KEY` · `BRICKLINK_CONSUMER_KEY` · `BRICKLINK_CONSUMER_SECRET` · `BRICKLINK_TOKEN` · `BRICKLINK_TOKEN_SECRET` · `GROQ_API_KEY` · `CEREBRAS_API_KEY` · `AMAZON_ASSOCIATE_TAG`

## Discord blueprint
24 roles · 9 categories · 40 channels · fingerprint `51b919ae771698b8…`

roles: Aria, Support, Mead-Head, Veteran, Subscriber-VIP, Subscriber-Pro, Subscriber-Basic, Customer, Pass-Holder, Owner-Pass, Admin-Pass, Track-WarframeSets, Track-WarframeRelics, Track-WarframeArcanesRank0, Track-WarframeArcanesMid, Track-WarframeArcanesRank5, Track-WarframeRivens, Track-WarframeMisc, Track-WarframeJackpot, Track-OsrsStarter, Track-OsrsMid, Track-OsrsHigh, Track-OsrsVolume, Track-MeadBrewing
categories: ADMIN, BACKEND, WELCOME, SHOP, LOUNGE, SUBSCRIBERS, MEAD LOUNGE, WARFRAME, OLD SCHOOL RUNESCAPE

## Doc registry
24 registered docs — all present ✅

