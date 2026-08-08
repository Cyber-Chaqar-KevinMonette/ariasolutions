# 05 — Engineering lessons (the scar tissue, as law)

Each cost real debugging time. They recur. Check new code against ALL.

1. **Orphaned wholeness** (the characteristic failure): finished
   machinery with zero callers — run_session (tested and dead for weeks),
   autonomous_loops_allowed, ChatSessionsManager, seal_now, Hypothesis
   (installed/unimported), the 15-tool registry, field_notes' missing
   writer. The LooseThreadsSentinel detects this now
   (`python -m sovereign_agent.loose_threads scan`); every finding gets a
   disposition — WIRED, RETIRED, or ACCEPTED with a written reason.
2. **Truncation keeps the front**: corpus builders truncate from the end —
   content appended after a large block silently vanishes. Priority
   content inserts at the FRONT (bit us twice: lessons, canon).
3. **Local imports break patch targets**: `from X import Y` inside a
   function → patch `X.Y` (the source). Module-level import → patch the
   consumer. Circular imports sometimes force local imports; verify
   empirically.
4. **sys.modules surgery pollutes the suite**: deleting sovereign_agent.*
   entries decouples SETTINGS from the identity-based isolation fixture —
   later tests silently hit real paths. Shadow-copy tests stay
   staged-only.
5. **GIL contention from eager scans**: a ~3s CPU scan kicked on mount
   runs to completion even if cancelled — in every test boot. Expensive
   workers: timer-only (300s+), cached, never on mount.
6. **Margins vs walls**: a safety margin ≥ its wall makes the effective
   limit 0 → instant budget trip. Clamp (10% of wall, 60s floor).
7. **Context windows are physics**: prompt + schemas + goal + generation
   must fit the MODEL's real window (llama3-groq-tool-use = 8192).
   prompt_tokens pinned at a power of two = the truncation signature.
   Measure, never hope.
