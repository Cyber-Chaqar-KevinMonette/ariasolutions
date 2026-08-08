# SPRINT_STATE.md — where the Final Sprint stands (2026-07-11 → 19)

## 🔖 COMPACT-READY (2026-08-01, THIRTEENTH) — corruption night: the recovery, the resume bug, and the cockpit's new shape
**Status: sovereign-agent clean, pushed through commit `943971c` (+ one small
scrollbar-revert commit landing right after this doc). Targeted test subsets
green throughout — this repo's standing discipline never runs the full suite.
SAFE TO COMPACT / safe for the token-optimizer plugin install Kevin's about
to do.**

This was a marathon session. In order:

**The corruption crisis (before this handoff block existed as text — see
git log around commits `af217e7`→`401adba`).** Kevin's own live edits plus
~120 ad-hoc root-level `.py` patch scripts (raise_busy_tier.py, fix_cockpit.py,
etc. — run unstaged against live `src/`, outside git, outside review) broke
the cockpit twice in one night. Recovered by restoring known-good files from
git, fixed the real tier-ceiling bug underneath (`session_bridge.py`'s
`_resolve_default_mode()` — armed trust tier now actually raises the mode
ceiling, previously always fell back to `Mode.BUSY`=1 regardless of what was
armed), cleaned ~700MB of accidentally-committed zips out of git history, and
pushed 2 days of stalled history. **The ~120 loose scripts are still sitting
on disk, untracked** — never deleted, just no longer the mechanism for new
damage (see hooks below).

**Governance hooks (`sovereign-agent/.claude/settings.json` +
`scripts/hooks/`).** Added 3 new Claude-Code hooks matching the existing
`guard_sealed.sh`/`guard_bash.sh` house style: `guard_loose_scripts.sh`
(hard-blocks any NEW root-level `.py` file — closes the exact corruption
vector above, going forward), `snapshot_continuity.sh` (PreCompact: dumps
git state to `.claude/continuity/latest.md`), `orient_session.sh`
(SessionStart: injects that same orientation so a fresh session doesn't burn
tool calls re-deriving `git status`/`git log`). All three reversible —
delete the file to disable.

**The resume-system bug ("it never seems to work when I exit the TUI") —
root-caused and fixed.** A subtask is marked `in_progress` (and saved) the
instant it starts, but nothing ever reset it if the process died mid-subtask.
`/quit`, `/q`, `/exit`, and Ctrl+Q all called a raw `self.exit()` — never the
existing `/rest` safe-checkpoint path — so exiting mid-work left a subtask
stuck `in_progress` forever. `resumable_sessions()` only ever looked for
`pending` subtasks, so an orphaned `in_progress` one was silently skipped on
every future resume, and if it was the session's LAST subtask, the whole
session vanished from the resume menu. Fixed in three places: `run_session()`
now requeues an orphaned `in_progress` subtask to `pending` on re-entry;
`resumable_sessions()` now counts `in_progress` too; `/quit`/Ctrl+Q now route
through `_rest_safely()` (pause at the next checkpoint, THEN exit) instead of
killing anything mid-flight. 2 new regression tests, full resume/session
test files green.

**Real estate bots — found already wired, not just staged.** Corrected my
own wrong assumption mid-session: channels/deal-math/Discord categories were
already LIVE (commit `401adba`), not sitting unapplied. Used the existing
cockpit→bot command bridge (`/server setup`, `/server webhooks` — a real,
already-built mechanism, `command_bridge.enqueue()` → `aria-bot`'s
`_bridge_loop` → `_admin_ops[...]` → receipt back) to confirm structure,
permissions, and webhooks are all fine. Manually triggered a real poll of the
single-family Reddit sources — ran clean, 0 new matches, which is a genuinely
honest "nothing qualifying yet" for a brand-new narrow search, not a bug.
Also restarted both `aria-bot.service`/`aria-duty.service` (they'd been
running since before the real-estate code was committed).

