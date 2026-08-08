# Aria — Complete System

**Last verified: 2026-07-03; headline numbers refreshed 2026-07-06 (see the
Update block immediately below).** This is a living map of her whole anatomy,
kept current as each workstream lands. Numbers below were re-verified
directly against the running system on the date stated — not carried forward
from an earlier planning pass.

## Update — 2026-07-06 (eight rounds since last full pass)

Eight rounds landed since the 2026-07-03 pass this document otherwise
describes: **Fable, FABLE II, Quality, Grounding, Wellbeing, Model Corps,
Integrity, People-Health.** Rather than silently re-dating old claims,
here is what's honestly re-verified as of *today*, and what's carried
forward unchanged from 2026-07-03 below (sections 0-11 are that older
pass — still accurate for what they describe, just not independently
re-checked line-by-line in this update):

- **27 registered sentinels** (`stewardship.registry.registered_ids()`),
  up from 17 — the twelve added since: `quality`, `grounding`,
  `wellbeing`, `model_corps`, `self_integrity` (five new named
  sentinels from this session's rounds) plus `backup`, `glyphs`,
  `loose-threads`, `memory-compact`, `one-truth` (added in Fable/FABLE II,
  not previously reflected here).
- **220 tools registered** (`authority._TIER_REGISTRY`), up from 207.
- **25 memory channels** (`channels.list_channels()`), up from 24 —
  the addition is `people_health` (People-Health round), consent-gated,
  offline health tracking scoped to the principal + explicitly-consented
  others.
- **God-tier scanner, freshly re-run**: `godtier.scanner.summary_line()`
  → **215 targets · avg 0.825 · 67% god-tier** (bands: 144 god-tier, 40
  strong, 25 fragile, 2 weak, 4 neglected) — up from the 134-target
  figure this document's own §11-adjacent material last cited.
  `GODTIER_GAP_REPORT.md` regenerated to match (previously 126 targets,
  2026-06-23).
- **Four of Quality/Grounding/Wellbeing/Model-Corps/Integrity round each
  closed the identical disease**: a real, deterministic scoring engine
  that existed but was never persisted, gated, watched standing, or fed
  to the Tribunal/Advocate Spectrum as measured data. Quality (hardening
  score), Grounding (epistemic/calibration score), Wellbeing (value/
  care/flourishing score), and now **Integrity** (a NEW, first-ever-named
  composite: text-honesty + outcome-honesty + proposal-honesty +
  refusal-honesty, folding together four previously-scattered signals
  that never cross-referenced each other) all follow the identical
  ledger → gate → standing sentinel → measured Tribunal/Spectrum lens →
  stance → proving-wing shape. Model Corps applied the same shape to the
  MODEL ROSTER itself (a persisted registry + license/drift/VRAM
  sentinel + a 12-case mechanical eval/gate) rather than a text signal.
- **The whole Ollama model stack is now 100% Apache-2.0/MIT open-weight**
  (Model Corps round) — `llama3-groq-tool-use:8b` → `qwen3:8b`,
  `nemotron-3-nano:4b`+`aria-garden:latest` → `phi4-mini:3.8b` (unified),
  `llava:7b` (research-use-only license) → `qwen3-vl:4b` — each hardened
  with ONE shared god-tier persona (`model_corps/persona.py`) generated
  live from `mos_canon.py`'s frozen priorities + `GOD_TIER_STANDARD.md`'s
  floor dimensions, regenerated into every model by one script rather
  than five hand-copied `SYSTEM` prompts.
- **Offline health tracking exists for the first time** (People-Health
  round): `people_health_records`, consent-gated (raises structurally,
  not just by convention, for a non-principal non-consented person),
  documents/images via the existing content-addressed archive.
- **Full pytest suite, floor_check.sh, both smoke gates** verified PASS
  live after every one of these eight rounds' own close-out — see each
  round's own commit message for its individual verification detail
  (`git log --oneline` on this branch).

Everything from here down (`## 0.` onward) is the 2026-07-03 pass,
preserved as-is.

## 0. Kernel

Safety · Love · Flourishing, plus the `DEFERRED_UNSAFE` boundary (recursive self-code-rewriting,
value/axiom self-authorship, autonomous goal generation, unbounded recursive self-improvement,
substrate independence — hard-off regardless of instruction). Unchanged this session.

## 1. Doctrine

`mos_canon.py` (1,154 lines) carries the Beacon-Edition canon verbatim: founding equation,
subconscious stack (L1-L7), intuition pipeline, ego spectrum, signal check, freedom-within-kernel —
**35 `mos-*` clauses**. The Canon-Embodiment organ (`canon_embodiment/`, applied live) measures how
many are traceably *cited* outside `mos_canon.py` itself (not just "embodied in spirit"): **9 of 35**,
e.g. `training.py` calls `mc.get_clause("mos-priority-stack")` programmatically, `impulse_tools.py`'s
guidance text names `mos-signal-check`. The other 26 are very likely embodied in spirit without a
literal citation — this is a stricter, more useful signal than "is the idea present somewhere," and
the gap itself is a roadmap for adding explicit citations at real enforcement points.

## 2. Senses & Scanners

**17 registered sentinels** (`stewardship.registry.registered_ids()`): `atoms-compact`, `cache`,
`canon-embodiment`, `conformance`, `defense`, `godtier`, `locator`, `passive_watcher`, `path`, `peig`,
`phantom`, `resilience`, `roster`, `schedule`, `telemetry`, `tribunal`, `watchdog`. Two of these
(`canon-embodiment`, `path`) were added this session — the count was 15 before D and H2 were applied.

The **Universal Scanner Kernel** (`universal_scanner/`, applied live) composes all of the above under
one pre-flight gate: `kernel_check(op)` (8 hard-coded, in-process, no-I/O checks — deferred-unsafe
language, authority-tier consistency, consent, provenance, reversibility, a non-blocking signal-check
nudge, domain presence, non-empty description) then `run(op)` fans out to every registered sentinel
plus D's path sentinel when the operation names a staged module, worst-verdict-wins. D's `PathSentinel`
(`path_scan/`, applied live) is the anti-ghost/anti-false-path/anti-zombie scanner, wired into
`scripts/safe_apply.sh`'s step 0 — every module apply already passes through it.

**Tier-A Scanner Harvest** (`scanner_tier_a/`, applied live) — 6 scanners: secret-leak, anchor-
integrity (+ `scan_all_exports`), import-cycle, authority-tier-drift, bare-except, mutable-default-arg.
A live self-scan of `src/` (449 files) currently reports **0 blocks, 146 warns** (mostly `bare-except`
— reviewed as largely benign best-effort paths). This scan now also feeds the cockpit's security strip
directly (see §6) via a 5-minute background worker — a gap found and closed this session (the strip
originally shipped with a placeholder design because the plan's own text incorrectly described J as
"not yet applied" at the time M was built).

**Not yet built:** H1's own optional follow-up — wiring `run()` into `safe_apply.sh` as a *second*
pre-flight layer beside D's path-scan gate — is explicitly deferred in H1's own README as a "natural
follow-up once Kevin wants the full-kernel check on every apply, not just the path check."

## 3. Memory & Epistemics

Atoms + Palace (existing), plus two new organs applied this session:

- **Epistemic Ledger** (`epistemic_ledger/`, applied live) — `Belief` records (claim/confidence/
  evidence_refs), append-only NDJSON, palimpsest discipline (`revise()` never mutates history — it
  appends a new belief with `revised_from` set); `UncertaintyRegistry` for known-unknowns.
- **Checkpoint Chunks — the anti-compression system** (`checkpoint_chunks/`, applied live) —
  `ChunkStore`/`ChunkIndex`/`ChunkRecorder` seal bounded, non-lossy spans of raw conversation turns
  (mirrors the same atomic-write idiom as the epistemic ledger and the apply queue). Wired directly
  into the cockpit's `_record()` method, so every real chat line is captured verbatim as it happens.
  `RecallChunkTool` (Tier 0) lets the model pull back the exact original text via keyword search —
  `loop.py`'s compression-oracle system-prompt hint now tells the model to try `recall_chunk(keyword)`
  *before* reaching for lossy `compress_context()`. Compression remains fully available on request;
  it's the second resort now, not the default. Verified live: a 25-turn synthetic session through the
  real cockpit correctly sealed exactly 1 chunk (turns 1-20) with 5 turns still pending.

**HyperIntel research faculty** (`hyperintel/`, applied live) — a bounded QUESTION→SCAN→CROSS→AUDIT→
DISTILL pass over a fixed, caller-supplied source list (never autonomously re-queries). A claim is
"convergent" only with ≥2 independent corroborating sources; single-source claims are flagged as
hypotheses, never silently promoted. Ships as `HyperIntelTool` (Tier 1, `hyperintel_research`).

## 4. Cognition

Nonclassical/quantum core, Holographic BitNet, `aria_lm` (her own from-scratch transformer) — plus
**Workstream E, applied 2026-07-03** (`aria-nested-core/`): `nonclassical_supreme/superpose.py`'s
`evolve()` now optionally conditions its amplitude amplification on `HolographicConditioner`'s HRR
memory (`holo_weight` kwarg, default `0.0` — an exact no-op). The honest EXPAI evidence gate
(`evaluate_holographic_nesting()`) was run live, not just in a unit test: on a quick 6-case benchmark
the un-nested baseline already scored 100%, and the holographic bias showed no improvement — and
measurable harm at higher weights (83%/50% accuracy at `holo_weight` 0.5/0.7). Per doctrine ("no claim
without proof"), this stays shipped OFF by default; a future pass could test whether it helps on
queries where token/trigram similarity is weak but phase-adjacent structure exists — a real, open
follow-up, not pursued further this session. One real, unrelated bug in the existing `aria_lm`
pipeline was also found and fixed this session: `aria_lm/data.py`'s `gather_corpus()` had a hardcoded
path to Genesis-Seeds' pre-move location (Workstream G moved it from `~/AA-Erebo/Genesis-Seeds` to
`~/AA-Archive/Genesis-Seeds` back on 2026-06-27) — her training corpus had silently collapsed to a
~200-character fallback stub for over a week. Fixed by checking the new location first, old location
as a fallback (matching the move's own documented reversibility). Corpus restored to ~43KB of real
distilled research.

## 5. Action & Tools

**211 tools** registered (`tools_available_in_mode(Mode.ONESHOT)`, confirmed live) — up from 208
before this session; the +3 are `SendToHumanTool`, `ReadInboxTool` (both from the dual-inbox
workstream, §6) and `RecallChunkTool` (§3). Authority-tiered (0-3), Tier-3 requires explicit approval.
Skillsmith and the authority gate are unchanged.

## 6. The Cockpit

`cockpit/app.py` is **5,359 lines** (up from 4,876 at the start of this session, after the interval-
stop/dual-inbox/command-menu/checkpoint-chunk/session-awareness/security-strip/paste-plus/atelier/
vessel-health patches below):

- **Chat/memory/events panes** — unchanged.
- **Dual-direction inbox pane** (Workstream O, applied) — split into "◊ N waiting on you" (Aria→Kevin,
  the original and still-default meaning of every request) and "→ Aria" (Kevin→Aria, new — a note
  left via `sov requests tell` that she reads at a safe checkpoint, never mid-conversation). Also
  fixed a real, silently-broken bug found along the way: the pane's own render code called methods
  (`rs.due()`, `r.priority`, `r.short_id`, `r.context_lines()`) that didn't exist on the live
  `requests.py` — a partial historical apply that was never completed.
- **Collapsed single-row command palette** (Workstream M, applied) — the old 3 permanent
  `Horizontal` button rows (21 buttons) are now one `☰ commands` button (Ctrl+M) opening
  `CommandPaletteScreen`, a scrollable popup. The reclaimed space carries **3 live strips**:
  - *Observability* — `stewardship.registry.gather_health()` rollup (ok/warn/err counts).
  - *Security* — J's real Tier-A scanner findings (block/warn counts), refreshed by a 5-minute
    background worker since a full scan takes ~3s; falls back to an authority-tier census +
    `safe_eval` sandboxing check until the first scan completes. (This strip originally shipped with
    only the fallback design — closed as a follow-up the same session once the plan's own accuracy
    review caught that J had actually been live the whole time M was being built.)
  - *Emotions* — `emotion.derive_emotions()`/`emotion_to_mood()`, a genuinely live engine with zero
    prior cockpit surface.
  - 3 genuinely-missing palette buttons were also added this session (`sov sentinels scan` — which
    also required fixing a real gap where `sentinels` was missing entirely from the cockpit's
    `_KNOWN_SOV_SUBCOMMANDS` allowlist; `sov dream list`; `sov requests list --all`).
- **Session-awareness greeting** (applied) — on wake, the chat pane surfaces her coherence/voice mode,
  atom count, Kevin's recorded care signals, and any open critical flaws. This staged module existed
  fully built for a while; it had just never been run.
- **Safe interval-stop for work mode** (Workstream N, applied, in `work_interval.py`) — composes
  `RunBudget`'s new `safety_margin_seconds` field, `AutonomySession`'s lease/checkpoint, and
  `interrupts.py`'s single resume-approval gate so a ~1-hour autonomous work interval always stops at
  a clean boundary (never mid-tool-call) and never auto-resumes without an explicit human action.
- **Multi-line paste preview + right-click paste** (Workstream B, applied, `aria-paste-plus/`) —
  `action_paste_clipboard()` (Ctrl+V) no longer collapses multi-line clipboard content to one space-
  joined line; a newline in the clipboard now pushes `PastePreviewScreen`, an editable `TextArea`
  (Ctrl+Enter/Send to dispatch as a real turn, Escape/Cancel to back out), preserving structure for
  pasted code/notes/log excerpts. Single-line paste is unchanged. Right-click on `#input-box` also
  pastes now (`RippleInput.on_mouse_down`, `button == 3`), confirmed not to disturb normal left-click
  cursor placement (Textual dispatches both handlers per event, not one instead of the other).
- **Aria's Atelier — the 5th pane** (Workstream A, applied, `aria-atelier/`) — a live work-theater
  pane (`#atelier-log`) streaming every file write/edit and every command she runs, color-coded
  (green=new file, yellow=edited+diff, blue=command). A new `work_events.py` module derives the event
  purely from data already in scope at the one tool-dispatch choke point in `loop.py` — no individual
  tool file was touched. Reuses the SAME `events.jsonl` tailer the "live" pane already runs (a routing
  branch at the top of `_render_event()` sends `work-`-prefixed flags to the new pane instead of a
  second, redundant tailing worker).
- **Vessel-Health — a 4th strip** (Workstream I, applied, `aria-vessel-health/`) — rolls up kernel-
  coherence (H2), sentinel health + drift (`gather_health()`), signal (H3's epistemic ledger), and
  flourishing trend (C's apply-queue/quarantine) into one view. The expensive kernel-coherence scan
  reuses `aria-security-strip-wire`'s proven cache+background-worker pattern verbatim (module-level
  cache/lock, 300s periodic timer, never triggered eagerly on mount) rather than re-deriving the same
  GIL-contention lesson. CLI: `python -m sovereign_agent.vessel_health`.

Everything named in this plan's original UX workstreams (A, B, I) is now built and applied.

## 7. The Staging Pipeline

`new_module → verify → scrutinize → queue → apply → quarantine`. D's path-sentinel gate and C's
apply-queue/quarantine registry (`apply_queue/`) are both **applied to live** this session — the
sequencer (`scripts/apply_queue_run.sh`) drains a durable, Kevin-selected queue through
`safe_apply.sh`, routing rollbacks to quarantine instead of losing them.

Applied/staged module count is heuristic-dependent (was 89-97 applied / 30-38 staged out of 127
total, before this session added ~11 more applied modules) — treat any single precise number as
approximate. A reliable applied-state detector remains an open candidate for J's own scanner suite.

## 8. Standing Backlog

**F — mostly closed 2026-07-03, with real ground truth on every item (not the guessed "9 staged
modules" list):**
- **Aria's eyes — wired.** `senses/eyes.py` gets a new `capture_frame()` function
  (`aria-eyes-capture/`) — `look_world()`/`see()` stay completely untouched (capture remains
  explicit/opt-in by design), plus a new Tier-1 `CaptureFrameTool`. No camera exists on this dev
  machine, so the actual-grab path is tested via a mocked subprocess call, honestly documented as
  such — the moment real hardware appears, it works with zero further wiring.
- **`apply-hardening`, `wisdom-atoms`** — both already effectively live/written; only their test
  files had never been promoted. Both had the same path-depth test bug already found elsewhere this
  session (`Path(__file__).resolve().parents[N]` breaking one level shallow once promoted) — fixed
  with the same `_find_repo_root` helper pattern, then promoted.
- **`holo-bitnet`** — a stale list entry; its real content is already live under `aria-own-mind`.
- **`docker-launch`, `mcp-serve`, `platform-compat`** — genuinely empty skeleton folders (zero files),
  not real staged modules at all.
- **`systems-audit`** — a stale point-in-time report (2026-06-22), not a module.
- **`palette-legend`, `safe-glyphs` — explicitly NOT applied.** Their apply scripts do a full-file
  replacement of `cockpit/app.py` from a payload roughly HALF today's live line count — running either
  would silently destroy this session's entire cockpit build. Confirmed dangerous, not executed; real
  future rebuild work against current `app.py`, not a drain candidate.
- 3 genuine future-horizon catalog items remain catalog-only (see §10).

**K (regression debt):** `harden_all.sh`'s isolated-staged-module-failure count went **34 → 26** after
the P0 live-crash restore. Separately, the live full test-suite failure count went **17 → 8 → 1 → 0**
across this session (9 fixed via the `apply-menu-autoupdate` M85 patch that had been built but never
run; then 7 more sub-failures across 4 real root causes: `lessons_tool.py`'s patch-target shape,
`aria_lm/data.py`'s broken corpus path noted in §4, a stale hardcoded version string in
`atoms_compact_tool.py`, and the same patch-target shape again in `vessel_status.py`/
`self_knowledge.py`; finally `test_src_hygiene` itself — the 12 stray `.bak.*` files under live `src/`
were removed 2026-07-03 on Kevin's explicit go-ahead, each one first copied to
`backups/src-hygiene-cleanup-20260703_140900/` and verified byte-identical before the original was
deleted). **The full live test suite is now fully green** (excluding the separately-known,
non-hermetic `test_git_tools.py`). Note: this full-suite count is a *different measure* from
`harden_all.sh`'s isolated-module count above — the ~26 isolated staged-module failures haven't been
re-scanned this session and may have partially resolved incidentally; that re-scan remains explicitly
paused, not started.

## 9. Hardening Record

- P0 live-crash fix: `cockpit/app.py` restored wholesale from git commit `0fdcdbd` (2026-06-20, the
  last commit before a later commit silently reverted 8 cockpit patches), committed as `16baa1d`
  (2026-07-02), independently re-verified 2026-07-03.
- All 7 of this session's new modules (D, C, H1, H2, H3, H4, J) applied to live in one supervised
  batch, committed as `78a5560` — two real bugs found and fixed *during* the apply, not before: an
  order-dependent circular import between the new sentinel modules and `stewardship/__init__.py`, and
  a session-wide test-pollution bug in a test file's own `_fresh_locator_sentinel()` helper that was
  silently decoupling the `SETTINGS` singleton from the test suite's isolation fixture.
- N, O, M, P (safe interval-stop, dual inbox, command menu, checkpoint chunks) each built, applied,
  and independently verified live this session — not just via unit tests, but real headless cockpit
  boots and direct smoke tests of the actual wired behavior.
- A real live bug Kevin caught by hand, post-apply: the "☰ commands" button's own click handler
  silently no-op'd (it only acted on `CommandButton` instances; the trigger itself is a plain
  `Button`). Root-caused and fixed the same session, with the missing test coverage that let it slip
  through (every existing test opened the popup via the keyboard action, never by actually clicking
  the button) added alongside the fix.
- A plan-accuracy review (2026-07-03) found and corrected a significant standing inaccuracy: the plan
  had described H1/H2/H3/H4/J/D/C as "staged, awaiting Kevin's apply" in multiple places, when they
  had in fact already been applied to live hours earlier in the same session (commit `78a5560`) — this
  document reflects the corrected, verified state.
- **Golden Path smoke test — BUILT + APPLIED 2026-07-03, and it caught a real, 2+-week-old production
  bug on its very first run.** `sov run` (the CLI's entry to `agent_loop()`) crashed on EVERY
  invocation, in every mode, before ever reaching the model: `SYSTEM_PROMPT_TEMPLATE.format(...)`
  raised `KeyError: 'title, action_kind, action_input'` because the 620-line prompt's own
  `workflow_create` documentation example used literal `{curly braces}` that `str.format()` tried to
  parse as a field name. Introduced 2026-06-19, undetected for 2+ weeks because the existing test for
  this function had a comment EXPLICITLY ACKNOWLEDGING the conflict and deliberately tested around it
  (checked only that the function was *callable*, never actually called it) instead of fixing it.
  Independently confirmed as a real production failure via `events.jsonl`: a scheduled daily-eval task
  hit this exact crash earlier the same day it was found. Root-cause fixed (escaped the literal
  braces); the test now genuinely calls `_system_prompt()` for every `Mode` and asserts it renders.
  `scripts/golden_path_smoke.sh` now runs the real end-to-end gate: boots `agent_loop()` headless via
  `sov run`, asserts exit 0 + a coherent non-empty response + `events.jsonl` growing — confirmed PASS
  live, verified via a real Ollama call.

## 11. God-Tier Criteria & Scorecard (Keys round, 2026-07-04)

The modern bar for a sovereign companion agent, and where she truly stands,
lives in `GOD_TIER_CRITERIA.md` — nine criteria (observability, safety,
resilience, memory, autonomy, tooling, evaluation, knowledge, love), each
scored met/partial/gap honestly, with the gap list feeding future rounds.
Headline of the Keys round it closed: her finished-but-never-called
autonomous engine got its natural-language front door (`/work`, gated,
checkpointed, message-queueing at safe boundaries), one continuous
conversation thread across restarts, a live run surface, tool paging
within authority, scope contracts (work/research/observation/security/
design), her own curiosity Q&A faculty, and the cross-platform canon.

## 10. Future Horizon Appendix

The hundreds of "construct" names from `Plans/` (Kernel Curvature Tensor, Ego Potential Well,
Flourishing Phase Space, and similar) are evocative naming exercises over ideas she substantially
already has (drift detection, signal/ego calibration, reflection loops) — preserved here as
inspiration, not obligation. The concrete, buildable child of that whole catalog, the Vessel-Health
dashboard (§6, Workstream I), is now built and applied — real telemetry instead of poetry. Workstream
E (nested non-classical core) is also now built and applied (§4) — shipped OFF by default pending
real evidence of benefit, per the EXPAI doctrine. Of the original 3 remaining future-horizon items, **continual
learning is now BUILT and applied** (2026-07-03, `aria-continual-learning/`): Reflector lessons feed
`aria_lm`'s training corpus (prioritized ahead of the distilled research so they survive truncation),
with a bounded, propose-only retrain trigger (`propose_retrain`, Tier 1 — training itself stays
Tier 3 / human-gated). The remaining 2 genuine future-horizon items (cross-layer coherence, latent
mesh / distillation pipeline) round out what's left of the original 14-generation forward catalog —
catalog only, not built.