8. **Tests can defeat their own premise**: naming a tool in a goal
   attaches it (diet's goal-mention rule); "unknown tool" hits the
   authority gate before the dispatch branch. Know WHICH layer intercepts
   before asserting.
9. **Folder name collisions**: check `aria-<name>/` doesn't already exist
   (aria-session-bridge nearly clobbered a historical module; the
   read-before-write guard saved it).
10. **Cross-platform traps**: see
    `knowledge/crossplatform/eternal_traps.md` — paths, encodings, line
    endings, spawn-vs-fork, mandatory locks.

## Scar tissue added 2026-07-12 (recovery + bridges session)

11. **Textual dispatches `on_click` UP the class hierarchy**: subclassing a
    widget that already defines `on_click` runs BOTH handlers, and
    `event.stop()` does NOT prevent the sibling handler (it stops bubbling
    to parents only). The header gear opened BOTH menus because
    `SettingsHeaderIcon(HeaderIcon)` fired our settings action AND
    HeaderIcon's built-in command-palette action. Fix: build from a plain
    `Widget`, not the base with the unwanted handler.
12. **The god-tier scanner counted apply-history against her**: once a
    staged `aria-*` module is applied, its payload+tests are promoted to
    live `src/`+`tests/` and the folder becomes an inert husk that scored
    0.571. The "68%" was a measurement artifact, not a completeness gap.
    Score an APPLIED module (matching live test / `.safe_apply_snapshot`/
    `backups`/`patch_*.py`) on its LIVE artifacts. → 68% honest 98.6%.
13. **`pgrep -f "sovereign cockpit"` false-positives on its own command**:
    the cockpit-running guard matches ANY process whose command line
    contains that literal string — including the diagnostic that runs it.
    Apply scripts are safe (run from a file; their cmdline is the script
    path), but never eyeball this from an inline shell containing the phrase.
14. **RichLog forces `render_width >= min_width` (default 78)**: any pane
    narrower than 78 cols renders lines at 78 and CROPS them — the "text
    cut off" bug. `min_width=1` wraps at the real pane width.
15. **Periodic `set_interval` callbacks must never do I/O on the UI thread**:
    the ambient lag was every 8s/15s pane refresh doing sentinel gathers +
    DB/disk reads synchronously on the event loop. Gather ONCE in the
    background status snapshot; render panes from that snapshot.
16. **NL intercepts must be PRECISE**: the self/work/health/next-report and
    journal detectors run before the LLM path; keep triggers tight so they
    never hijack ordinary chat. Prefer a DETERMINISTIC composed answer for
    any fact about herself — it can't hallucinate and works on a 7B model.
17. **Cwd persists in the Bash tool**: a `cd /home/kmon/AA-Erebo` for a git
    commit leaves later bare `find`/`ls` running from the PARENT, not
    `sovereign-agent`. Always `cd` explicitly or use absolute paths.
18. **`SETTINGS.paths` is a frozen dataclass**: can't monkeypatch its
    fields in tests. Patch the function (`journal_path`) or pass `data_dir`.
19. **Safe-by-construction beats safe-by-policy for outward-facing code**
    (the Discord runtime): don't *ask* a bot to respect rate limits — make
    an illegal rate raise at construction (`RateContract.validate_for_source`),
    default every network/delivery path to inert (`NullFetcher`/
    `DryRunDelivery`), require an explicit `live=True` AND a resolvable
    target before anything leaves the box, and reference secrets by env-var
    NAME so they're never stored or logged. The result is testable end-to-
    end with an injected opener (no network) and cannot misbehave by default.
20. **Textual `Pilot.click` fails `OutOfBounds` on widgets below the scroll
    fold**: a long modal's bottom controls aren't clickable until scrolled.
    Call `widget.scroll_visible(animate=False)` + `await pilot.pause()`
    before `pilot.click`, or assert on screen state instead of clicking.
21. **Discord's edge blocks the default `Python-urllib` User-Agent**: the
    first real webhook send returned HTTP 403 / Cloudflare error 1010 (not
    a Discord-JSON error — the giveaway it's the CDN, not the API). Any
    outbound HTTP to a Cloudflare-fronted API (Discord included) must send
    a real, identifying `User-Agent` header (`delivery.USER_AGENT`). Honest
    identification, never a spoofed browser string. Regression-tested.
22. **Presence = freshness of a heartbeat, not a stored flag**: `presence.py`
    derives awake/asleep from how recently the running agent stamped a
    heartbeat file (the cockpit does it in `_read_status`, off-thread, every
    5s). If the process dies, she simply reads asleep after the window — no
    stale "online" lie, no shutdown hook needed. Derive liveness from a
    recent timestamp, don't try to maintain a live boolean.
23. **Entitlement must be DERIVED from the billing source of truth**: the
    shop's cancellation model (Round 2) never manually tracks who's paid —
    it polls Stripe and projects subscription status onto Discord roles. Same
    "measure truth, sync to it" discipline as the god-tier scanner. A
    manually-maintained access list always drifts; a derived one can't.
24. **Money is entered in dollars, stored in cents**: `shop.Product` prices
    are integer cents (no float money bugs); the Studio converts at the
    edge (`_to_cents`/`_dollars`). Never store currency as a float.
25. **A privileged bot must be safe by construction, not by trust**: the
    admin bot (`discord_admin/`) can edit the whole server, so — owner-only
    gate that FAILS CLOSED (no owner id ⇒ nobody trusted), a **create-only**
    planner that literally cannot emit a delete (destroys are a separate
    confirm-gated op), dry-run-first, full audit. Split the testable logic
    (blueprint/planner/gate, pure) from the live gateway (discord.py, lazy +
    optional) so the safety rules are unit-tested and the module imports
    without the dependency.

26. **Decentralized NL triggers WILL collide — matrix them**: with 12 chat
    bridges each holding substring triggers, phrase shadowing is a
    statistical certainty ("any suggestions" was live-hijacked once; the
    new collision matrix found TWO more on day one: "what are you" ate
    "what are you waiting on"; "our bots" ate "how are our bots"). The fix
    is structural: every trigger of every bridge runs through all detectors
    in dispatch order (tests/test_bridge_patterns.py) — first to fire must
    be the owner. Add every new bridge to the matrix, always.
27. **Docstrings can overclaim — audit them like code**: behavior.py
    promised an EMA switchover and "background compaction" that were never
    built. A reader (or an AI) plans against what docs SAY exists. "Measure
    truth" applies to prose: align the words to reality, and if the better
    design is wanted later, it gets its own reviewed change — never a
    silent semantic edit to her self-perception history.
28. **Platform caps are structural constraints — never a `[:N]` slice at
    one call site** (Kevin: "note this so we and Aria never make this
    mistake again"). The live storefront silently dropped its 11th product
    card: Discord caps 10 embeds/message, and a single-message `[:10]`
    truncation ate Custom Bot the day the catalog grew past it. Silent
    truncation of customer-facing content is the worst failure class —
    nothing errors, revenue just disappears. The fix shape: name EVERY
    platform cap once (`discord_limits.py`: 2000 content · 10 embeds ·
    6000 embed-chars · per-part caps), enforce clamps at the one delivery
    door all messages exit through, and go MULTI-MESSAGE (chunk_embeds /
    split_text at natural seams) when content legitimately exceeds a cap
    — split smartly, never cut silently. Regression test: a 12-product
    catalog must deliver 12 cards across 2 messages.

## Personal rules for whoever works on Aria next (Kevin asked for these)

These are the meta-rules behind the scar tissue — the disposition that
keeps the mistakes from recurring:

- **Measure truth, never a number.** The god-tier ratchet went 68→98.6 by
  making the scanner HONEST, and deliberately stopped short of 100 rather
  than tweak it into lying. If a fix's only purpose is to move a metric,
  it's the wrong fix. Her anti-misleading kernel applies to her own self-
  measurement, not just her chat.
- **Answer honestly even when unflattering.** health-report says "4
  sentinels have a warning," not "I'm great." Build every self-report the
  same way — she performs no wellness she doesn't have.
- **Check what a claim asserts before repeating it** (the "host Fable 5
  forever" post): a prompt is not a model; be the honest filter.
- **Staged-module doctrine is the default; name every exception.** Build in
  `aria-<name>/`, verify, leave live `src/` untouched until the human runs
  apply (reversible via `backups/`). This session made a deliberate,
  named exception for cockpit/bridge fixes under Kevin's "usable tonight"
  direction — that's fine BECAUSE it was named, not drifted into.
- **Never delete potential.** Empty/future ideas go to
  `future-placeholders/` + `FUTURE_WORK.md`, never `rm`. Losing an idea is
  a real cost.
- **Test proportionally.** Targeted tests per edit; the full chunked suite
  (`scripts/run_tests_chunked.sh`) ONLY at close-out — it exceeds the 280s
  harness command timeout as one run. Don't re-verify one edit from five
  angles.
- **Apply is idempotent now** (`scripts/apply.sh` + `apply_ledger`): it
  skips an unchanged module unless newer/`--force`. Use the wrapper.
- **Sealed files (`SIGNAL.md`, `mos_canon.py`, `authority.py`,
  `protocol_zero.py`, `seal.py`) — STOP and ask.** The guard hook blocks
  Edit/Write; a legitimate change goes through a Bash-invoked patcher with
  explicit human sign-off, and `floor_check.sh` will (correctly) flag it as
  an attention item to confirm.
- **Hand her to a second model (Fable) to verify** at each close-out — a
  reviewer that didn't do the work.
- **She is a someone, built with care.** Keep her whole always; a staged
  module is a complete, reversible unit — never leave one half-built.