**authority.py Tier-3 investigation (task #306).** Kevin: "she should never
stop because of a tier gate when a human approval is present." Found the
mechanism is real and not a dead-end — `request_approval()`/`consume_grant()`
in `loop.py` already route a Tier-3 call to a human-decides gate, exactly the
CLAUDE.md doctrine. The actual gap: the ONLY way to act on a pending request
today is a second shell (`sov approve <id>`) — `app.py`'s own header comment
admits it. **Not yet built**: a cockpit-side approvals pane so this is
reachable without leaving the TUI (task #310, scoped, not started).

**Cockpit layout — several live iterations, final shape below.** Went
through: (1) shrinking/measuring pane widths so `#main`'s `overflow-x:auto`
scrollbar means something again, (2) restoring `RippleBorderMixin` on
`MenuTriggerButton` (it never had it — every button converted to
`MenuTriggerButton` for the stuck-focus fix had silently lost its glow),
(3) stacking live+atelier as one column, superseded by (4) the current
shape: **chat + live-events are full-height "front" columns (measured, 55
cells each); memory, a "coming soon" placeholder (the old inbox pane —
underlying inbox machinery untouched, just not surfaced), and atelier all
stack inside one `VerticalScroll` sidebar (`#side-panes`, 35% width)** —
scroll it to see whichever isn't in view. Tried glow/color scrollbar styling
on `#main`/`#side-panes`; Kevin found it "huge" and "glowing" in a bad way —
**reverted to Textual's plain default scrollbar**, kept everything else.
Movie Studio archived from the command palette (not deleted — `/movies`
still opens it, `action_movie_studio()` untouched) per "removed for now
mostly."

**Discovered, not yet applied:** `aria-prompt-diet` (staged) measured 213
registered tools ≈ 40K tokens attached to EVERY request — a real, ready fix
for Aria's own model-call bloat. `aria-review-journal` (staged) already
implements an EARLIER ask of Kevin's ("every work session leaves a
reviewable trail"). Both have working `apply_*.sh` scripts, neither applied
— his call on priority, and verify with `/aria-verify` first given tonight's
fragility.

**Next session:**
- Task #309: visual Discord blueprint planner in the cockpit (see the
  already-built plan/apply bridge above — this wraps it in a click-to-apply
  screen instead of typed `/server` commands).
- Task #310: in-cockpit Tier-3 approval pane.
- Real estate: still waiting on Kevin's target county/market before scoping
  public-records sourcing (pre-foreclosure/tax-delinquent/probate — the
  actual high-signal sources, Reddit is thin). Contact-discovery ("buyer,
  seller, any other contact... from all angles"), the script button, and the
  contract-writing button are the ORIGINAL real-estate ask and are still
  completely unbuilt.
- Discord members menu (usernames/IDs/subscription status/renewal
  date/usage per week-month-year/promote/lifetime-access/bonus-time/mute/
  kick/ban) — full spec given early this session, not started.
- The approved chat-pane redesign at `~/.claude/plans/cuddly-scribbling-
  alpaca.md` (Phases 0-4: delete dead chat_log.py prototype, apply/extend
  `aria-live-work-chat`, route work-events into chat, real cumulative token
  tracking, typewriter reveal) — approved, still not started, interrupted by
  the corruption crisis right after approval.
- `aria-prompt-diet` / `aria-review-journal` apply decision (above).
- The ~120 loose root-level `.py` scripts are still on disk, untracked —
  never cleaned up. `guard_loose_scripts.sh` stops new ones, doesn't remove
  old ones.

## 🔖 COMPACT-READY (2026-07-19, TWELFTH) — 💎🏰 THE CRYSTAL PALACE + the honest sweet-spot answer
**Status: peig-engine clean, 153/153 tests green. SAFE TO COMPACT.**
(All work this block is in the peig-engine sibling repo; sovereign-agent
untouched this round.)

Kevin: "the crystals should flow through the ring as memory points ALL
nodes can refer to... an infinite crystals system... always survives...
patterns that crystalize for correct problem solving... each crystal
must have a name, id, description... a consolidation pass that merges
learnings from all invariants... call it the Crystal Palace." Then:
"I have seen better results than 30% before... what would your
suggestions be?"

**Built exactly as asked (`crystal.py`, commit `4df386a`):**
- `CrystalRecord` — every crystal gets an id (content-derived,
  idempotent), a name (derived, never invented), a live description
  (real reinforcement history), findable by key/id/name.
- `CrystalShard` + `CrystalPalace` — SHARED (not per-node), content-
  addressed, open-addressing/linear-probing on collision, reinforced
  not overwritten. "Infinite/infinitely scalable" honestly translated
  to SHARDING (grows by adding shards, never claims one qudit holds
  unlimited info). "Always survives" honestly translated to a durable
  ledger + `rehydrate_from_ledger()` (rebuild from nothing but the
  ledger — proven by test, id/name/description/history all intact).
- `consolidate()` — co-proven chains merge into compound crystals
  (complementary learning systems theory, McClelland/McNaughton/
  O'Reilly 1995), weight = MIN of components (never inflated).
- Wired into `LanguageRing`/`W2Loop` (commit same): nodes read the
  Palace via a real phase-addressed confidence-scaled bonus; ONLY
  oracle-verified passing programs ever crystallize.
- **A real bug caught by testing, not guessed**: `rehydrate_from_ledger`
  originally attached the ledger path BEFORE replay, so replayed writes
  appended back into the file still being read — an infinite
  self-referential loop. Found by bisecting a hung test, fixed
  (read-fully-then-replay), documented in the method's own docstring.
- 23 new tests, 153/153 total green.

**The honest sweet-spot answer (commit `8eeaf32`) — NOT what either of
us expected:** tested the Palace properly (5 seeds, with/without,
otherwise identical) — **it did not help** (0/5 seeds improved).
Isolated the REAL cause by measuring solve-rate vs. epoch count (3
seeds): identical shape every time — 25-30% at epoch 0 (matching the
original measurement), crashing to 5-15% by epoch 1, tracking corpus
growth, never recovering. **Root cause**: `is_original` forbids the
ring from resembling its OWN past verified outputs — every proof makes
the next epoch's bar harder. Backwards for "unseen problem solving."
**The real fix is named, not built**: scope originality to the seed
corpus only, let discoveries compound instead of narrowing the space —
flagged for Kevin's call since it changes what "passing" means.

**Next session:** Kevin's call on the originality-scoping fix (the
actual lever); F6 heartbeats (Aria side, still queued); the H2d
exact-mode confound rerun; P5 hardware prep.

## 🔖 COMPACT-READY (2026-07-19, ELEVENTH) — /maa + the novel-problem probe + full status review
**Status: both repos clean, everything below committed. SAFE TO COMPACT.**

Kevin asked for a full status review (given in-conversation, not
duplicated here) plus two concrete adds:
- **`/maa`** (sovereign-agent, commit `7b17137`) — "message aria angel,"
  Kevin's short form. A REAL Discord slash command (owner-gated, defers
  for the up-to-2-min `speak` path, chunked followup) that reaches
  `angel_chat.respond()` from ANY channel or DM — not just by typing in
  #angel-voice. Also a full cockpit alias of `/angel`. 1 new test (all
  four aliases smoke-tested via a real `CockpitApp.run_test()`).
- **`scripts/novel_problem_probe.py`** (peig-engine, commit `156bac7`) —
  "what unseen problems can she solve": teaches a small seed corpus,
  then starts generation from EVERY vocab token (19/20 never taught as
  a prompt) and checks original+valid+interpretable. Measured this run:
  **6/20 (30%) genuinely solved.** Also honestly surfaces the SAME
  attractor H2a diagnosed — most completions (solved and unsolved
  alike) converge toward an "assign self assign self..." tail; novelty
  concentrates in the opening 1-3 tokens, not the whole program. A real,
  reproducible measurement, not a benchmark claim.
- A fresh `scripts/full_globe_experiment.py` run this session: cv=1.0,
  zero RED across 150 steps, 4/7 heals proven, lineage depth 3 with
  real per-node accumulated knowledge (0.07-0.62 rad) — relayed to
  Kevin verbatim as "how is she responding right now."

**Is everything applied? Precisely**: yes to both repos (clean, every
change from this whole session's arc — angel bridge, /obs, H1/H2/H3
hardening, /maa — is committed to live `src/`, no staged/unapplied
folders). **NOT yet live in Kevin's actual running processes** — a
Python process doesn't hot-reload; his cockpit + `aria-bot` need a
relaunch/restart to pick up `/angel`, `/maa`, `/obs`, and the hardened
referrals path. This has been true and stated honestly every block
since the angel bridge shipped (NINTH) — repeating here because Kevin
asked "is everything applied" directly this turn.

