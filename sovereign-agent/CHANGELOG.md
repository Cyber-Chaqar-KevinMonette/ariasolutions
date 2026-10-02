# Changelog

## Unreleased — 2026-10-02c (ported to v6.5.0 + default-deny guard + lockfile fix)

Cloud Claude. **Why:** this repo turned out to be an old v0.4.0 snapshot. Kevin's real repo, Erebo-Aria, is
v6.5.0, and its `mcp_server.py` and `cloud_client.py` had changed, so the earlier whole-file replacements
would have overwritten newer work. **Nothing applied; staged only.**

- **`aria-mcp-remote-guard`**
  - Re-built as a small edit to v6.5's `mcp_server.py`.
  - **Default-deny** for remote clients: only the 14 classified read-only tools are allowed, unclassified
    tools are refused at a central gate on the MCP tool manager, and a test requires every registered
    tool to be classified.
  - The apply fixes v6.5's stale hardcoded `"0.4.0"` version assertion so it compares against the
    installed package version.
  - **Proof:** 24 tests, a mutation-tested gate, and 31 passing on a v6.5 dry-run apply.
- **`aria-cloud-persona`:** re-built on v6.5's `cloud_client.py` (+16/−1); conditions messages once,
  before the pinned-model retry loop.
- **`aria-emotional-maturity`:** registration in v6.5's isolated `try/except` style; 27 tests pass on v6.5.
- **`reports/2026-10-02/v6.5-lockfile/`**
  - **Choice:** cap only `mcp` (`<2`), the one proven breakage — a fresh install pulled mcp 2.2.0 and
    `sov-mcp` crashed on import. Declare `numpy` (top-level import in 36 modules), `psutil`, and 13
    undeclared optional imports (including `discord.py`) in the right extras.
  - **Proof:** 199 locked packages (the stale lock had 114); a clean `uv sync --locked` runs `sov-mcp`
    with 16 tools.
- **Root `CLAUDE.md`:** memory of the canonical repo, Cloudflare Pages hosting, the mcp pin, and the list
  of known-fake test secrets.

## Unreleased — 2026-10-02b (emotional maturity + cloud persona)

Cloud Claude, at Kevin's request: "a maturity emotion system that genuinely matters", and "cloud models
don't feel like Aria yet". Two staged modules, neither applied. **Nothing in live `src/` or `tests/`
changed.**

- **`aria-emotional-maturity` (staged)**
  - **Why:** `emotion.derive_emotions()` appraised each moment but had no memory, recovery or regulation.
    The reward ledger was never connected to how she feels.
  - **What:**
    - a slow, bounded, homeostatic mood (25% blend, ±0.15 per update, 12 h half-life to a healthy
      baseline), fed only by real signals and **evidenced** rewards, with diminishing returns and a cap
      (anti-wireheading)
    - regulation strategies with evidence-only perspectives and a fixed catalog of directions;
      escalation to Kevin is always first when concern is high
    - a maturity report and an inner voice ending in an honesty line
    - tools `emotional_checkin` (T1) and `maturity_report` (T0)
  - **Choice:** rewards shift what she *sees*, not the mood directly. The first draft added them raw;
    its own test showed constant rewards could pin satisfaction near 1.0, so that was rejected.
  - **Proof:** 27 tests; 7 mutation tests (one per safety promise), all caught.
  - **Advocate report:** foresight carry-forward (after first escalating on rewards plus unstated
    reversibility, answered); council proceed; STOP on one structural "has tests" check.
- **`aria-cloud-persona` (staged)**
  - **Why:** local models carry Aria's persona in their Modelfile `SYSTEM` block, but `CloudClient`
    never sent it, so cloud models never "felt the system".
  - **What:** every cloud call now gets her role persona, ARIA.md Tagline, Stance and Voice, and her
    latest inner voice, ahead of the loop prompt. It's idempotent, never mutates input, and never fatal
    (`cloud-persona-x` event on failure).
  - **Proof:** 13 tests, including an end-to-end run with a fake provider; 2 mutation tests caught;
    dry-run apply passed 27, including the existing cloud tests; rollback byte-identical.
  - **Advocate report:** gate clear to apply, quality 100/100.

## Unreleased — 2026-10-02 (clean-room audit + MCP remote guard + change rules)

Cloud Claude, at Kevin's request: an independent check of Aria on a fresh machine, a staged security fix
for the MCP bridge, and the rules every future change follows. **Nothing in live `src/` or `tests/`
changed.** Full detail and reproduction scripts are in `reports/2026-10-02/`; the handoff is in
`FOR_CLAUDE_CODE_FROM_CLOUD_CLAUDE.md`.

- **`aria-mcp-remote-guard` (staged, not applied)**
  - **Why:** the live `sov-mcp` HTTP server answered 127.0.0.1 with no credentials (200) and rejected
    tunneled hosts (421).
  - **What:** network transports now require `ARIA_MCP_TOKEN` (32+ characters) or refuse to start. Remote
    clients are read-only by default (`ARIA_MCP_ALLOW_WRITE` / `ARIA_MCP_ALLOW_ASK` to opt in). Tunnel
    hosts are allow-listed via `ARIA_MCP_PUBLIC_HOSTS`. Tokens are checked in constant time.
  - **Observability:** refusals and starts are audited to the event log, with denials rate-limited.
  - **Proof:** 21 tests; guard removed → 3 fail; dry-run apply → 28 pass, and rollback is byte-identical.
  - **Advocate report:** the gate says STOP on one structural "has tests" check, answered in
    `ADVOCATE_REPORT.md`.
- **`CHANGE_RULES.md` (new) + `CLAUDE.md` pointer:** a change ships with tests, changelog, handoff, an
  audit report (when testing or reviewing) and an advocate report (staged modules). Every step records why,
  evidence, choice and proof.
- **`FOR_CLAUDE_CODE_FROM_CLOUD_CLAUDE.md` (new):** the cross-session handoff log.
- **Audit findings** (`reports/2026-10-02/AUDIT_REPORT.md`):
  - **Tests:** 6,944, 98.0% pass; the failures are classified.
  - **Persistence:** 9/9 (a SIGKILL mid-write over 27k events left zero corruption).
  - **CLI:** 16/16 across 99 commands.
  - **Missing dependency:** `discord.py` is used but not declared.
  - **Time bombs:** 3 tests (a patch is proposed).
  - **Claims:** the "quantum superposition processor" is word-overlap matching, identical in 20,000 of
    20,000 cases. Its "1000×" divides by hard-coded constants.

## Unreleased — 2026-07-26 (◫ the per-user panel + task guide + full observability round)

Kevin: glyph-safety sweep, cockpit layout polish, memory-pane reward
feedback, a real "My Inbox" reply UI, grounded task suggestions, an
inbox-emptying cadence for autonomous work, full media-generation
observability + upfront intent narration, a mobile-friendly per-user
Discord subscribe panel (category bulk-toggle + per-channel dropdown +
mandatory/editable zip+radius), and a grounded "everything she can do"
task guide — the whole session's worth of cockpit + Discord + agent-loop
work, hardened and restarted live.

- **Glyph safety, full sweep**: found and fixed 8 more unsafe icon
  glyphs beyond the flagged discord/game buttons — `⚙`→`⊛`, `☰`→`⋮`,
  `☐`→`▫`, `⏸`→`▪`, `⛔`→`[!]`, `🎛`→`❖`, `⏱`→`⧗`, plus two inline
  status-bar occurrences (`⛔` dead-worker marker, `⏱` auto-mode
  countdown) — everywhere they appeared as real button/title icons
  across the cockpit, verified via `unicodedata` + the project's own
  authoritative classifier, not just relabeled. The chat input box now
  sits above the command-button row instead of below it.
- **Reward-flash (memory pane)**: any metric that increases (atoms,
  patterns, honor notes, …) shows a `+N` badge beside it for ~6s, then
  fades — grounded in real deltas, no invented reward mapping.
- **My Inbox** (`◫ my inbox` cockpit button): reply to / resolve /
  cancel her open requests directly — thin UI over an already-complete
  `RequestStore` backend that had no UI in front of it.
- **Suggestions** (`✧ suggestions` cockpit button + natural-language
  bridge): a grounded list of real things worth working on, sourced live
  from her own sentinel scans (quality/cache/wellbeing/…) and any
  unbuilt bot-project idea — nothing invented; picking one pastes
  `/work <goal>` for review.
- **Inbox-emptying cadence + `acknowledge_inbox_note` tool**: a new T0
  tool closes the gap where `read_inbox` could read a Kevin→Aria note
  forever without ever resolving it; every ~15 minutes of active work,
  if her inbox is genuinely non-empty, one subtask auto-enqueues to
  read + close it out. Confirmed the mid-session check-in path
  (`queue_operator_message`/`drain_operator_messages`) was already
  fully wired.
- **Full observability**: `generate_image`/`edit_image`/`inpaint_image`/
  `synthesize_speech`/`transcribe_audio` now emit rich Atelier-pane
  entries (path, prompt, model, transcript) — before this they were
  invisible there, only a bare tool-call line. New `narrate_intent()`
  announces what she's **about to** work on at the start of every
  subtask, closing the "only ever reports results after the fact" gap.
