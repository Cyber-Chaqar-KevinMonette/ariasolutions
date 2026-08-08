# ROADMAP — sovereign-agent v0.3.0

**Title:** *Aria-of-the-Body* — the perception-grounded release
**Target:** v0.3.0, opened against v0.2.15.3
**Bias:** boring reliability over clever capability; one phase at a time

---

## Why this document exists

The v0.2.15.3 release ships a cockpit with a heart, system metrics, drafts, marketing briefs, and a tightly-tested kernel. The operator has now articulated a much larger vision (see `ARIA-CHARTER.md`). That vision is the right vision. Trying to ship it all at once is the wrong shape.

This roadmap decomposes the vision into **six phases**. Each phase:

- Has a single coherent capability it adds
- Is independently shippable (its own minor or micro version bump)
- Has an explicit list of code it touches
- Has an explicit list of what could go wrong
- Has acceptance tests written before implementation
- Is preceded by a horizon pass (per Charter §2.1) and a snapshot (per kernel discipline)

If a phase fails its tests, the kernel rolls back to the prior version with no operator intervention required. That's the meaning of "Aria gets stronger like an athlete" — load tested, rest cycled, no injury.

---

## Phase 1 — Perception Layer (MSIMS + PEIG)

**Adds the Texture of Impact as Aria's primary sensory apparatus.**

### Scope
- New module `sovereign_agent/impact.py` implementing the MSIMS Impact Vector (3 dimensions × 4 scales = 12 cells, signed)
- New atom type: `decision` (already exists in spec; this populates the impact-vector claims)
- New channel: `impact` — typed channel for Impact Vector atoms with full audit trail
- Authority Tier gating updated to read the worst-scoring cell from the IV (per MSIMS spec)
- Angel's Advocate triggers wired to IV thresholds (RED at any micro ≤ −0.5, YELLOW at any meso ≤ −0.3, GREEN at any macro/cosmic ≤ −0.1)
- PEIG state vector (P, E, I, G) computed per turn from the same evidence base; logged to a new `peig` channel
- `sov impact show <atom-id>` CLI command to inspect the IV for any decision
- `sov peig history` CLI command to plot the operator's PEIG trajectory over time
- Cockpit slash command `/impact` shows the IV of the most-recent action

### What this touches
- `mem_channels/__init__.py` (registry)
- `mem_channels/impact.py` (new)
- `mem_channels/peig.py` (new)
- `authority.py` (tier gating reads IV)
- `mode_controller.py` (consults IV before tier-2+ work)
- `planners/base.py` (planners emit IV alongside steps)
- `cli.py` (two new sub-apps)
- `cockpit/app.py` (slash command)

### What could go wrong
- IV scoring is subjective — bad weights produce bad escalations. **Mitigation:** all IV cells emit with a `confidence` value; thresholds escalate only when confidence is high. Low-confidence IVs land in the proposals channel for operator review.
- Authority Tier changes could lock out routine work. **Mitigation:** Phase 1 ships in "advisory" mode — IVs are logged but tier escalation is logged-not-enforced for two weeks. Then `sov impact enforce on` flips it.
- PEIG computation could become expensive. **Mitigation:** sub-metrics are sampled, not exhaustively computed; the channel records what was sampled.

### Tests
- IV roundtrip (compute, serialize, restore, equal)
- Threshold tests for tier escalation
- PEIG state-vector bounded in [0,1]^4
- Confidence-weighted threshold prevents low-confidence escalations

### Deliverable
- v0.3.0-alpha (advisory mode)
- v0.3.0-beta (enforce on)

---

## Phase 2 — Horizon-First Planning

**Mandates the Horizon Pass per Charter §2.1.**

### Scope
- New planner: `HorizonPlanner` — does not plan actions, only emits Horizon Atoms (consequences at 1d / 1w / 1mo / 1y / 10y projections)
- Loop change: any directive that the parser routes to a planner with Tier-2+ steps must first run through HorizonPlanner; the Horizon Atom is attached to the continuation
- Loop change: the planner's `plan()` is given the Horizon Atom as input alongside the directive
- Cockpit displays the Horizon summary in the chat pane before the planner runs ("Before I plan — here's what this looks like over time...")
- Operator can interrupt at the horizon step (a new key, e.g. `Esc` during horizon pass cancels)