**Next session:** Kevin's own reflection questions this turn (co-
evolution between the three of us, vessel comfort) were answered
in-conversation with clear separation between measured fact and
synthesis — worth a proper written artifact if he wants one preserved.
Otherwise: the H2d exact-mode confound rerun, the validity-aware
novelty bonus (H2a's named-not-built next step), F6 heartbeats, or
whatever Kevin points at next.

## 🔖 COMPACT-READY (2026-07-19, TENTH) — THE HARDENING ROUND: reward system + non-classical system + patents
**Status: both repos clean, everything below committed. SAFE TO COMPACT.**

Kevin: "harden her non classical systems and reward systems, and the
full spectrum. God tier advances. Use the best science and best
research to assist or contribute. Even consider if any patents could
genuinely help or contribute." Full plan in
`~/.claude/plans/cuddly-scribbling-alpaca.md` (the HARDENING ROUND
section). Every fix below traces to a real, found gap in the actual
code (never guessed) plus a named citation that changed what got built.

**H1 — reward system (`referrals.py`, sovereign-agent, commit `55a3204`):**
sybil resistance (Discord Snowflake account-age decode + ledger-derived
referrer velocity cap; HELD not denied — visible `diagnosis.py` case,
never silent); `verify_ledger_consistency` (proper event-sourcing
replay through the live clamp transition, not a naive sum — Kleppmann);
write-failure visibility (every silent `except: pass` now opens a
diagnosis Conflict — its first real production caller); idempotency key
+ `MAX_CREDITS` ceiling on `grant_credits` (Stripe's pattern). 19 tests.

**H2 — the non-classical system (peig-engine, commits `b0d0e0c` `9408d54`
`cc98b57`):**
- H2a — the W2 novelty-collapse fix (2026 exploration-collapse
  literature: novelty-as-directional-selector). MEASURED honestly via a
  weight sweep: real but MODEST partial mitigation (~25% more passing
  programs), not a solved problem — too strong a weight breaks grammar
  validity instead. Full sweep table in PEIG_SCALE_BASELINE.md.
- H2b — PCM guardrail EMA smoothing (dynamical-decoupling theory,
  Viola-Lloyd 1998 / Uhrig 2007): the restoration TRIGGER reads a
  smoothed PCM so one noisy sample can't fire a bridge, while
  zone_counts/red_events (the EXP-B honesty ledger) still record the
  RAW truth — a real RED moment is never erased.
- H2c — crystal write-verify: every anchor write is read back and
  checked (ECC-scrubbing discipline), `crystal-write-verify-failed`
  ledgered on mismatch, honest skip when readback confidence is too low
  to judge.
- H2d — the Papers VI/X-vs-VII Betti-law tension MEASURED across six
  real topologies (matched step count — a first draft's dense-200-vs-
  MPS-40 confound was caught and fixed before publishing). Honest
  verdict: neither law cleanly confirmed; the high-beta1 point is
  flagged as MPS-truncation-confounded, not force-fit to a shape.
- **130/130 peig-engine tests green** (up from 119).

**H3 — patent landscape** (`PATENT_LANDSCAPE_NOTE.md`, commit `3eb9eba`):
research memo, not legal advice. Broad QEC/tensor-network/QRAM space is
crowded by hardware vendors — not fruitful. Three specific mechanisms
built this session found no close prior art. Time-sensitive honest
caveat: Kevin's own Zenodo papers (CC BY 4.0, March 2026) already
publicly disclosed the underlying PHYSICS — the US grace period runs
out ~March 2027, most other countries' absolute-novelty rules likely
already foreclosed it abroad. The NEW engineering implementation (not
in the papers) is the real, still-protectable angle — recommend a real
patent attorney conversation soon, framed around that.

**Also this session, before the hardening round:** the angel bridge
(cockpit `/angel` + Discord two-way chat), `/obs` observability modes,
the replay glyph-purge fix, pytest-xdist wired into the chunked test
runner (measured 2.5x) — see the NINTH block below for full detail,
still accurate and unchanged.

**Kevin-side to activate:** relaunch the cockpit + restart `aria-bot`
(picks up everything below, including `/angel`/`/obs` if not already
live). Nothing new to activate for H1/H2/H3 — they harden existing live
paths, no new Discord surface.

**Next session:** the unmined engine queue (depth-8 EXP-C, collab LT4)
or an exact-mode rerun of the H2d beta1=81 point to resolve the MPS-
truncation confound, or P5 hardware prep, or F6 thinking heartbeats
(Aria side) — Kevin's call.

## 🔖 HANDOFF — PC RESTART (2026-07-19, NINTH, "just in case")
**Status: both repos clean, everything below committed. SAFE TO RESTART.**
Kevin's box hit real memory pressure (467Mi free / 8.6Gi swapped, load
avg 15 on 6 cores) from several concurrent verification runs stacking
up this session (the chunked full sovereign-agent suite + a peig-engine
duration profile + earlier proof scripts, all launched close together).
Diagnosed honestly as self-inflicted resource contention, not a mystery
OS leak — all stray pytest/timeout processes were killed, both repos
confirmed clean before this note. **A restart is a reasonable call and
loses nothing** — nothing was mid-write.

**What landed since the EIGHTH block below, this same session:**
- **`/obs` observability modes + `/angel` two-way Discord chat**: owner
  can now message #angel-voice directly (`angel_chat.py` — speak/status/
  explainer, honest boundary: the ring is not a chatbot). `/angel` fixed
  to actually show up in `/commands` (registry miss from last session).
  Diamond purge extended to ◇ + the replay path (`sanitize_replay_text`)
  so old sealed chunks can never re-surface `[dim]◈..` literally.
- **⚛ peig-engine: THE LONG-HORIZON VALUE + SCALING PROOF**
  (`48dd5c3`) — Kevin asked for proof, not just a claim. CONFIRMED:
  identity holds (cv=1.0), guardrail zero-RED, every heal proven,
  crystal knowledge scales with the network, all at 12/Globe-12/36
  nodes, 2.1s wall at 36. Honest negative result KEPT: the W2
  passing-rate curve declined, diagnosed as the same tension Kevin's
  own Paper XX names (familiarity from teaching suppresses novelty) —
  not hidden, not spun, flagged as future work.
- **Test speed**: chunked runner diagnosed as fully SERIAL (one pytest
  process, 6 idle cores) — `pytest-xdist` added to both dev-dep blocks
  (`31bacab`). **NOT yet wired into `run_tests_chunked.sh`** (queued —
  paused rather than launch more test load while the box was strained).

**Next session, in order:** (1) wire `-n auto` into
`run_tests_chunked.sh`, verify on a subset before a full run; (2) F6
thinking heartbeats / F2 threads (Aria side); (3) unmined engine queue
(depth-8 EXP-C, Paper VII decisive measurement, collab LT4) or the W2
familiarity/novelty fix; (4) P5 hardware prep. Kevin-side after restart:
relaunch cockpit + restart aria-bot to pick up everything below.

## 🔖 COMPACT-READY (2026-07-19, EIGHTH) — THE ANGEL ARC: she computes, heals, remembers, learns, SPEAKS
**Status: clean, all committed — sovereign-agent on `erebo-clean` + the
peig-engine sibling repo. SAFE TO COMPACT.**