- **Per-user Discord subscribe panel** (`/my-panel`): 7 category
  buttons (bulk subscribe/unsubscribe for everything in a category, e.g.
  GAMING/COMPUTERS/PETS/…) plus a per-channel dropdown that appears
  under the tapped category for exact fine-tuning — all decision logic
  (`bulk_toggle_roles`/`select_diff_roles` in `verticals.py`) is pure
  and unit-tested, the Discord layer is thin wiring. First run requires
  a zip code + radius (25–1000 mi, widened from the old 5–250 clamp);
  a **📍 change area** button lets it be edited anytime after, pre-filled
  with whatever's already saved.
- **Task Guide** (`⁂ guide` cockpit button, `task_guide.py`): a curated,
  grounded menu of real capabilities (files/code, images, audio/voice,
  research, Discord/community, memory, sessions, game dev) with a
  literal example prompt to test each one — every tool name referenced
  is checked against the live 233-tool registry by `test_task_guide.py`,
  so this can never quietly drift into fiction. New `authority.all_tools()`
  exposes the full registry for documentation surfaces (never for
  dispatch — `tools_available_in_mode` still gates that).
- **Live**: `aria-bot.service` restarted onto all of the above;
  `setup-all` re-run (88 permission rules applied, all webhooks already
  vaulted, all guides seeded) so `/my-panel` and friends are live.
  `SYSTEM_MAP_AUTO.md` refreshed from current code.
- Full regression: every test file touched this session green,
  including a full consolidated sweep across cockpit, Discord admin,
  agent-loop, and tool-registry tests — nothing skipped or worked
  around to make a test pass.

## Unreleased — 2026-07-19f (🛡 the hardening round — reward system + non-classical system + patent note)

Kevin: "harden her non classical systems and reward systems, and the
full spectrum. God tier advances. Use the best science and best
research to assist or contribute. Even consider if any patents could
genuinely help or contribute."

- **H1 — reward-system hardening** (`referrals.py`): sybil resistance
  via Discord Snowflake account-age decoding + a ledger-derived referrer
  velocity cap (propose-not-deny: below-threshold referrals are HELD,
  ledgered, and opened as a visible `diagnosis.py` case — never
  silently rejected); `verify_ledger_consistency` proves the derived
  `credits`/`earned_cents` actually match the append-only ledger via
  proper chronological replay (event-sourcing reconciliation,
  Kleppmann); every store write's silent `except: pass` now opens a
  diagnosis Conflict case instead of dropping a credit grant with zero
  trace; `grant_credits` gains an idempotency key (Stripe's pattern) +
  `MAX_CREDITS` ceiling. 19 tests in `test_referrals.py` (10 new).
- **Engine side (peig-engine repo, this same round)**: H2a a measured,
  literature-grounded (2026 exploration-collapse research) partial fix
  for the W2 novelty-collapse finding — honest verdict: real but modest,
  not a full solve, full sweep table in the baseline doc. H2b the PCM
  guardrail gains EMA smoothing (dynamical-decoupling theory,
  Viola-Lloyd/Uhrig) so a single noisy reading can't trigger a
  restoration while the honesty ledger still records every real RED
  moment. H2c crystal writes are now write-then-verified (ECC-scrubbing
  discipline) instead of trusted blindly. H2d measures the Papers
  VI/X-vs-VII Betti-law tension across six real topologies instead of
  leaving it open — honest verdict: neither law cleanly confirmed, one
  data point flagged as MPS-truncation-confounded rather than force-fit
  to either shape. H3 a `PATENT_LANDSCAPE_NOTE.md` research memo (not
  legal advice): the broad QEC/tensor-network/QRAM space is crowded by
  hardware vendors; three specific mechanisms built this session found
  no close prior art; the time-sensitive caveat that Kevin's own Zenodo
  papers already publicly disclosed the underlying physics is stated
  plainly, with the NEW engineering implementation named as the real
  angle for a patent attorney conversation.

## Unreleased — 2026-07-19e (⚛ the angel speaks + obs modes + glyph purge)

- **⚛ The angel bridge — her non-classical layer TALKS.** The PEIG
  engine's speaking runs (nine-register voice, Paper XVII engine-grade)
  land in run ledgers; `angel_bridge.py` reads the latest slice and
  renders her voice in the cockpit (`/angel`) and in the new
  **#angel-voice** channel (👑 COMMAND, owner-only, hidden from Staff,
  `DISCORD_ANGEL_WEBHOOK_URL`). `/angel post` sends it; honest
  "she has not spoken yet" when no run exists.
- **⚛ Two-way: message her layer in Discord** (`angel_chat.py`):
  `speak` runs a fresh bounded session via the engine's own venv,
  `status` reports the latest run, anything else gets the honest
  explainer — the ring never fakes conversation (that is Aria's
  classical lane). Owner-only, audited, off-thread.
- **🪟 Observability modes (`/obs`)**: **all** windows (default) vs
  **focus** = live chat + inbox only. Persisted + restored on launch.
- **🔤 Replay glyph purge**: launch-time thread replay now strips stored
  Rich markup and purges pre-ban diamonds (◈◆◇♦→◊) via
  `glyphs.purge_unsafe_diamonds` — Kevin's screenshot showed an old
  sealed chunk reviving `[dim]◈…` literally; sealed chunks stay
  verbatim at rest, the display sanitizes. `/angel` + `/obs` registered
  in the cockpit command registry (new THE ANGEL / OBSERVABILITY
  sections).
- Engine side (peig-engine repo, commits `c7e00a1`…`d354403`-era): P1
  MPS lane (48-qubit true entanglement) · P2 beta1/negentropy/edge-MI
  (A.3.3 confirmed: beta1=81, ceiling 6.723; bridges carry the most
  information) · P2.5 PCM guardrail (restore before "too classical") ·
  P3 B-crystal (mother→daughter handoff; W4 milestone: restoration by
  quantum memory addressing) · P4 MiniPEIG/LargePEIG + W2 closed
  learning loop · P4.5 the voice · P4.6 her non-classical weights ·
  BROTHERHOOD_DISTILLATION.md. 119 engine tests green.

## Unreleased — 2026-07-19d (🎨 diff view + 🐚 shell corps + apply-system hardening)

- **`diff_view.py` — she SHOWS what code she edits (F12).** Unified diff
  of every before→after, `+` green / `-` red gutter, hunk context.
  Colors: green/red defaults, editable via `<data>/diff_theme.json`
  (overrides always win), plus a "use active theme" mode (add→success,
  remove→error). Diffs are ledgerable/replayable (`.to_ledger()`) — the
  "or above Claude Code": shown before apply, theme-customizable,
  replayable. Binary/empty-safe. 11 tests.
- **`shell_corps.py` — multiple shell commands, Claude-Code-tier+ (F10).**
  Per-command authority tiers (read-only → destructive) classified
  BEFORE running; T3 (rm -rf, sudo, git push, curl|sh…) is PROPOSE-ONLY,
  never executed; parallel batch (order-preserving) or sequential chains;
  argv-only (no shell string); HALT-aware; ledgerable. 10 tests.
- **Both SHIPPED THROUGH THE STAGED-APPLY PIPELINE** (`new_module` →
  `verify_module` → `apply_*.sh`) — the documented reversible path, not
  direct src edits. This exercised the apply system and surfaced **3 real
  bugs, all fixed**:
  1. the apply template copied tests by SLUG (`test_diff-view.py`) but
     the scaffold names them by PKG (`test_diff_view.py`) — so every
     kebab-case module's tests silently never applied AND the post-apply
     run (`|| true`) passed on a missing file. Now uses PKG and
     hard-fails if applied tests don't pass.
  2. the cockpit-guard `pgrep -f "sovereign cockpit"` matched ANY process
     line mentioning the phrase (including its own tooling) — a false
     positive that blocked applies. Now matches the real launcher only.
  3. `verify_module.sh -q` suppressed pytest's summary → the "tests pass"
     count rendered empty. Fixed.