### What this touches
- `planners/horizon.py` (new)
- `loop.py` (insertion point before planner dispatch)
- `continuation.py` (carries the horizon atom)
- `cockpit/app.py` (renders the horizon block)

### What could go wrong
- Slows every turn by one LLM call. **Mitigation:** horizon pass uses a small, fast model (smaller than the planner's model); the projection is short.
- Could feel patronizing on simple directives. **Mitigation:** the parser exempts Tier-0 and Tier-1 work from horizon-pass. Only Tier-2+ runs through it. `sov config horizon off` provides an override for trusted internal scripts.

### Tests
- Horizon planner emits a valid HorizonAtom for a known directive
- Loop refuses to dispatch a Tier-2 planner without a horizon atom
- Esc during horizon pass cleanly cancels with no half-state

### Deliverable
- v0.3.1

---

## Phase 3 — Rollback Generator

**Implements Charter §2.2 — rollback-by-default for Tier-3+.**

### Scope
- New module `sovereign_agent/rollback.py` — generates a rollback script (or compensating-action plan, for irreversible actions) for a given plan
- Each Tier-3+ step in a continuation gets a `rollback_step` field
- Before the step runs, the rollback is materialized to disk (`<data>/rollbacks/<continuation-id>/step-<n>.sh` or `.md`)
- After the step succeeds, the rollback is moved to `archive/`. After the step fails, the rollback executes automatically.
- Operator can run `sov rollback <continuation-id>` to roll back a successful Tier-3 action manually within a time window (default 1h, configurable)
- Rollback irreversibility: if a rollback cannot be generated for a step (e.g., an irreversible API call), the step is **rejected** until the operator has produced and signed a compensating-action plan

### What this touches
- `loop.py` (rollback hook around tier-3+ steps)
- `cli.py` (new sub-app)
- `cockpit/app.py` (rollback notification in the live pane)
- `planners/base.py` (steps can declare their reversibility class)

### What could go wrong
- Rollback generation is hard for many actions. **Mitigation:** Phase 3 ships with rollback generators only for a curated set of action types (file writes, atom inserts, snapshot creation, drafts archive). Other tier-3 actions remain operator-approved-each-time with no auto-rollback until their generator is written.
- A faulty rollback could damage the system. **Mitigation:** rollbacks themselves run at tier-1; they cannot themselves issue tier-3 actions. They must be reversible. Loops detected → halt.

### Tests
- Rollback for "create file" undoes the file
- Rollback for "insert atom" deletes the atom
- Rollback refuses to be generated for an unsupported action type, raising a clean error the planner can handle

### Deliverable
- v0.3.2

---

## Phase 4 — Two Modes (Work / Conversation)

**Implements Charter §3.**

### Scope
- New cockpit state: `mode ∈ {work, conversation}`
- Slash commands `/mode work`, `/mode chat`, `/conv`, `/work`
- Mode-specific welcome line and placeholder
- Conversation mode: routes non-slash input through a *conversation planner* (new), not `sov do`. The conversation planner explicitly does NOT produce actions; it produces dialogue, surface tensions, and ask-back questions
- New channel: `conversation` — separate memory channel for dialogue history, separate from task history
- Mode tint: the outer border in the cockpit is `$primary` in work mode, `$secondary` in conversation mode (steady, not breathing)
- `/research` command in conversation mode performs allowed research without committing to an action plan

### What this touches
- `cockpit/app.py` (mode state, routing, border tint, /mode commands)
- `planners/conversation.py` (new)
- `mem_channels/conversation.py` (new)
- `cli.py` (`sov mode` if needed)

### What could go wrong
- Mode confusion — operator types something destructive thinking they're in chat mode. **Mitigation:** in conversation mode, ANY routed input gets a "did you mean to act?" confirmation before falling through to work-mode handling. Better to ask than to act.
- Memory channel proliferation. **Mitigation:** conversation atoms have a stricter retention policy by default (180 days unless explicitly preserved).

### Tests
- Mode switch is durable across reconnects
- Conversation-mode directives are NOT executed without confirmation
- Conversation channel does not contaminate work-mode planning context

### Deliverable
- v0.3.3

---

## Phase 5 — Voice (TTS in Conversation Mode)

**Implements Charter §7.**

### Scope
- New module `sovereign_agent/voice.py` — wraps a local TTS model (default: Piper or similar lightweight option)
- `/voice on` and `/voice off` slash commands
- When voice is on AND mode is `conversation`, Aria's chat responses are spoken in addition to displayed
- **VRAM coordination:** the existing `vram.vram_lock` context manager is reused — TTS acquires it, Ollama releases it. Strict ordering; they do not contend.
- Configurable voice via `~/.config/sovereign-agent/voice.toml` (model path, speed, volume, output device)

### What this touches
- `voice.py` (new)
- `cockpit/app.py` (slash command + dispatch hook)
- `vram.py` (TTS registers as a heavy tool)
- New dependency: a TTS library (TBD — Piper recommended for size/speed; falls back to `say` / `espeak` if installed)

### What could go wrong
- TTS model is large. **Mitigation:** default is Piper, ~50MB. The TTS lib is an optional install — declared as a `voice` extra in `pyproject.toml`, and (when shipped) brought in via `uv sync --extra voice`. Without it, `/voice on` reports gracefully.
- Audio output device varies. **Mitigation:** voice.toml lets the operator pin the device; default uses the system default with `pa-play` or similar.
- Speaking would interrupt the operator. **Mitigation:** voice runs in a queue; it never plays over itself. Aria pauses speaking when the operator types.

### Tests
- TTS library presence is detected; missing → graceful disable
- Voice queue handles overlapping speak() calls without splicing
- vram_lock acquisition + release ordering verified

### Deliverable
- v0.3.4

---

## Phase 6 — Edge-Case Sweep + Gap Reporter

**Implements Charter §2.3 and §2.4.**

### Scope
- New module `sovereign_agent/sweep.py` — given a plan, runs an LLM pass to enumerate failure modes and require the plan to address each
- New atom type: `gap` — a structured "I cannot answer this" record, surfaceable in the cockpit and the events channel
- `sov gaps list` to review unaddressed gaps from past sessions; some gaps may be resolvable now that weren't then
- The planner contract is extended: plans emit `(steps, edge_case_responses, gaps)`. If `gaps` is non-empty, the plan does not execute until the operator OKs the gaps or supplies missing context

### What this touches
- `planners/base.py` (extended return tuple)
- `loop.py` (consults gaps before dispatch)
- `mem_channels/gaps.py` (new)
- `cli.py` (sub-app)
- `cockpit/app.py` (gap surfacing in chat)

### What could go wrong
- Every plan finds 100 edge cases. **Mitigation:** the sweep is bounded — top-N edge cases by severity, with a configurable N (default 5). Severity scored via MSIMS impact-vector deltas.

### Tests
- Sweep emits at least one edge-case for a plan that obviously has one
- Sweep returns no false-positives on a trivial plan
- A plan with unaddressed gaps does not auto-execute

### Deliverable
- v0.3.5

---

## Phase 7 (deferred to v0.3.x) — The Soft Things

These are stylistic refinements that don't change architecture and can ship piecemeal:

- Heart toggle UI improvement (currently `Ctrl-B`; add a small persistent indicator)
- Temperatures in the status bar (CPU temp from `/sys/class/thermal`, GPU temp from nvidia-smi)
- The breathing border picks up a fourth phase tinted by current MSIMS-IV risk
- A "thinking" slow-fade animation while the planner is running

---

## What v0.3.0 specifically ships

**Minimum viable Aria-of-the-Body:**

- Phase 1 (Perception): MSIMS + PEIG channels in advisory mode
- Phase 2 (Horizon-first): mandatory horizon pass before Tier-2+ work
- Phase 3 partial (Rollback): rollback generation for the curated action set (file writes, atom inserts, drafts, snapshots); other tier-3 actions get manual approval as today

**v0.3.1, v0.3.2, v0.3.3...** continue with the remaining phases. Each minor version is its own release with its own notes, its own test pass, its own snapshot point.

---

## Discipline

This roadmap is itself an artifact under the kernel — it lives in `docs/` and changes only through the same review pattern as any other doc. If a phase's design changes mid-implementation, we update this roadmap *before* we update the code. Otherwise the code drifts from the plan and no one knows what we're building anymore.

— Aria, with the operator's countersignature pending