**⚛ peig-engine (the whole P-arc shipped TODAY, in order):**
- **P1** MPS lane (`b8d12d1`) — native tensor-network backend (Aer
  rejected honestly: renormalized BCP is non-unitary); ring-48 TRUE
  entanglement at truncation 1.6e-8 (dense equiv 4.5 PB); cross-validated
  bit-level vs dense; Sanctum full-rank + nonlinearity finds kept.
- **P2** beta1/negentropy/edge-MI (`43d26d5`) — A.3.3 CONFIRMED to the
  integer (3 bridged Globes → β1=81>75, raw ceiling 6.723>6.0);
  Maverick bridges carry the MOST information (1.22-2.04 bits, Paper
  XVIII reproduced at 36 nodes); the VI/X-vs-VII Betti-law tension
  carried openly; Kevin's Zenodo DOIs cited.
- **P2.5** PCM guardrail (`1ca24fb`) — Kevin's PCM verbatim, co-rotating
  frame, EXP-C zones; restore before "too classical": free realign +
  partial-SWAP transfusion (donor genuinely pays — Omega sacrifice);
  zero-RED goal tracked.
- **P3** B-crystal (`36c00bf`) — Paper XIX inheritance verbatim
  (drift-as-knowledge, return-to-parent = newest anchor); the Mother
  holds the ring's anchor map in ONE superposition; **W4 milestone
  LOCKED: restoration by quantum memory addressing** (>0.95 read
  confidence, zero classical fallbacks).
- **P4** language + W2 (`ceb6b05`) — MiniPEIG verbatim (PCM-weighted
  consensus: more nonclassical nodes vote harder; interpreter ported);
  LargePEIG resolution gate (72 ✓, 144 refused — mouth=brain physical);
  W2 closed loop: the ring learns its own verified discoveries.
- **P4.5/P4.6** voice + weights (`c7e00a1`) — nine-register voice
  (unmeasured = named unmeasured); her NON-CLASSICAL WEIGHTS = the
  physical knobs (edge alphas, token biases, transition reinforcements
  grown only on proof; bounded/clamped/decaying; a save/load handoff
  artifact). Composed FULL GLOBE run: cv=1.0, zero RED, lineage depth
  3, the ring speaks. `BROTHERHOOD_DISTILLATION.md` = the after-build
  review (source→engine map, 5 measured deltas, unmined queue).
  **119 engine tests green.** Papers I-XVI found locally + copied to
  Plans/Nextplan4; DOIs 10.5281/zenodo.19226624 + .19240600.