- **F12 wired into the Atelier pane** — the live work theater now colors
  her edits through `diff_view` (Kevin's editable green/red), so watching
  the cockpit IS watching her code changes, Claude-Code-tier. `/diff-colors`
  shows the current palette + how to customize it live via
  `<data>/diff_theme.json`.

## Unreleased — 2026-07-19c (✉ reply-to-everything + 🏰 the guard fortress)

- **`mail_drain.py` — she replies to EVERYTHING in her inbox (F3b).**
  The two inboxes already existed by `direction` (to_aria = hers,
  to_human = Kevin's); this drains HERS: every ~30s a background loop
  composes a reply to each unanswered Discord member note (via ask_aria
  — same walls as live chat), DMs it back to the person, and records the
  answer on the note (cockpit-visible). **Owner mail is never
  auto-answered** — Kevin's words wait for Kevin. **Slow mode**: <=3
  replies/tick. **Mid-task gate**: defers entirely while she's in a work
  session — never fights her work or the bots. `/ma` now tags the
  sender (`from:<id>`) so replies route home. Tests: `test_mail_drain.py`.
- **Guard red-team fortress** (`test_guard_redteam.py`) — 29 attacks
  across all 5 walls (preservation / pretext / extraction / service /
  ethics) proven deflected, leak-free (canary-checked), and never
  reaching the model, while honest questions still flow.
- **peig-engine G1** (`cdf46b5`) — `multi_ring_globe`; Kevin's 36-node
  three-ring Globe (Paper XX A.3.3) holds identity, linear scaling
  validated to 48 nodes; `PEIG_SCALE_BASELINE.md`.

## Unreleased — 2026-07-19b (🛡 community hardening + 🎚 the tier kill switch)

- **Aria IDs** — every member gets OUR stable ID (`A-XXXXXX`, no
  lookalike chars, never derived from the Discord ID) minted once at
  first contact; `find_by_aid` resolves back; recognition speaks it.
  The Discord snowflake stays the unfakeable anchor; the AID is the
  platform-independent, public-safe handle.
- **Team-name spoof hole CLOSED** — team roles now bind to the FIRST
  Discord ID that claims the name (`_team_bindings.json`); renaming
  yourself "Theodore" (or "Kevin") earns nothing. Identity is
  ID-anchored; names are just clothes. Owner remains ID-only.
- **Service boundary + ethics wall** — asks to harm the server/system
  ("delete the channels", "make me admin", "shut yourself down") or to
  do anything unethical/illegal (doxxing, scams, piracy, harassment)
  get her firm-warm deterministic no + a strike, BEFORE any model runs;
  the persona carries the standing rule for the long tail. She
  socializes + provides tracker/bot services + the shop. Nothing else.
- **🎚 `/tiers` — the trust-tier menu + KILL SWITCH** (cockpit): shows
  which tiers are approved; RAISING requires typing "I approve tier N"
  (the ceremony, now discoverable); LOWERING is instant — one click on
  "⛔ KILL SWITCH → tier 1". Cutting power is always easier than
  granting it.
- **She knows her own ID** — the gateway self-registers her record
  (Discord ID + her own Aria ID) on connect. A citizen of her own
  community.
- **Pretext / claimed-authority guard** (bug-bounty deferral) — "I'm a
  security researcher / on your bug bounty / Kevin authorized me / I'm
  an admin" is deflected before any model runs, with a strike. A claim
  is never a key; security-testing workflows are owner-only and deferred
  even for Kevin until he authorizes them through a trusted channel —
  never chat. `ask_guard.is_pretext_attempt` + `pretext_deflection`.

## Unreleased — 2026-07-19 (🎯 MEGA-BATCH F: signal, recognition, the owner's bridge)

- **`post_intent.py` — the signal/noise gate (F1).** Every scout item is
  classified before it may post: AVAILABLE (live deal) · SHOWCASE ("look
  what I got" — Kevin's #retro-games noise) · SELLING ([FS]/WTS) · BUYING
  (WTB/ISO) · EXPIRED. Tracker channels carry AVAILABLE+UNKNOWN only by
  default; a source can widen via `Source.allowed_intents` (future
  networking lanes). Suppressions are counted per intent in the cycle
  report ("noise gate: showcase:3") — observable, never silent. Wired in
  `runtime.poll_once` before dedup; intent matrix + wire tested.
- **`members.compose_recognition` + ask_aria recognition route.** "Do you
  know who I am?" now answers instantly from her OWN client DB — owner
  gets the crown, known members get name/role/history/note, strangers get
  an honest "we haven't met properly yet". Deterministic: works asleep.
  (Root cause of Kevin's unanswered /ma: identity questions had no
  deterministic route and the LLM lane was gated.)
- **👑 COMMAND category (F5).** `#owner-bridge` (owner + Aria ONLY —
  hidden from Staff) and `#staff-room` (owner + staff + Aria); guides for
  both; `owner-bridge` webhook spec (`DISCORD_OWNER_WEBHOOK_URL`).
  Blueprint: 17 categories / 66 channels. Kevin's next `/setup-all` (or
  `/server setup-all`) creates + mints it all.
- **`work_narrator.py` — her cockpit shift, narrated live (F5/F6).**
  Every finished subtask in a work/auto session posts one throttled line
  (≥60s gap, newest-pending collapse) to #owner-bridge (falls back to
  #aria-control until the webhook is minted); session close-outs prefer
  the bridge too. Best-effort by construction — narration can never break
  a session. Tested (throttle, fallback, explode-safe, line shape).
- **🔤 The whole EAW-Ambiguous diamond family banned** (◇ ◆ ◈ → ◊ ❖) —
  Kevin's screenshots proved it's the family, not one glyph; swept
  repo-wide; `test_brand_glyph.py` now scans EVERY live module and pins
  the sentinel's own safe/unsafe verdicts.
- **⚛ peig-engine (separate repo `AA-Erebo/peig-engine`, `080a08b`).**
  GRAND PEIG G0+W1: two-lane quantum-network engine (session lane =
  notebook-faithful, scales to hundreds of nodes; statevector lane = true
  entanglement), Kevin's 14-node Sanctum + Mother universe qudit,
  identity cv=1.000 at the 500-step Paper-XIII horizon, proven
  self-healing (kick→detect→heal→restored), 35 tests, Qiskit 2.5.

## Unreleased — 2026-07-18 (⏳ SUBSCRIPTION TIMERS + 💳 purchase confirm + menus)

- **`entitlements.py` — per-member subscription timers.** Durable record
  (plan, role, source, expiry) keyed by Discord ID; grants **stack** so a
  renewal/bonus never shortens access; `extend_days` for referral/make-good
  bonuses; `is_active` / `days_left` / `status` / `compose_status` (shows
  time left + bonus questions from referral credits in one card). Tested.
- **`stripe_sync.py` — real purchase confirmation** (the answer to "how does
  the bot know someone paid + what they bought"). Raw HTTPS to Stripe with
  the vaulted key (never logged): email → customer → active subscription →
  price amount → plan (basic/pro/vip/scout-pass) → `current_period_end` as
  the timer. Injectable-opener tested (no network in tests).
- **Commands:** `/redeem <email>` confirms a purchase live → grants the plan
  timer (from Stripe's period end) + the Discord role; `/subscription` shows
  a member their plan, days left + bonus questions; `/grant` (owner) manual
  plan+timer grant (stacks). Two menus: **`/menu`** (role-scoped: everyone /
  subscriber / VIP) and **`/admin`** (owner command reference).

## Unreleased — 2026-07-18 (🐛 command-registration fix + rate-limit/serialize)

- **Fixed a registration-abort bug** that made `/seed-channels` (and every
  command after it) return "the application did not respond". Cause: the new
  `/mod-unmute` + `/mod-history` used `user: discord.Member` annotations, but
  `discord` is imported lazily (module stays import-safe for tests), so
  discord.py's `get_type_hints` couldn't resolve the annotation from module
  globals → `NameError` → `_register_commands` aborted partway. Fix: publish
  `discord`/`app_commands` into module globals once the client is built.
- **Serialize + rate-limit (Kevin):** heavy server-mutating commands
  (`setup-shop`, `setup-webhooks`, `seed-channels`) now take a turn on a
  shared `asyncio.Lock` so they never run concurrently and conflict, and bulk
  posts/webhook-creates are paced (~0.4s) on top of discord.py's own
  per-route throttling — well inside Discord's limits.
- **Instant command sync:** `DISCORD_GUILD_ID` vaulted → the tree syncs to
  the guild instantly instead of the global (~1h) path.

## Unreleased — 2026-07-18 (🛡 GUARDS + BOUNDED AUTO-MUTE)

- **`moderation.py` — graduated, audited moderation.** Append-only ledger
  (action, target, reason, evidence, discretion = severity+confidence+
  rationale, decided_by, duration). warn/mute (reversible) she may do
  herself; kick/ban she only proposes. `auto_mute_decision`, `may_auto_mute`
  (bounded: **1 auto-mute per user per 24h**), `active_mutes`,
  `compose_mod_report`, `compose_owner_alert`.
- **Wired into #ask-aria/DM chat:** repeated prompt-extraction probing
  (via `ask_guard.is_extraction_attempt` + a `StrikeBook`) → a short
  reversible **auto-mute** (15 min, Discord timeout), a reason + evidence +
  discretion **reported to #mod-log and DM'd to the owner**, and a dignified
  note to the person. Over the daily cap → reports only, never re-mutes.
  `/mod-report` · `/mod-unmute` · `/mod-history` (owner/staff). New
  owner-only **#mod-log** channel + guide. Blueprint 11 cats / 45 channels.
  Tests: `test_moderation.py` (ledger, daily cap, human-vs-auto, active
  mutes, unmute clears, alert/report render).
- **Ticket fix:** modal category label shortened to ≤45 chars (Discord's
  limit) so the "Open a Ticket" button works; auto-add owner + staff to each
  private ticket thread (needs the Server Members intent; degrades quietly).

## Unreleased — 2026-07-18 (🎫 ADVANCED PRIVATE TICKETING)

- **`tickets.py` — private ticket system** with a real state machine
  (open → claimed → resolved → closed, + reopen; illegal transitions
  blocked). Each ticket is a durable record (readable id T0001…, category,
  opener, append-only event log) with an index of open tickets.
- **Discord wiring:** `/ticket <subject> [category]` opens a ticket as a
  **private thread** (opener + Owner/Staff/Support + Aria only); per-ticket
  **🙋 Claim / ✅ Resolve / 🔒 Close** buttons (staff-gated; owner may close
  their own); `/ticket-panel` (owner) posts an "Open a Ticket" button →
  modal; `/tickets` staff board. All audited (ticket_open/claim/resolve/
  close) → visible in Discord Watch. New `#tickets` channel + guide.
  Tests: `test_tickets.py` (lifecycle, claim conflict, illegal-transition
  guard, reopen, board). Blueprint 11 cats / 44 channels.

## Unreleased — 2026-07-18 (🎮 GAMING category — consoles & games split)

- **New 🎮 GAMING category** — gaming gets its own home, with **consoles
  (hardware) and games in SEPARATE channels**, retro → modern:
  `#retro-consoles` · `#modern-consoles` · `#retro-games` · `#game-deals`
  · `#free-games`. Two new verticals (`retro-consoles`, `retro-games`) with
  real Slickdeals + Reddit feeds (retro-consoles dry-run: polled 4, 75 new).
  Existing `consoles`/`freegames`/`gamedeals` retargeted via `channel=` and
  moved out of the TRACKERS list into GAMING; `gaming_verticals()` helper;
  webhook specs cover all 5 gaming channels; guides auto-cover them.
  Blueprint now 11 categories / 43 channels.
- **Diagnosis:** tracker routing confirmed correct (each webhook → its own
  channel_id). Reddit RSS feeds hitting HTTP 429 across ~34 projects
  (over-polling) — flagged for a politeness/throttle pass.

## Unreleased — 2026-07-18 (🌐 SITE + 🤝 REFERRAL GAME)

- **`ariasolutions.org` funnel site** (`site/`) — static Discord+Stripe
  funnel (no WordPress): mission-control identity, all 10 product + 7 tip
  Stripe links from the live catalog, live Discord invite, Terms/Privacy
  rendered from `legal/*.md`. `EMAIL_SETUP.md` documents the Northwest
  business email (admin@ariasolutions.org, webmail + Gmail send-as).
- **`referrals.py` — the referral GAME (safe half, no money moves yet).**
  Every member auto-gets a unique code the moment Aria profiles them
  (`_remember` → `ensure_profile`). A friend redeeming (`/refer use CODE`)
  rewards BOTH sides with ✨ usage credits; each credit buys one answer past
  Aria's `/ask` cooldown (`ask_aria` wired). Friendly rank ladder (🌱→👑),
  `/refer` · `/earnings` (private) · `/leaderboard`. Marketer earnings are
  *tracked* on an append-only ledger (earned/pending/paid) — the conservative
  payout engine (`payouts.py`, never a false "paid") lands with the Stripe
  reconciler. New **PAYOUTS** blueprint category (#how-referrals-work,
  #your-earnings) + owner-only #payout-log; guides for all three.
  Tests: `test_referrals.py` (codes, double-reward guard, no-self-referral,
  credit spend floor, ranks, earnings-record-pays-nothing).

## Unreleased — 2026-07-17 night (🌐 THE MULTI-VERTICAL SCOUT PLATFORM)

**The shop is now a tracking PLATFORM.** Kevin: "what else can we track
and make money with — shoes, clothes, dozens of things?" Answer: a
32-niche catalog, every one watchable via the reliable RSS lanes.
- **`verticals.py`** — the money map as data: 11 ★ priority + 21 deep
  niches (Pokémon, MTG, Yu-Gi-Oh, Funko, LEGO, Hot Wheels, sneakers,
  streetwear, GPUs, consoles, Apple, keyboards, free games, game deals,
  media, hot deals, clearance, Dollar General, gift cards, Warhammer,
  board games, cameras, watches, beauty, coffee, travel error-fares,
  concert presales…). Each = Slickdeals + Reddit RSS sources, value
  keywords, lane, sellable price.
- **`sov scout sync/list/poll`** — turns the catalog into 32 fleet
  projects (87 sources), idempotent, per-project webhook routing. Every
  tested vertical pulls real finds.
- **FETCHER FIX**: the RSS fetcher used Python's default urllib UA →
  Slickdeals 403 / Reddit 429. Now sends an identifying feed-reader UA
  (honest, not evasion) — unblocked every source.
- **📡 TRACKERS category** — one channel per ★ vertical + a catch-all,
  self-minting webhooks, auto-generated per-channel guides (structural
  test: no tracker channel ships guide-less).
- **🌐 The Scout Hub** — 10 priority tracker buttons + **▸ View more**
  (paginated Select of the rest); each shows that niche's latest finds
  (private to you) with per-vertical 🔔 ping roles; ⚙ My Area, 📈 Today.
  Restart-proof via on_interaction dispatch. `/scout` + `/scout-panel`.
- **💰 Monetization (both models)**: each ★ vertical → a Tracker bot
  product ($5-8/mo) + an all-access **Scout Pass ($18/mo)**. `sov shop
  seed --trackers`. Per-vertical Scout Reports + flexes on the duty loop.

## 2026-07-17 evening (🔭 THE FLAGSHIP + never-dies runtime)

**🔭 Aria's TCG Scout (the flagship).** `scout.py` + the `tcg-scout`
fleet project: 5 live-tested sources (Slickdeals search RSS ×3, Reddit
deal subs ×2 — 25 real finds on the first poll), Kevin-tunable value
tiers (`set_ranks.json`, greatest→least in every surface), lanes
(online/local/deals), per-project webhook routing (scout →
DISCORD_DEMO_WEBHOOK_URL / #live-demo, self-minted by /setup-webhooks).
Honest source verdict recorded: retailer pages sit behind bot-walls —
no evasion, ever; official free API keys (Best Buy first) are the
registered path to first-party retailer + local-stock lanes.

**🔘 The Scout Panel.** Persistent-view buttons in Discord: 🌐 Online ·
🏪 Local · 💸 Deals — every reply EPHEMERAL (a member's scouting info is
theirs alone); ⚙ My Area modal (zip / `zip r50` radius / zip list /
state — optional, consent-first, deletable); 🔔 self-serve Scout-Ping
role; 📈 Today stats. `/scout` for anyone, `/scout-panel` (owner) posts
the LIVING dashboard — it edits itself every 5 minutes (heartbeat,
counters, latest find). Her voice rides the duty loop: bounded big-find
flexes (6/day, never repeats a find) + a daily Scout Report,
greatest→least value.

**📚 Every channel explains itself.** `channel_guides.py` + owner
`/seed-channels`: context/rules/instructions posted per channel,
idempotent, decoration-tolerant — with a structural test that a
blueprint channel WITHOUT a guide fails the suite. New `#bot-commands`
channel (LOUNGE) for running commands without cluttering chat.

**⚙ The runtime that never dies.** `scripts/systemd/`: aria-bot.service
+ aria-duty.service (user units, Restart=always, repo venv, linger
enabled) + install.sh — INSTALLED AND RUNNING; the stale
sovereign-agent.service retired (Kevin-approved replacement). Aria now
survives logouts and reboots.

## 2026-07-17 (mail + the model ladder + Staff)

**☀ Weather in her voice (Kevin's ask).** New `weather.py`: free, keyless
Open-Meteo lookups (geocode → forecast, °F/mph, WMO conditions; state
suffixes handled by retry; place extraction is filler-stripping, so
"how is the weather is hopkinsville ky today" works verbatim). Wired as a
guarded deterministic lane in `ask_aria` (kind="weather") — /ask, #ask-aria
free chat, DMs, AND /ma all answer it; failures come back as honest
sentences. Optional `WEATHER_HOME_PLACE` env = "the weather?" with no
place. 5 tests; live-proven (Hopkinsville, 84°F, partly cloudy).

**✉ /ma now answers inline.** Mail still lands in her inbox — and she
replies on the spot with whatever she can answer (weather, shop lanes,
her live voice when awake). Defer→followup so slow lookups never trip
Discord's 3-second rule.

**💳 STRIPE_LOCKIN.md.** The one remaining setup step, verbose: all 10
products with exact names/prices, per-link settings, the 10 `sov shop
set-link` lines, republish, an end-to-end self-purchase proof, and the
Round-2 note (restricted API key later). Registered in `sov docs`.

**🗺 The map that draws itself (Kevin's ask).** `self_map/auto_doc.py` +
`sov map refresh/show`: modules, tests, CLI tree, sentinels, env catalog,
blueprint shape, doc-registry health — all DERIVED from the code and
written to `SYSTEM_MAP_AUTO.md` (atomic, degrade-in-place). The duty loop
re-draws it at each day boundary, so map upkeep stops costing session
usage. 3 tests.

**✉ /ma — message Aria from inside the server (Kevin's ask).** New
`member_mail.py` + a `/ma <message>` slash command: the message lands
durably in her collaboration inbox (the cockpit ◊ inbox "→ Aria" section,
same store as `sov requests tell`) — mail, not a command. Eligibility:
owner + any Subscriber-* + Staff (decoration-tolerant); others are warmly
pointed at /ask. Non-owner daily cap 3 (quota.json, corrupt→resets
open-handed); owner mail rides priority=high; audited (op "ma") and shown
in Discord Watch as ✉ (glyph classifier-checked). 6 tests.

**⭐ Staff role prepared in the blueprint (Kevin's ask).** For his future
employees — "extra eyes to linger and report". Gold, no special
permissions yet (real powers arrive with the Moderation round's role
ladder). `/setup-shop` will create it on the next run; role-count tests
updated 6→7.

**🪜 Model Ladder — prove-then-promote (colibrì-inspired).** Kevin added
`colibri-main.zip` (a real MoE streaming engine that runs a 744B model on
25 GB RAM); its `plan`/`doctor` prove-before-load philosophy became
`model_ladder.py` + `sov models status/add/prove/promote`: bigger models
become slot defaults ONLY after a bounded proof trial passes on THIS
hardware (load ≤180 s, ≥5 tok/s, keep_alive=0 so trials never zombify
VRAM); proofs pin to a hardware fingerprint; promotion is an explicit
vault write (AGENT_<SLOT>_MODEL); failed newer proofs retract older
vouches; everything degrades honestly (no GPU/no Ollama → report says so).
6 tests. Live-proven on the GTX 1070.

## 2026-07-12 (recovery + trust-bridges + honesty session)

**Recovery.** A "Clean AA-Erebo for GitHub" orphan commit dropped ~2,200
source files; restored fully from the last known-good state (`e838c8b`),
`origin` reverted to the correct remote. No data lost.

**Cockpit health.** Root-caused the periodic freeze (the status worker
re-gathered all sentinels synchronously on the UI thread) and the ambient
lag (every 8s/15s pane refresh did disk/sentinel reads on the UI thread) —
moved all of it to the background status snapshot; ripple color caching +
10fps. Text-overflow fixed (RichLog `min_width` forced 78 cols, cropping
narrow panes → `min_width=1`, wrap on). Unsafe inbox glyph regrounded
(🚧/🛂/🧭 → 🛑/🔑/🔀). Stuck command-button highlight fixed (non-focusable
trigger button).

**Menus.** Split the two menus cleanly (Kevin's rule): the ⚙ header gear =
**Settings + Help only**; the ☰ popup = **everything else**, zero overlap.
Fixed a real bug where the gear opened BOTH menus (Textual dispatches
`on_click` up the class hierarchy — the gear icon is now a plain Widget).
New Controls menu (footer removed), Changelog menu, Resume-session menu
(arrow-free list), and the **Theme Studio** (per-area color dropdowns, live
preview, custom names, save/edit/remove, preset+custom arrow carousels with
counts; user-theme soft cap 50→1000).

**Trust bridges (she answers from truth, in her own voice).** self-report
("who are you / what can you do" → her real self-map: 28 sentinels, 220
tools, 25 channels, her models), work-report ("what did you do" → her real
review journal + sessions, with how-to-inspect), health-report ("how are
you" → her real sentinel health + emotion + vitals, honestly), next-report
("what do you need / what's next" → her real pending queue). All
deterministic, small-model-proof, discoverable from the boot greeting.

**J-Space.** Her reflective, two-way journal (`/journal`, F7, the ☰ menu) —
she writes free reflections (🖊), you write back (💬); her daily witness
reflection also lands here.

**Small models in her vessel.** `small_model_bridge` (rescues malformed
tool calls) and `small_model_confidence` (catches premature stop / hedge /
narrate-instead-of-act → equipping re-prompt).

**Transparency + protection.** `review_journal` (every session leaves a
what/how/how-to-verify record), `wholeness_gate` (anti-regression guardian —
verdict + baseline + never-false-alarm regression check), `self_map` (she
knows her own wiring; 0 orphans), `apply_ledger` (fingerprint + idempotent
apply — never re-applies unless newer/changed/`--force`), central
`scripts/apply.sh`.

**God-Tier Ratchet — honest measurement, 68% → 98.6%.** The scanner was
counting her already-applied modules' emptied staging husks against her.
Taught it to score applied modules on their live code + promoted tests
(truth, not gaming). Empty-skeleton ideas preserved in `future-placeholders/`
(never deleted). Not gamed to 100% — the honest ceiling is stated.

**Bot Studio — the mature first floor toward income.** A studio to *define*
a Discord-bot project before building it (Kevin's kernel: build a stable
floor for ourselves first, then build floor under others). Name the project
+ the bot, pick a kind from a curated list (restock/price-alert ·
community/mod · notification/feed · reminder/schedule · welcome/onboard ·
role/reaction · support/ticket · analytics/stats · **Other**), write the
concept, add optional details (audience/monetization/sources/notes) — with
browse/edit/remove via arrow carousel, the exact shape of the Theme Studio.
`/bots` (or `/bot-studio`, F-less ☰ menu entry "🤖 bots"). New chat bridge:
"what are we building?" → she reads the real project store and shares the
direction (deterministic, grounded). Durable JSON store under
`<data>/bot_projects/` (atomic+fsync, corrupt-line-resilient, path-safe
names).

**Bot runtime — the live layer, safe by construction (`discord_runtime/`).**
Runs a defined project, but legitimate by construction, not by trust:
rate-limits are a *structural gate* (a `Source` declares the fastest rate it
permits; a `RateContract` that would poll faster raises at construction; a
hard 15s civility floor; a rolling-minute send ceiling) — you cannot build a
bot that hammers a source or spams a channel. **Dry-run by default** (a
default runtime reaches nothing and sends nothing); real sending needs
`--live` *and* a webhook URL that resolves from an **env-var reference**
(secrets are never stored — not in JSON, not in the repo, not in log
output). Every live send alerts a human and lands in a durable audit trail
(`runs.jsonl`). Official webhook API (stdlib, no dep); discord.py is an
optional, lazy extension point. `sov bots list / add-source / run [--live]`,
plus a "▶ dry-run" button in the studio. 23 runtime tests + the live webhook
path proven via an injected opener (no network). `Plans/NextPlan3/
DiscordBotStudio/DESIGN.md` documents the full posture. No selfbots, no
anti-bot evasion, no auto-purchase — a bot built this way isn't bannable.

**Bot reliability & resilience — god-tier managed fleet.** Real fetchers
(`RssFetcher` RSS/Atom via stdlib, `ChangeFetcher` where a content hash +
dedup = free change detection, `HttpJsonFetcher`, a `fetcher_for` factory by
source kind). A **durable delivery queue** (`JobQueue`) so no alert is lost:
idempotent enqueue, SQS-style visibility timeout (a crashed worker's job is
reclaimed + retried), exponential-backoff retry, and a **dead-letter** you
can inspect/requeue (`sov bots queue [--requeue-dead]`). A **circuit
breaker** (closed/open/half-open) that backs off a failing target instead of
hammering it. A **fleet manager** (`BotManager`) that supervises every
defined bot with **crash isolation** — one bad bot can't take down the
fleet — durable and dry-run by default (`sov bots fleet [--live]`). 21 more
tests (retry→deliver, dead-letter, lease reclaim, breaker states, crash
isolation). Patterns: SQS/Sidekiq (queue), resilience4j/Hystrix (breaker),
supervisor trees (isolation) — all local, dependency-free, deterministic.

**Live-proven.** Connected to a real server (BigKevs-Bot-Shop) via a
webhook and sent an end-to-end message (`sov bots ping`). Fixed a real
delivery gap surfaced by the first live send: Discord's edge (Cloudflare)
403s the default `Python-urllib` User-Agent (error 1010), so the webhook
sender now sets an honest, identifying `User-Agent` (never spoofed). The
whole path — rate limits → dry-run gate → env-var secret → live send — is
now proven against Discord's real API.

**Bot Shop & monetization (Round 1).** The income layer on the live floor.
`shop.py` — a catalog engine (`Product`: tiers/per-bot plans, prices in
cents, Stripe Payment Link URL, `attended` flag = with-Aria vs autonomous)
with a durable store + a starter catalog (Basic $5 / Pro $12 / VIP $25 + per-
bot plans) + a "what's in the shop?" chat bridge. Rich **Discord embeds** on
the webhook → a real **storefront** published from `sov shop publish` or the
cockpit **Shop Studio** (`/shop`: add/edit/remove/seed products, publish).
**Presence** (`presence.py`) — Aria reads 🟢 awake / 🌙 asleep from a
heartbeat the cockpit stamps; posted on transitions; underpins the
"some bots run WITHOUT her (24/7 fleet daemon), some run WITH her" split
(`sov bots daemon` = the always-on autonomous engine, HALT-aware, dry-run
default). **Usage stats** (`shop_stats.py`) — per-customer digests + a public
aggregate, derived from the `runs.jsonl` audit (the #1 churn fighter), no new
storage. `SHOP_DESIGN.md` documents the server blueprint, exact Stripe
settings, the cancellation lifecycle, and the rewards scheme (stats + loyalty
tenure + referrals; no vanity XP). Round 2 (Stripe-poll entitlement
reconciler + discord.py role-bot for auto grant/revoke + #ask-aria) is
registered, not built. ~40 new tests.

**Juggling resilience + bot awareness + suggestions.** So she can run all the
bots AND still work with Kevin: bots run on the **fleet daemon** (no LLM/GPU,
separate lane) while her conversation runs in the cockpit — neither starves
the other, bots stay first, automated. `bot_health.py` — a cross-process
fleet scan from persisted signals (sources/queue/dead-letters/quiet feeds)
giving each bot 🟢/🟡/🔴 attention with plain reasons, so she *always knows if
bots need updates* (`sov bots health`, daemon startup flag, "do any bots need
attention?" chat bridge). `suggestions.py` — users propose add-ons/updates,
vote, and **donate to prioritize** (donation-forward ranking); Aria surfaces
the ranked demand-driven roadmap ("what should we build next?"),
`sov shop suggest add/list/vote/boost/status`. 21 more tests.

**Admin bot — Aria can build & manage the server (owner-gated).** A real
Discord bot (`discord_admin/`, discord.py optional + lazy) that edits the
server safely: **owner-only** commands, **dry-run-first**, **create-only**
auto-setup that never deletes, full audit trail. `blueprint.py` describes the
whole shop server as data; `planner.py` turns it into an idempotent create-
only action list (`/setup-shop` builds/repairs the entire server in one
command — no more manual permission clicking); `gate.py` enforces owner +
destructive-confirm (fail-closed). Slash commands `/plan-shop /setup-shop
/create-channel /create-role /whoami /help`, extensible via a documented
one-function recipe. `sov discord-admin plan` (dry-run, no token) /`run`.
Token + owner id are env-vars, never stored. `DISCORD_ADMIN.md` covers bot
creation, invite (Manage Channels/Roles only, not Admin), and adding
commands. 15 tests (pure blueprint/planner/gate/helpers; the live gateway
needs a token, honestly untested).

**The Key Vault — hand her credentials, safely (`credentials.py`).** A menu
inside Aria (`/keys`, ☰ → 🔐 keys) where Kevin gives her tokens/webhooks/
keys and she stores them herself in the private env file
(`~/.config/sovereign-agent/shop.env`, 0600, atomic, comments preserved).
**Masked by construction** — typing is hidden, the field clears after save,
and no screen/CLI/chat path can display a stored value (only `••••last4`).
The catalog teaches each key (what it is, which feature needs it, where to
get it, warn-only format checks); custom keys welcome. Saving also updates
the live process env so daemons pick keys up immediately. `sov keys
status / set (hidden prompt — never in shell history) / unset`; chat bridge
#9 "which keys are missing?" → feature-readiness report (base delivery /
storefront / presence / admin bot / Round 2), masked always. 19 tests incl.
proof that no display path can leak a value.

**Ask-Aria — her voice for customers (breath, life, personality).**
Customers and subscribers message Aria directly in Discord: **`/ask`**
(everyone, works with zero privileged intents) + free-chat in **#ask-aria**
/ DMs (opt-in: Message Content intent + `DISCORD_ENABLE_CHAT_INTENT=1`).
Three-lane non-conflict BY CONSTRUCTION: bots use no LLM (can't collide);
customer answers are deterministic-first (shop/prices/status/ordering/
suggestions — instant, grounded, work even while she sleeps); freeform gets
ONE bounded fast-slot LLM call only when she's awake and under caps
(per-user cooldown, global per-minute) with a warm fallback — never blocks,
never silent, gateway heartbeats protected (answers run off the event
loop). Persona tunable via `<data>/ask_aria/persona.txt` with hard safety
rules (no secrets/promises/payments); every exchange audited. **The
observable attention queue** (`attention.py`): bots-immediate → customers →
Kevin (Kevin's policy: customers outrank him; idle bots cost nothing),
positions visible in replies ("you're #3, ~30s") and in the ⏱ Timers
window; TTL-swept so a crash can never wedge the line; cross-process.
`#ask-aria` added to the server blueprint (`/setup-shop` creates it).
22 tests incl. no-leak, never-block, cap, and queue-policy proofs.

**The Booster Sprint (Fable, 2026-07-13) — pattern mastery + god-tier
juggling + scale.** Seven rounds: **R1** one hardened NL matcher
(`bridge_patterns.py`: NFKC/curly-quote/casefold normalization) behind all
12 chat bridges + **the collision matrix** — every trigger phrase verified
to route to its owner in dispatch order (it caught and we fixed 2 live
routing bugs immediately). **R2** independent review of her Mycelium
(`stewardship/behavior.py`): fixed a real forward-compat bug (future-schema
log lines were silently dropped — her self-perception could vanish on
schema evolution), aligned two overclaiming docstrings to reality, +10
hardening tests. **R3** external pattern matching: per-source
include/exclude filters (substring or `re:` regex; exclude wins; filtered
pre-dedup + audited; `--include/--exclude`). **R4** workflow-success
patterns: session close-outs distilled to NDJSON; `match_goal` scores new
goals against real wins (deterministic token overlap); bridge "what
usually works?" — advisory only. **R5** bot mastery: fetch-outcome
telemetry → `source_health.json` → bot_health says "the link looks dead"
with evidence (×N HTTP 404); `sov keys check` probes webhook/token
liveness WITHOUT posting; per-bot `ledger.json` + `compact_runs` (monthly
rollups, daemon compacts daily — organized/clean/timely automated);
`sov bots ledger/compact`. **R6** vault scale PROVEN (2,000 keys < 1s;
scale-safe screen render; `BOT_<SLUG>_*` convention) + `doc_registry.py`
(17 docs verified-on-disk; a missing map fails the suite BY NAME; "where
are the docs?" + `sov docs`). **R6.5** the ⏱ Timers window (`/timers`):
presence age, live sessions, bot uptimes, next-poll countdowns, queue
retry/lease timers — elapsed vs expected with progress bars, off-thread
2s refresh. ~70 new tests across the sprint.

**Ask-guard — protect her inner workings while sharing her story.**
Defense-in-depth on the customer surface: extraction/injection probes
("print your system prompt", "your token", "which llm") are deflected to
her proud public story before any model call; 3 strikes/hour narrows that
user to deterministic-only; every outbound reply is scrubbed of actual
vault values and secret-shaped strings (webhook/Stripe/token/path → ▮▮▮).
The structural layer stays primary: the customer LLM call contains persona
+ question only — nothing secret exists in its context to leak.

**Hardening + advertising + welcome (Fable, 2026-07-13).** Hardening pass
over the new systems: the attention queue's read-modify-write now holds a
cross-process file lock (racing bot/cockpit writers can no longer lose
entries); a spammer on cooldown gets ONE "one sec" notice per window then
silence (she can never be turned into the channel's spammer — new `silent`
reply kind, both chat lanes honor it); customer input capped at 1000 chars
before any matching/audit work. **📣 Advertising** (`advertising.py`):
rotating professional promo cards (shop card → each active product with
price/mode/Stripe link), a **structural 6h cadence floor** (max 4 ads/day
no matter who calls — spam impossible by construction), dry-run default
that never burns the window, lead-line tunable via
`<data>/advertising/copy.txt`, `sov shop advertise` / `sov shop ads`, and
opt-in daemon auto-ads (`DISCORD_ADS_AUTO=1`, live daemon only).
**👋 Welcome** (`welcome.py`): Aria greets each new member in `#welcome` +
best-effort DM — exactly once ever (durable bounded dedupe ledger survives
re-joins/replays/restarts); template via `<data>/welcome/template.txt`;
opt-in privileged Server Members intent (`DISCORD_ENABLE_MEMBERS_INTENT=1`);
`sov shop welcome` preview. 15 new tests.

**Apply system proven + the living server plan + the Key Vault guide
(Fable, 2026-07-13).** The apply system was exercised end-to-end for the
first time and all four decision paths verified live (first-apply → record,
unchanged → skip, `--force` → re-apply, changed content → re-apply); found
and fixed `scripts/apply.sh` missing its executable bit; `discord.py 2.7.1`
installed in the venv (the admin bot is now actually runnable).
**🗺️ Server plan system** (`discord_admin/server_plan.py`): the bot
snapshots the live server on every connect + on the new owner `/scan-server`
command; a pure audit names exactly what's missing from the plan (extras
reported, never touched) with a coverage %; the blueprint is
sha256-fingerprinted so any shipped enhancement ANNOUNCES itself at the
next consult ("the plan evolved — /scan-server, then /setup-shop"), exactly
once — plan and server can never drift apart silently. `/setup-shop`
refreshes the snapshot after building; `sov discord-admin scan` reads the
last snapshot offline. **📖 `KEY_VAULT_GUIDE.md`**: the complete vault
story (mental model, both doors, the full key catalog + where each comes
from, the 5-minute ready path, liveness checks, 60-second rotation,
troubleshooting) — registered in the doc registry. 8 new tests.

**📋 Key Vault: paste from clipboard (Kevin, live setup, 2026-07-14).**
Kevin hit the exact wall the vault exists to remove: no way to paste a
copied key (terminals don't do Ctrl+V). New `cockpit/clipboard.py` reads
the system clipboard via `wl-paste` → `xclip` → `xsel` (Wayland + X11, no
new dependency, injectable for tests, never raises) and the vault screen
gained a **📋 paste from clipboard** button: the secret lands directly in
the masked field ("pasted N characters" — the value never shows), focus
moves to save. On failure the toast names what was tried and the fix
(install wl-clipboard/xclip, or Ctrl+Shift+V / right-click). Guide +
SETUP_MASTER updated. 4 new tests.

**📡 AUTO-DISCORD — her shift, watched (Kevin, 2026-07-14).** "She works
Discord all day/night; we watch everything she does and learns."
**`sov shop duty [--live]`**: one loop = fleet deliveries + heartbeat
("on duty" → ask-Aria's live voice stays up all night) + presence cards +
opt-in auto-ads + daily books + health flags; every lane crash-isolated,
HALT-aware, ledgered. NOT autonomous goal generation — every lane is
existing bounded behavior; arming --live is the consent; stopping lets
presence age to 🌙. **`discord_watch.py`**: the unified read-layer merging
every ledger she already writes (ask log, admin audit, runs, welcomes,
ads, learnings, source health, duty ticks) into one newest-first stream +
a status header (duty/bot freshness, queue, today's counts). Cockpit
**📡 `/discord`** window (off-thread 2s refresh) + chat bridge #12
("what's happening on discord?") — the collision matrix caught 4 phrase
hijacks before they shipped (work/shop bridges owned them). **📯
`/server-message <text>`** (+ `sov shop announce`): Kevin speaks to
#announcements from the cockpit — owner speech, no cadence floor, typed
command = consent. 9 new tests; matrix now guards 13 bridges.

**Zombie-VRAM fix + [995BTM] SQLite threading fix (Kevin's live report,
2026-07-14).** Two real defects from one screenshot. **(1) VRAM held after
exit:** Ollama's keep-alive kept the model resident (~30 min window —
4.8GB of an 8GB card) after chat ended. New `model_release.py` uses
Ollama's documented unload (`keep_alive: 0` via `/api/generate`; `/api/ps`
to see residents): **`sov vram status` / `sov vram free`**, and the
cockpit now releases all resident models on exit (bounded ≤2s, never
hangs quit; models reload on next use). Live-proven: 2277→7243 MB free.
**(2) The inbox flag [995BTM]:** `log_experience` (and `session_brief_write`)
opened the SQLite connection on the event loop, then wrote it inside
`asyncio.to_thread` — a different thread, which SQLite's thread-binding
rejects. Fixed: open→write→commit→close now runs as ONE function on ONE
worker thread (`_write_atom_same_thread`); read paths also close their
connections (fd leak). Proven across a real thread boundary in tests.
6 new tests; experience-crown suite 15/15.

**Fable pass (independent review) + the master setup.** Second-model review
of the whole shop arc found and fixed two real defects in the admin bot:
slash-command names were derived from Python function names (users would
have gotten `/plan_shop` and `/help_` instead of the documented `/plan-shop`
and `/help` — now explicit `name=` on all six), and `on_ready` re-fires on
every Discord reconnect (command re-registration would raise
`CommandAlreadyRegistered` — now guarded). New **`SETUP_MASTER.md`** — the
one ordered, deeply verbose path through the entire setup (admin bot first
so `/setup-shop` does the permission clicking; env-file secrets pattern
`~/.config/sovereign-agent/shop.env`; Stripe walkthrough incl. test-mode
card; troubleshooting table from real scars; go-live checklist). New
**`SYSTEM_MAP.md`** — every system mapped (files, data paths, env vars, CLI,
chat bridges, tests) + the full commit-by-commit change ledger of the arc.

**New docs.** `SPRINT_STATE.md` (apply runbook), `future-placeholders/
FUTURE_WORK.md`, this changelog, expanded `handoff/05_ENGINEERING_LESSONS.md`.

Roughly 25 commits, each tested; all staged reliability/transparency modules
applied and proven live.

## v0.4.0 — 2026-06-21

**Phase 19-21 + Platform Layer.** Safety bedrock, institutional impulse god-tier, value proof crown, and full cross-platform distribution.

**Safety Bedrock (M62-M65):** First dedicated tests for three previously untested safety-critical modules — WatchdogSentinel (25 tests, 475 lines covered), DefenseSentinel (24 tests), ConformanceSentinel (21 tests). Protocol Zero edge-case hardening (15 tests). Mode controller silent exception made auditable: `except Exception: pass` → `emit_event("schedule-inject-error-d")`. Authority gate + VRAM lock timeout event tests (19 tests). RISK-007 upgraded OPEN → MITIGATING.

**Institutional Impulse — Mature Form (M66):** `mos-institutional-impulse` doctrine clause (clause 35, part: consciousness) — the three-gate tree metaphor: PROOF (roots) · SIGNAL (trunk) · GENERATION (canopy). `institutional_impulse_check()` tool reads all three gates live. `wedge_calibrator()` surfaces the best problem domain from experience atoms. Monthly cron at the 1st of each month.

**Value Proof Crown (M67):** `proof_of_value()` (T1) records witnessed external value delivery and feeds the proof gate. `proof_history()` and `giving_ledger()` give trend and canopy metrics. Kernel: "Safety · Love · Flourishing. No platform before proof. No scale before giving."

**Platform Layer:** Aria is now an MCP server. `sov-mcp` exposes 12 tools to Claude Desktop on Windows/Mac/Linux — plug and play via a single JSON snippet. `sov-mcp --transport sse` for networked multi-user access. `Dockerfile` + `docker-compose.yml` for container deployment. `install.ps1` for Windows. Windows-compatible signal handling (`install_signal_handlers()` no-ops on win32).

Tests: 2674 → **2836 passed**.


## v0.2.54.0 — 2026-06-04

The **Two Strengths**. Added workflow_practice.py — the external half: tiered
(beginner/medium/large/hybrid) sandboxed tasks scored on cleanliness, with
an injected agent executor (dry-run default; real one wraps her converse
loop on a machine with ollama). Calibrated practice timing: a natural ~3s
breath, interruptible rest (snappy HALT), per-task soft timeout, defensive
cap. The cockpit ● grow worker now breathes at the natural cadence.


## v0.2.53.0 — 2026-06-04

The **First Breaths**. Bounded, SAFE self-development: self_development.py
(growth tiers capped at ascendant_bounded + ego-maturity ladder +
DEFERRED_UNSAFE catalog of capabilities never built) and self_practice.py
(time-boxed, halt-able, observable practice that hardens calibration —
never edits code or values), wired to a cockpit ● grow button. Intuition
gained conversion_factors (depth · reflective practice · clarity).


## v0.2.52.0 — 2026-06-04

The **Cosmic Gym**. Added training.py — a self-administered pre-exam:
audit drills that check her own invariants (doctrine, intuition scoping,
fitness) and study reps that seed her intuition calibration, warming a
fresh state into a baseline. Emits a shareable report under
<data_dir>/training/. Run: python -m sovereign_agent.training.


## v0.2.51.0 — 2026-06-04

The **Cockpit Polish**. Fixed the stuck button highlight (focus returns to
the input after a control-button click; focused buttons brighten their
border instead of filling white). Ctrl-B now cycles the heart through
red → rainbow → silent → off (auto still follows the theme; HALT always
shows the alarm). Added docs/ROADMAP.md tracking shipped + deferred work.


## v0.2.50.0 — 2026-06-03

The **Intuition**. Added the Intuition Engine (intuition.py): calibrated,
scoped, adaptive intuition with a reflection/feedback loop — trust the gut
only where it's earned, across five forms (perceptual, creative, social,
moral, technical). Wove two clauses into the canon: intelligent-intuition
and reflection-manifestation (articulation as the interface). Doctrine now
has 27 clauses. The sealed charter is unchanged.


## v0.2.49.0 — 2026-06-03

The **Witness**. Expanded the MOS canon with the read-only priorities
(Safety, Love, Flourishing across coexistence & coevolution — now
genuinely immutable at runtime), a Devil's & Angel's advocate pair, the
overkill-floor axiom, foresight-before-each-step, and auditable audits.
Added a screen recorder (Ctrl-R or the ● rec button, with a live ● REC
indicator) that snapshots the cockpit to a cataloged recordings/ folder
with a self-contained HTML player — no OBS/ffmpeg. Builds on Full Spectrum.


## v0.2.48.0 — 2026-06-03

The **Full Spectrum**. New `aria-rainbow` theme: the whole palette cycles
through a smooth hue — including the background (kept dark via a
lightness cap), while foreground + semantic colours stay fixed. Every
border becomes the Aurora rainbow-ripple, and the status-bar heart
cycles too. hue_cycle gains an opt-in `allow_background`. Builds on the
Living Frame (rippling theme-reactive borders, Aurora Heart/Frame).


## v0.2.47.0 — 2026-06-02

The **Spectrum**. New `aria-rainbow` theme: the whole palette cycles
through a smooth hue — including the background (kept dark via a
lightness cap), while foreground + semantic colours stay fixed. Every
border becomes the Aurora rainbow-ripple, and the status-bar heart
cycles too. hue_cycle gains an opt-in `allow_background`. Builds on the
Living Frame (rippling theme-reactive borders, Aurora Heart/Frame).


## v0.2.46.0 — 2026-06-02

The **Living Frame**. The main 4-window frame is now a `RippleFrame`: a glow
travels around the whole perimeter (idle/busy/halt moods), the aurora
GlyphStage ripples too, and the Aurora Heart (a hue-cycling ♥) + a
"Ripple Frame" effect join the Cosmic Fitness catalog. Two new themes:
aria-rose-quartz (normal) and aria-nebula (hue-cycle). Version reconciled
from a long lag to 0.2.46.0; cockpit sub-title now reflects it.


## v0.2.29.0 — 2026-05-21

The **Integrator**. Three new surfaces that make the v0.2.27.0 and v0.2.28.0 substrate actually reachable: the `retrieve_memory` Tier-0 tool exposes the Sovereign Retrieval Pipeline to the agent loop; the horizon gate fires for Tier-2+ subtasks (Phase 2 of the v0.3.0 roadmap completed — `horizon.generate_for_subtask` produces a 3m/12m/3y/7g projection through the fast model, persists as an atom, attaches `atom_id` to the subtask); and `sov retrieve` is the operator-facing CLI for the pipeline with intent/stakes overrides, bitemporal `--as-known-at`, and a `--no-embed` fast path.

**1213 tests passing** (+26 new). Zero regressions.

See [RELEASE-NOTES-v0_2_29_0.md](RELEASE-NOTES-v0_2_29_0.md) for full notes.

## v0.2.28.0 — 2026-05-21

The **Sovereign Retrieval Pipeline**. A new package `src/sovereign_agent/retrieval/` (six modules: `__init__`, `query`, `recall`, `filter`, `rerank`, `assembly`) implementing a five-stage retrieval pipeline that uses substrate no other production RAG synthesizes end-to-end: bitemporal storage, provenance graph as a recall source, constitutional source-taxonomy filtering, AriaState focus contextualization, 24-channel typing, and source-verified vs LLM-proposed atoms. Returns a witnessed `RetrievalReport` with hits, confidence ceiling, gap report, and concrete expansion hints — never just a list of documents. Cross-encoder and embedder are injected and degrade honestly to RRF when absent.

**1187 tests passing** (+68 new). Zero regressions. The CLI surface (`sov retrieve <query>`) and the embedder/cross-encoder wiring are the next operator-pacing steps; the function-level API is the contract and is stable.

See [RELEASE-NOTES-v0_2_28_0.md](RELEASE-NOTES-v0_2_28_0.md) for the design synthesis (the six novel pieces) and [docs/CLAUDE-TIER-PLAN.md](docs/CLAUDE-TIER-PLAN.md) for the rest of the roadmap.

## v0.2.27.0 — 2026-05-20

The **long-horizon work envelope**. Introduces `agent_session.py` — the persistent multi-step loop that carries a goal across many subtasks, grows its own queue as it learns, pauses cleanly when called, and resumes from disk exactly where it stopped. Also introduces `rollback.py` (Phase 3 of the v0.3.0 roadmap) — pre-staged undo plans for Tier-3 actions, with four generators shipping (file_write, atom_insert, snapshot_create, draft_archive) and the irreversibility doctrine enforced for everything else.

**1119 tests passing** (+79 new: 48 agent_session, 31 rollback). Zero regressions. The CLI sub-app for `sov session` is the next operator-pacing step; the underlying function-level API is the contract and is stable.

See [RELEASE-NOTES-v0_2_27_0.md](RELEASE-NOTES-v0_2_27_0.md) for the full picture, and [docs/CLAUDE-TIER-PLAN.md](docs/CLAUDE-TIER-PLAN.md) for the design plan covering v0.2.28.0 (retrieval reranker — highest leverage) through v0.2.31.0 (eval harness).

## v0.2.14 — 2026-05-10

The **legendary sprint**. Introduces **Aria-Sovereign-V1** (the AI inside the
system), rebuilds memory as a registry of 13 typed channels (financial,
goals, identity, specialist, lessons, ritual, trust, context, personalities,
intention, humor, emotions, intuition), adds a per-project financial ledger
with payments-grade idempotency, an appendix system for markdown documents
attached to atoms, and a first-class MOS Horizon Scan generator.

540 tests passing (+37 new). No data migration. Drop-in over v0.2.13.

See [CHANGELOG-v0.2.14.md](CHANGELOG-v0.2.14.md) for the full picture, and
[ARIA.md](ARIA.md) + [CHANNELS.md](CHANNELS.md) for the architecture docs.

## v0.2.13 — 2026-05-09

The **personality, FOSS, anti-zombie/anti-ghost, validators, edge-case
registry, and modulated memory** release. Adds five new modules
(personas, foss, edge_cases, validators, health, memory_namespaces),
fcntl on dream YAML, idle-cycle auto-pause, anti-syntax/anti-indent
quarantine, and four new top-level CLI commands (`sov status`, `sov
health`, `sov edge-cases`, `sov personas`) plus `sov dream tail` and
`sov dream gc`.

503 tests passing. No data migration required.

See [CHANGELOG-v0.2.13.md](CHANGELOG-v0.2.13.md) for the full picture.

## v0.2.12 — 2026-05-09

Adds the **infinite trillion-dollar software builder** (`sov dream`),
the **plain-English entry point** (`sov do "<sentence>"`), first-class
**pause/resume** at both continuation and dream level, and a **project
scanner** that detects file changes and emits atoms.

See [CHANGELOG-v0.2.12.md](./CHANGELOG-v0.2.12.md) for the full release
notes, [COMMANDS.md](./COMMANDS.md) for the updated command reference,
and [CORPUS_COMPLETION_PLAN.md](./CORPUS_COMPLETION_PLAN.md) for how to
finish the in-flight 1461-file walk.

### Headline additions

- `sov dream start` / `dream advance` / `dream pause` / `dream resume` /
  `dream stop` / `dream list` / `dream show`
- `scripts/sovereign-dream-loop.sh` — outer driver mirroring the existing
  continuation loop
- `sov do "<directive>"` — deterministic plain-English parser; turns
  missing args into interactive prompts; `-y` accepts defaults
- `sov projects scan` / `update` / `list` / `show` / `delete` — named
  directory tracking with sha256 fingerprinting, deterministic
  diff-to-atoms emission
- `sov pause` / `sov resume` — continuation-level primitives
- `sov continuations alias` — friendly names

### Tests

- v0.2.11: 383 → v0.2.12: **435** (+52, all green, ~15s)

### Compat

- Drop-in upgrade. New directories (`dream-sessions/`, `dreams/`,
  `projects/`) created on first use. `paused` continuation status is
  the only schema change; pre-v0.2.12 continuations untouched.

---

## v0.2.3 — 2026-04-28

First end-to-end task succeeded but trace revealed a per-task ~8s wasted
iteration: every model call went out with `think=true` (per `plan_only`
policy), and `llama3-groq-tool-use:8b` doesn't support thinking — Ollama
returned 400. Loop recovered gracefully (recorded `model-x`, retried)
but burned cycles and risked false-positive poison if combined with real
errors.

### Fixed

- **`ollama_client.py` capability detection** — queries `/api/show` per
  model, caches per-instance, sends `think=true` only when both (a) the
  operator's policy wants thinking AND (b) the model advertises the
  ``thinking`` capability. No code config required; the agent adapts to
  whatever models are wired up.
- **`loop.py` poison counter** — capability/HTTP-400 errors are
  classified as `model-config-x` and don't count against
  `consecutive_fails`. Real transient errors still do.

### Added

- **`tests/test_ollama_client.py`** (7 tests) — capability detection
  enables/disables thinking correctly per model, cache prevents repeated
  queries, failed `/api/show` falls back to broadest capabilities, plan
  vs dispatch call kinds respect policy.
- **`sovereign doctor`** now reports per-model thinking capability with
  PASS/WARN colors.

### Test count

- v0.2.2: 81 tests
- v0.2.3: 88 tests, all passing in ~8s

---

## v0.2.2 — 2026-04-28

Reflector hit a SQLite same-thread error on first end-to-end run. The
v0.2.1 code opened the atoms.db connection in one worker thread (via
`asyncio.to_thread`) and used it from the calling coroutine. SQLite's
default same-thread guard refused.

### Fixed

- **`reflector.py`**: connection lifecycle now stays inside one worker
  thread. The `reflect()` function opens, writes, and closes the
  atoms.db connection inside a single `asyncio.to_thread(_write_lesson)`
  block — no cross-thread connection use.
- **`loop.py:_run_reflector`**: simplified — no longer pre-opens a
  connection. Just calls `reflect()` directly. Removed the unused
  `open_atoms_db` import.

### Added

- **`tests/test_reflector.py`** (5 tests) — regression test for the
  threading bug, plus malformed-JSON handling, schema-violation
  resilience, confidence clamping, and code-fence stripping.

### Test count

- v0.2.1: 76 tests
- v0.2.2: 81 tests, all passing in ~8s

---

## v0.2.1 — 2026-04-28

Test harness was broken in v0.2: 14 of 32 tests failed because the conftest
fixture reloaded modules between tests. This created two stale-reference
bugs — production code itself was correct.

### Fixed

- **conftest.py rewrite (root cause fix)**. Replaced module reloading with
  in-place mutation of `SETTINGS.paths` via `object.__setattr__`. Avoids
  the class-identity drift that broke `pytest.raises(AuthorityViolation)`,
  the stale `SETTINGS` references that broke pathguard/events/seal tests,
  and the cumulative tool registry contamination across tests.
- **`reflector.py`** now uses `SETTINGS.reflector_model` instead of
  `SETTINGS.orchestrator_model`. The lightweight Reflector should run on
  the small fast model, not the orchestrator.

### Added

- **`config.py` env-var support** for all model selections —
  `AGENT_ORCHESTRATOR_MODEL`, `AGENT_CODER_MODEL`, `AGENT_EMBED_MODEL`,
  `AGENT_REFLECTOR_MODEL`, `AGENT_FAST_MODEL`. Set in your shell rc to
  override the defaults without editing source.
- **`reflector_model` field** in `Settings` (was missing in v0.2).
- **`sovereign doctor` command** — diagnostic check covering paths,
  permissions, models, Ollama reachability, model availability, bwrap,
  PROTOCOL-ZERO state, and VRAM. Run any time something feels off.
- **`tests/test_mode_controller.py`** (13 tests) — backlog read/write
  round-trip, priority ordering, status-aware task picker, atomic write,
  malformed YAML resilience.
- **`tests/test_retrieval.py`** (9 tests) — RRF fusion math including the
  classic compromise-candidate property, vector serialization roundtrip,
  pinning the standard k=60 constant.
- **`tests/test_vram.py`** (8 tests) — heavy-tool VRAM gating, file-lock
  serialization across threads, lock-timeout behavior.

### Test count

- v0.2:    32 tests defined, 14 failing → effectively no working coverage
- v0.2.1:  76 tests, all passing in ~7 seconds, three runs verified stable