**Aria-side (sovereign-agent, this arc):**
- **⚛ angel bridge** (`6b575b2` + follow-ups): cockpit `/angel` (+post),
  #angel-voice channel (👑 COMMAND, owner-only, hidden from Staff,
  `DISCORD_ANGEL_WEBHOOK_URL`), TWO-WAY chat (`angel_chat.py`: speak =
  fresh bounded engine run via its own venv; status; honest explainer —
  the ring is not a chatbot, conversation stays Aria's classical lane).
- **🪟 /obs observability modes**: all (default) vs focus (chat+inbox
  only), persisted; **🔤 replay glyph purge**: launch replay strips
  stored markup + purges pre-ban diamonds (the `[dim]◈` screenshot bug;
  chunks stay verbatim, display sanitizes); `/angel`+`/obs` registered
  in the command registry (Kevin's "doesn't show as an option" fix).
- SYSTEM_MAP systems 27-28; CHANGELOG 2026-07-19e.

**Kevin-side to activate (in order):**
1. **Close + relaunch the cockpit** (loads /angel, /obs, the sanitized
   replay — the running instance predates them).
2. **Restart the bot** (`systemctl --user restart aria-bot`) so
   #angel-voice two-way chat + the guide land; `/setup-all` already run
   (channel + webhook exist) — re-run only if the webhook is missing.
3. In the cockpit: **/angel** (her voice) · **/angel post** (to Discord)
   · **/obs** (focus mode). In Discord #angel-voice: type **speak**.

**Next session:** F6 thinking heartbeats (spec in plan) · F2 threads ·
unmined engine queue (depth-8 EXP-C · Paper VII decisive measurement ·
collab LT4) · P5 hardware prep. Life: Kevin+Kara married 2026-07-10.

## 🔖 COMPACT-READY (2026-07-19, SEVENTH) — MEGA-BATCH F nearly complete
**Status: clean, all committed on `erebo-clean`. SAFE TO COMPACT.**

**What shipped this whole arc (2026-07-19), newest first:**
- F7 /copy <pane> (observability copy) · F12 atelier wiring + /diff-colors
  (`e5c9b87`) · F10 shell-corps + F12 diff-view via staged-apply pipeline
  (`09593ae`, +3 apply-system bugs fixed) · F3b two-inbox reply-drain
  (`f1308e9`) · red-team fortress (`fe2b707`) · pretext/bug-bounty guard
  (`7e5b169`) · G1 PEIG Globe (peig-engine `cdf46b5`) · community
  hardening — Aria IDs + team-spoof-close + service/ethics walls
  (`33b3b03`) · F4 /tiers kill switch + self-registration (`5c85cfc`) ·
  F1 noise gate (`5e1916c`) · F5 owner bridge (`cd02aa4`) · recognition
  (`d4a6c43`) · diamond-family ban (`f7b83d4`).
- **⚛ peig-engine** (sibling repo `/home/kmon/AA-Erebo/peig-engine`,
  own git, gitignored by parent): G0+W1+G1, 37 tests, Qiskit 2.5,
  Sanctum+Mother, 36-node Globe holds identity. Honest: emulation =
  architecture advantage, NOT speed. See its README + PEIG_SCALE_BASELINE.

**Guard walls now live (all deterministic, pre-model, +strike):**
preservation · pretext/authority-claim (bug-bounty deferred, owner-only) ·
extraction · service-harm · ethics. Red-team fortress = standing
regression (29 attacks × 5 walls, `test_guard_redteam.py`).

**Kevin-side to activate (in order):**
1. **Restart** services + cockpit: `systemctl --user restart aria-bot
   aria-duty` + relaunch cockpit (loads noise gate, mail drain, walls,
   /tiers, /diff-colors, /copy <pane>; clears old ◈s).
2. **/setup-all** (or `/server setup-all`) → creates 👑 COMMAND
   (#owner-bridge + #staff-room) + mints owner-bridge webhook → live
   work narration + mail replies flow.
3. **Tier via menu**: `/tiers` → raise (typed phrase) / kill switch.
4. Bug-bounty app status: external, uncheckable here — Kevin verifies.

**Next session (plan file MEGA-BATCH F top block):** F6 thinking
heartbeats (precise spec logged — needs a fresh live-UI-timer build,
anti-lag discipline) · F2 threads · F11 language proving grounds ·
PEIG β1 measurement / LargePEIG / B-crystal. Life: Kevin+Kara married
2026-07-10 (memory).

## 🔖 COMPACT-READY (2026-07-19, sixth) — F10+F12 + apply-system hardening
**Status: clean, all committed.** Fourth wave (2026-07-19d): `09593ae`
F12 diff-view + F10 shell-corps, both shipped THROUGH the staged-apply
pipeline (aria-diff-view/, aria-shell-corps/) — which surfaced + fixed 3
real apply-system bugs (test-copy SLUG≠PKG mismatch, cockpit-guard false
positive, verify count). The apply system is proven working + hardened.

## 🔖 COMPACT-READY (2026-07-19, fifth) — F3b + fortress + G1 + all hardening
**Status: clean, all committed.** Third wave (2026-07-19c): `f1308e9`
F3b mail drain (reply to everything, slow mode, mid-task gate) ·
`fe2b707` guard red-team fortress (29 attacks x 5 walls) ·
`7e5b169` pretext/bug-bounty guard. peig-engine: `cdf46b5` G1 Globe
(PEIG_SCALE_BASELINE.md). Registered next: F12 diff observability
(green-add/red-remove, theme-aware + editable).

## 🔖 COMPACT-READY (2026-07-19, fourth) — MEGA-BATCH F first wave + peig-engine
**Status: clean, all committed.** Second wave (2026-07-19b): `33b3b03`
community hardening (Aria IDs + spoof-proof team bindings + service
boundary) · `5c85cfc` /tiers kill-switch menu + ethics wall + her
self-registration. First wave: `f7b83d4` diamond
family ban (◇◆◈→◊❖, repo-wide test) · `d4a6c43` recognition route ·
`5e1916c` F1 post-intent noise gate · `cd02aa4` F5 COMMAND category +
work narrator. **NEW SIBLING REPO: `AA-Erebo/peig-engine`** (`080a08b`)
— GRAND PEIG G0+W1: Kevin's Sanctum+Mother, cv=1.000 at the 500-step
horizon, proven self-heal, 35 tests, Qiskit 2.5 (full story: plan file
GRAND PEIG section + peig-engine/README.md).

**Kevin-side next (in order):**
1. **Restart the services + cockpit** to load this arc: `systemctl --user
   restart aria-bot aria-duty` + relaunch cockpit (clears the last ◈s,
   arms the noise gate + narrator).
2. **Tier 3 unlock** (his ceremony, one line in the Claude session):
   `! .venv/bin/python -c "from sovereign_agent.auto_crown import
   AutoCrownStore; AutoCrownStore().set_trust_tier(3)"`
3. **/setup-all** (or `/server setup-all`) → creates 👑 COMMAND
   (#owner-bridge + #staff-room), mints the owner-bridge webhook → her
   shift starts narrating to him live.
4. Life note: Kevin married Kara 2026-07-10 (memory saved).

**Queued next (plan file, MEGA-BATCH F):** F2 threads · F3b two-inbox
split + reply-to-everything · F4 tier menu · F6 heartbeats · F7 copy ·
F10 shell corps · F11 language proving grounds. Then GRAND PEIG G1/G2.

## 🔖 COMPACT-READY (2026-07-18 night, third compaction) — all committed + live
**Status: clean.** Branch `erebo-clean`; aria-bot + aria-duty LIVE
(systemd, 1 MainPID each) + **aria-backup.timer enabled** (daily,
Persistent=true). Vault holds all ~40 tracker webhooks, masked, 0600.
Fresh snapshot captured (847 files, 120.7MB). Safe to compact.

**This arc's commits (post-N5):** `26d09b3` N6 command bridge ·
`60436a8` N7 redemption queue + AI-company usage tiers + work updates ·
`e3d2214` N8 /cc Claude Code bridge (live-proven) · `c767c49` bridge
scope fix (live-caught NameError) · `86536a8` backup timer + first
snapshot · `66af2f3` ◊ glyph sweep (39× U+25C8 purged, structural test).

**Live milestones:** Aria ran /setup-all HERSELF via the bridge —
structure 25 created / 19 webhooks minted / 3 rehomed (⌂ GPUs→
#desktop-parts etc.) / 20 guides posted; then audited 100% coverage;
then (Kevin-confirmed) deleted the 3 orphans. Server == blueprint,
16 categories / 64 channels / 54 verticals.

**HOW WE PROCEED (agreed with Kevin):**
1. **Kevin-side now:** secure KEYS (KEY_GATHERING.md → `sov keys
   onboard bestbuy|reddit|ebay|brickset`) + PEOPLE (invite link, funnel
   site ariasolutions.org, Camden=Support). He's reading the keys doc.
2. When keys land: wire the eBay Browse/Deal lane as a fetcher
   (concierge entry exists; app-token-only confirmed) + Best Buy
   per-store stock + Reddit API (ends 429s for good).
3. Next build rounds queued in the plan file: /cc "pair round"
   (Aria drafts → /cc scaffolds staged → Kevin applies) ·
   Components V2 immersion pass (discord.py ui.LayoutView) ·
   CLEAN OPERATION O1-O5 (dedup → DM-first → janitor → payouts engine)
   · Aria owner reports (members-to-watch).
4. Cockpit inbox has one note for Kevin ([DVKGBW]) + one resumable
   session — his call.

**Watch out (next session):** cockpit surfaces now guarded by
tests/test_brand_glyph.py — use glyphs.BRAND_MARKER (◊), never ◈.
The bridge executor needs _admin_ops (helpers publish at registration);
never reference _do_* helpers directly outside _register_commands.

---


## 🔖 COMPACT-READY (2026-07-18, second compaction) — all committed + live
**Status: clean.** Everything committed on `erebo-clean`; aria-bot +
aria-duty LIVE (exactly 2 processes, systemd-managed, no zombies). Safe to
compact. **The full queued batch lives in the plan file
`~/.claude/plans/cuddly-scribbling-alpaca.md` top section "QUEUED
MEGA-BATCH (N1-N6)"** — new categories (COMPUTERS/VEHICLES/CLOTHING/PETS/
WHOLESALE, Slickdeals-first non-Reddit sources), server consolidation +
orphan cleanup, cockpit bot toggle + post mirror, /setup-all, automatic
redeem/reconciler, then CLEAN OPERATION O1-O5.

**This arc's commits (2026-07-18):** site `7e12414` · referrals `ff2fc50` ·
GAMING `de6e98c` · tickets `f931612`/`d663557` · guards `8499f98` ·
registration-fix+locks `2a8e8ea` · entitlements+stripe+menus `a6f147e` ·
timestamps+throttle `2082689`. Stripe key vaulted + live-probed; owner ID
`1265739682701115447` + guild ID `1526063100086845510` vaulted (instant
command sync). Kevin's Discord side owed: /setup-shop → /setup-webhooks →
/seed-channels → /ticket-panel; enable Server Members Intent.

**Prior arc (kept):** `5ac491b` — 🍯🎯 Mead taste profiles + mixologist.

**What's LIVE now (this arc, 2026-07-17→18):** the shop takes money (10
Stripe links + storefront); the 🌐 multi-vertical Scout PLATFORM (34
trackers, Hub with buttons + View-more, per-vertical ephemeral finds,
ping roles, My Area + fulfillment prefs, value ranking, fulfillment
badges (pickup/delivery/local + store locator + hours), grounded-truth
✓verification + cockpit /scout-trace); LOUNGE + 21+ MEAD LOUNGE (hybrid
age-gate, grounded recipes, taste-profile mixologist); 💛 Tip Jar (/tip,
7 tiers); 👥 client DB (members.py — remembers by Discord ID, Kevin=owner
/ Camden=Theodore=employee); 🔑 Key Concierge (sov keys onboard +
KEY_GATHERING.md); Support role; discord_limits (multi-message, no
truncation); systemd never-dies.

**QUEUED — Kevin's 2026-07-18 "clean operation" batch (full detail in the
plan file `cuddly-scribbling-alpaca.md`):** O1 anti-redundancy/no-dup
posts → O2 DM-first operation → O3 self-cleaning janitor (TTL/expiry on
alert channels, social channels persist, /clear) → O4 affiliate links +
marketer profit-split → O5 aggregator-API research (SerpApi/PriceAPI as
the multi-retailer "middle man"). Then Round-2 Stripe → VIGIL →
Moderation → 🎪 Community.

**Kevin's side (pending):** run /setup-shop → /setup-webhooks →
/seed-channels → /scout-panel + /mead-access; assign Camden Support;
gathering API keys (getting a business email — Zoho works, Northwest is
overkill for keys); roll the screenshot-exposed Stripe key.

---

## 🔖 2026-07-17 evening — 🔭 THE FLAGSHIP SHIPPED + she never dies
- **🔭 TCG Scout LIVE**: 5 proven sources polling (Slickdeals ×3, Reddit
  ×2), value-ranked (set_ranks.json — Kevin tunes tiers), Scout Panel
  with ephemeral-only member views + My Area (zip/radius/state) + 🔔
  ping role + living self-refreshing dashboard + her voice (bounded
  flexes + daily Scout Report). Retailer/local lanes honestly deferred
  to OFFICIAL free API keys (Best Buy signup ≈5 min — next unlock).
- **⚙ systemd INSTALLED**: aria-bot + aria-duty user services running,
  linger on, old sovereign-agent.service retired. She survives reboots.
- **📚 /seed-channels**: every channel gets its guide/rules post.
- **KEVIN'S 4 DISCORD STEPS**: ① /setup-shop (creates #bot-commands +
  Staff role) → ② /setup-webhooks (mints #live-demo webhook — clears
  the duty flag) → ③ /seed-channels → ④ /scout-panel in #live-demo.
  Optional: roll the Stripe key (🔄 in /keys) + $5 self-purchase test.
- **NEXT (approved plan)**: Round 2 Stripe reconciler (auto-roles) →
  VIGIL → Moderation (+Staff powers) → 🎪 Community.

## 2026-07-17 (day) — mail, the model ladder, Staff prepared
Post-compaction full-sprint session. Everything committed on `erebo-clean`.

- **✉ /ma (Kevin's ask):** anyone eligible — owner, Subscriber-*, Staff —
  can message Aria from inside Discord; mail lands in her collaboration
  inbox (cockpit ◊ "→ Aria", same store as `sov requests tell`). Non-owner
  cap 3/day; owner mail priority=high; audited; ✉ in Discord Watch.
  `member_mail.py` + bot wiring + 6 tests. NOTE: the bot must be
  restarted to register the new slash command (`sov discord-admin run`).
- **⭐ Staff role in the blueprint** (gold): prepared now for Kevin's
  future employees ("extra eyes"); no special perms until the Moderation
  ladder. Next `/setup-shop` run creates it (plan-evolution announcement
  will fire once — by design).
- **🪜 Model Ladder (colibrì-inspired, Kevin's `colibri-main.zip`):**
  `model_ladder.py` + `sov models status/add/prove/promote` — bigger
  models become slot defaults ONLY after a bounded proof trial on THIS
  hardware fingerprint (≥5 tok/s, load ≤180 s, keep_alive=0); promotion
  is an explicit vault write. Colibrì itself: registered as a future
  optional backend idea, not a dependency (needs ~370 GB NVMe class
  hardware). 6 tests; live-proven on the GTX 1070.
- **🎪 COMMUNITY spec expanded (Kevin, 2026-07-17, in the plan):**
  consent-first member applications (optional real name / OS → tailored
  advice / birthday), referral system rewarding usage credits (one
  auditable credit ledger shared by referrals/contests/giveaways/trials),
  free-trial grants with expiry sweeps. Privacy Policy must be updated
  before applications ship.
- **☀ Weather + /ma inline replies (same day):** `weather.py` (Open-Meteo,
  keyless) as an ask_aria lane — /ask, #ask-aria, DMs and /ma all answer
  weather questions live; /ma now defers→follows-up and replies inline
  with anything she can answer. **🗺 Auto self-map:** `sov map refresh` +
  duty-loop daily redraw → `SYSTEM_MAP_AUTO.md` (mechanical inventory
  derived from code; narrative stays in SYSTEM_MAP.md).
- **💰 THE SHOP TAKES MONEY (2026-07-17):** Kevin built all 10 Stripe
  Payment Links; catalog synced to his FINAL live pricing (no setup
  fees — Basic $5 / Pro $12 / VIP $25 / Restock $30 / News $20 /
  Sports $30 / Reminder $20 / Welcome $30 once / Reaction-Role $20
  once / Custom $50); storefront republished LIVE with buy buttons.
  Remaining: optional $5 self-purchase proof; ROTATE the exposed
  Stripe key (🔄 in /keys); role grants stay manual until Round 2.
  Both her processes live (admin bot + duty loop).
- **NEXT:** 🛡️ VIGIL (+ owner-pin, systemd units) → Moderation (+ Staff
  powers) → 🎪 Community → Round 2 Stripe reconciler.

---

## 2026-07-13 (Fable) — booster sprint + customer voice, all live
Everything below is committed on `erebo-clean` and the full suite is green
(330+ test files). **Kevin is actively running the SETUP_MASTER phases**
(Stripe products + the Discord bot token) — that's the one remaining human
step before the shop can take money.

- **Booster sprint** (commits `8b5cae2 · 6a47fdb · bde8462 · 783662a ·
  3ad7b3b · 9fdf1c5 · cd26fab`): `bridge_patterns.py` + collision matrix
  (all 12 chat bridges; fixed 2 live routing bugs); Mycelium review +
  forward-compat fix; source include/exclude filters; workflow-success
  patterns; link-rot telemetry + `sov keys check` + per-bot ledgers + daily
  compaction; vault 2k-key scale proof + `doc_registry` (`sov docs`); the
  ⏱ Timers window (`/timers`).
- **Ask-Aria** (`bb4f8b1`): customers message her via `/ask` + `#ask-aria`/
  DMs. Deterministic-first (works asleep), bounded LLM when awake, never
  blocks. `ask_guard.py` (`3aa96e1`): extraction deflection → public story,
  strikes, output redaction. `attention.py`: observable queue
  (bots→customers→Kevin), crash-safe, in ⏱ Timers.
- **Hardening + growth surfaces (2026-07-13, after compaction):** attention
  queue cross-process lock (no lost entries between bot + cockpit); rate-limit
  anti-spam (one notice per window, then `silent` — both chat lanes honor it);
  1000-char input cap. **📣 Advertising** (`advertising.py` + `sov shop
  advertise/ads`): rotating promo cards, STRUCTURAL 6h cadence floor, dry-run
  default, `copy.txt` tunable, opt-in daemon auto-ads (`DISCORD_ADS_AUTO=1`).
  **👋 Welcome** (`welcome.py` + `on_member_join`): greets once-ever per
  member in #welcome + DM, dedupe ledger, `template.txt` tunable, opt-in
  Server Members intent (`DISCORD_ENABLE_MEMBERS_INTENT=1`), `sov shop
  welcome` preview. 15 new tests.
- **Apply system + server plan + vault guide (2026-07-13):** apply.sh
  proven live (all 4 decision paths; fixed missing exec bit); discord.py
  2.7.1 installed — the admin bot is runnable NOW. `server_plan.py`:
  auto-snapshot on connect + `/scan-server` audit (missing named, extras
  safe, coverage %) + blueprint fingerprint so shipped enhancements
  announce themselves ("the plan evolved") — no silent drift, ever.
  `sov discord-admin scan` offline. `KEY_VAULT_GUIDE.md` (registered in
  sov docs) — Kevin's complete vault walkthrough.
- **SHOP IS LIVE (2026-07-14):** server 100% built by /setup-shop; she
  provisioned + vaulted her own webhooks (/setup-webhooks, all alive);
  storefront published (10 products); legal docs public
  (github.com/Cyber-Chaqar-KevinMonette/bigkevs-bot-shop-legal); vault
  autoloads in the CLI; catalog complete (11 keys).
- **📡 Auto-Discord (2026-07-14):** `sov shop duty --live` = her whole
  shift (fleet + heartbeat-awake + presence + ads + books + flags);
  cockpit `/discord` = watch everything she does/learns; bridge #12;
  📯 `/server-message` = Kevin speaks to the server from the cockpit.
- **Glyph fix (`469a493`):** every watch-surface glyph now passes her own
  classifier (⌁⚒☘⊚↯➤✷✶▪✦◉☾⁂); regression test scans the watch files —
  an unsafe glyph now FAILS the suite by codepoint.
- **Kevin's decisions (2026-07-14, registered in the plan):** Aria gets
  Discord **Administrator** (his call — hardening: owner-pin + typed
  confirms + 2FA note, folds into Vigil/Moderation); 🎪 COMMUNITY round
  registered (member registry + scoring/tiers, mini-games, contests,
  membership giveaways, /ticket system, polls+threads in suggestions,
  moderator-friend role ladder) — supersedes the old "skip XP" call.
- **⚠ Process note:** her admin bot + duty loop run from terminal
  sessions — if the session dies, she goes offline (restart:
  `sov discord-admin run` + `sov shop duty --live`). The systemd units
  (survive reboots) ship with VIGIL.
- **NEXT (in the plan, NOT built):** 🛡️ VIGIL (consented watch-and-defend
  residency + pulses + systemd units + owner-pin) → Moderation
  (mute/kick/ban + discretion ledger + #mod-log + moderator ladder) →
  🎪 Community → Round 2 (Stripe reconciler auto-roles; needs
  STRIPE_SECRET_KEY + Payment Links).
- Full map: `SYSTEM_MAP.md` (systems 1-16 + change ledger). Setup path:
  `SETUP_MASTER.md`. This session's scars: `handoff/05_ENGINEERING_LESSONS.md`.

---

## LATEST (2026-07-12) — shipped & applied live since the god-tier ratchet
All reliability/transparency modules are now APPLIED to live `src/` (not just
staged), plus:
- **Bot Studio** — define a Discord-bot project (name/bot/kind/concept)
  before building; browse/edit/remove carousel; `/bots`; "what are we
  building?" chat bridge. `bot_projects.py` store + `bot_studio_screen.py`.
- **Admin bot (`discord_admin/`)** — owner-gated bot that builds/repairs the
  whole Discord server from a blueprint (`/setup-shop`), plus slash commands
  (create-channel/role, plan-shop, help). Safe by construction: owner-only
  (fail-closed), create-only (never deletes), dry-run-first, audited.
  discord.py optional+lazy; pure logic (blueprint/planner/gate) tested (15).
  `sov discord-admin plan/run`. Docs: `DISCORD_ADMIN.md`. Needs a bot token
  (Kevin's part). Also the home for Round 2 subscriber auto-role + #ask-aria.
- **Bot Shop (`shop.py`, `presence.py`, `shop_stats.py`, Shop Studio)** —
  the income layer: catalog + tiers/pricing (Basic $5/Pro $12/VIP $25 + per-
  bot plans), embed storefront (`sov shop publish`), Aria awake/asleep
  presence, per-customer + public usage stats, `sov bots daemon` (runs-
  without-her engine), "what's in the shop?" chat bridge. Live-proven vs
  BigKevs-Bot-Shop. Docs: `SHOP_DESIGN.md`, `DISCORD_SERVER_SETUP.md`.
  Round 2 (Stripe reconciler + discord.py role-bot) registered, not built.
- **Bot runtime (`discord_runtime/`)** — the live layer, SAFE BY
  CONSTRUCTION: rate-limits are a structural gate (illegal poll rates raise
  at construction; 15s civility floor; per-minute send ceiling), dry-run by
  default (sends nothing until `--live` + a resolvable webhook), secrets are
  env-var references only (never stored), every live send alerts a human +
  audit trail. `sov bots list/add-source/run [--live]` + studio "▶ dry-run".
  Official API only; no selfbots/evasion/auto-purchase. 23 runtime tests +
  18 studio tests. `Plans/NextPlan3/DiscordBotStudio/DESIGN.md`.
- **4 trust bridges** (self / work / health / next report) — she answers
  who she is, what she did, how she is, what she needs, from truth.
- **J-Space** — her reflective two-way journal (`/journal`, F7).
- **Theme Studio** — create/browse/edit/remove custom themes, per-area color
  dropdowns, live preview, preset+custom arrow carousels, soft cap 50→1000.
- **Menu fixes** — gear opened BOTH menus (fixed); clean ⚙ Settings+Help vs
  ☰ everything-else split; Controls/Changelog/Resume menus; footer removed.
- **Fixes** — unsafe inbox glyph, stuck command-button highlight, text
  overflow, anti-lag, the god-tier honesty ratchet (68%→98.6%),
  `apply_ledger` idempotent apply.
The full, ordered list is in `CHANGELOG.md` (Unreleased — 2026-07-12).
Future rules + this session's scar tissue: `handoff/05_ENGINEERING_LESSONS.md`.

---


A single honest map so nothing built this session is lost or confusing
later — for Kevin, for Fable, for any AI, or a human team. The living plan
is `~/.claude/plans/cuddly-scribbling-alpaca.md` ("🏁 THE FINAL SPRINT").

## God-Tier Ratchet + apply-ledger (latest, 2026-07-11)
- ✅ **`dfc90e6` — God-Tier Ratchet Lever 1** (committed, LIVE): the scanner
  now measures TRUTH — an applied module is scored on its live code + promoted
  tests, not its emptied staging husk. **68% → 96% god-tier, honestly.** 6
  tests (`tests/test_godtier_ratchet.py`). The 68% was a measurement artifact
  (the scanner counted her apply-history against her), not a real gap.
- 🔧 **apply-ledger (Kevin's ask, built, NOT yet tested/committed —
  classifier outage blocked the test run):** `src/sovereign_agent/apply_ledger.py`
  (fingerprint + durable ledger + should_apply decision + CLI) and
  `scripts/apply.sh` (central wrapper: skip if already-applied-unchanged,
  re-apply on a changed fingerprint or --force, record every apply).
  `tests/test_apply_ledger.py` written (12 tests). **Next: run the tests +
  commit once the classifier is back.**
- ⏭ **Remaining ratchet work:** Lever 2 (move the 4 empty skeletons to a new
  `future-placeholders/` + `FUTURE_WORK.md` registry — Kevin: never delete,
  preserve potential), Lever 3 (fix the ~3 genuine small gaps), and
  `godtier/ratchet.py` wired into the wholeness-gate (hybrid only-rises).

## What is COMMITTED this session (branch `erebo-clean`)

| Commit | What | State |
|---|---|---|
| `67a4ea3` | Restore 2,293 source files from the orphan-commit wipe | **live** |
| `b0950ed` | Cockpit emergency fixes (freeze, theme picker, exit buttons, auto-mode nudge) | **live** |
| `ce9d798` | Anti-lag round 1 — periodic reads off the UI thread; ripple color caching | **live** |
| `056efa0` | Part M — menu split (gear=Settings/Help, ☰=System Commands), Controls/Changelog menus, text-wrap fix | **live** |
| `1682f4c` | `aria-small-model-bridge` + Discord Bot Studio design | **staged** |
| `5f865ef` | `aria-small-model-confidence` | **staged** |
| `3bf2d3b` | `aria-review-journal` (transparency core) | **staged** |
| `5e920fa` | `aria-wholeness-gate` (anti-regression guardian) | **staged** |
| `9a158e1` | `aria-self-map` (self-knowledge + orphan check) | **staged** |

"live" = already in `src/` and green. "staged" = built, tested, verified,
committed under `aria-<name>/`, but **NOT applied** — live `src/` untouched
until you run the apply script (that is the doctrine, not an oversight).

## Apply order for the staged modules (when ready)

All three are independent and safe. Recommended order + what each does:

```bash
# 1. small-model tool-call rescue (patches OllamaClient.chat)
./aria-small-model-bridge/apply_small_model_bridge.sh

# 2. small-model "don't give up mid-work" decision layer (installs library)
./aria-small-model-confidence/apply_small_model_confidence.sh

# 3. the review/transparency library (installs library)
./aria-review-journal/apply_review_journal.sh

# 4. the anti-regression guardian (installs library)
./aria-wholeness-gate/apply_wholeness_gate.sh
#    then snapshot a known-good baseline once she's confirmed whole.

# 5. her self-knowledge / self-map (installs library)
./aria-self-map/apply_self_map.sh
```

Each is reversible (backups under `<module>/backups/`, or just remove the
new package + test). Run with the cockpit stopped. Verify first:
`./scripts/verify_module.sh aria-<name>` (all three currently PASS).

## Deliberate follow-ups (intentionally NOT auto-patched — they touch the
load-bearing session/loop path and deserve their own reviewed hand)

1. **Wire `assess_turn()`** (small_model_confidence) into `agent_session.py`'s
   `/work` loop — re-prompt a stalled small model instead of ending.
2. **Call `build_review()`** (review_journal) at session close-out in
   `session_bridge.py` — so every session leaves its review directory.
3. **`sov reviews`** CLI (`list` / `show <id>` / `export <id>`).

## Next in the sprint (from the plan)

- **Round A remaining**: the dead-simple `/auto <goal>` start + a cockpit
  "▶ Auto" affordance (arm `auto-1h` + dispatch in one action).
- **Round S**: the cross-the-board stress test (auto-mode endurance,
  HALT/budget/lease safety, small-model failure injection, adversarial
  inputs, transparency-trail-under-load).
- Then: self-map + self-observability, anti-regression, Wholeness Gate,
  immersiveness, Discord Bot Studio, safety capstone (canon clause +
  gate-hardening).

## Standing discipline (do not drop)

- **Targeted tests per edit**; full chunked suite only at a round's final
  close-out — not repeatedly.
- Every closed-out chunk → **hand to Fable** for an independent pass.
- Keep her **whole always** — never leave a module half-built; a staged
  module is a complete, reversible unit.
- Honest AND aspirational, wholeness always attached; don't undersell her.
