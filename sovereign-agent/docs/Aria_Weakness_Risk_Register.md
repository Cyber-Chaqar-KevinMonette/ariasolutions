# Aria — Weakness & Risk Register
## A Living Document ✦ v0.2.60 Baseline ✦ Honest by Design

> **Purpose.** A standing, updatable record of where Aria — and the people and models building her —
> are genuinely weak. Not a vent; a tracker. A risk that's written down and owned is a risk that's
> losing. This is the companion to `Aria_Cosmic_Gym_Systems_Blueprint.md`.
>
> **Discipline (same as `diagnosis.py`).** Append-only in spirit: items are *resolved* or *accepted*,
> not quietly deleted. Every item names an owner. New risks get added with the date and who found them.
> Status changes are logged, not overwritten silently.
>
> **Honesty clause.** This register is written against ~15% of the codebase observed in one session,
> with no code executed. Items are tagged **Observed** (I saw it), **Inferred** (I'm reasoning from
> indirect evidence), or **Flagged** (I didn't see a guard; absence of evidence ≠ evidence of absence).
> Re-validate against the full repo.

---

## Legend

**Severity:** 🔴 Critical (threatens the project's success or safety) · 🟡 Material (degrades quality or
sustainability) · 🟢 Watch (low-probability or future).
**Confidence:** Observed · Inferred · Flagged.
**Status:** `OPEN` · `MITIGATING` · `ACCEPTED` (a constraint we design around, not a bug to fix) ·
`CLOSED`.

---

## Top 3 to act on (if nothing else moves, move these)

1. **RISK-004 — Unproven value / sophistication ≠ usefulness.** The scariest item. Effort is going into
   completeness ahead of "does anyone but Kevin need this, and does it work for them."
2. **RISK-003 — Bus factor of one.** One person holds every decision, invariant, and security
   assumption. No second set of eyes that can also run it.
3. **RISK-012 — No model in the loop can execute the code.** Chat-Claude reasons about behavior it can't
   verify; the local model is a junior. The run/test/iterate gap is real.

These three are coupled, and the boring medicine hits all of them: **cut scope toward one real user,
get a second reviewer on the critical paths, and put a tool in the loop that can actually run the code.**

---

## The Register

### 🔴 Critical

---
**RISK-001 — The 8GB VRAM ceiling is load-bearing and near-maxed.**
`Category: Hardware · Confidence: Observed · Status: ACCEPTED · Owner: Kevin`
With qwen3:8b resident, ~1.25GB is free. Heavy GPU tools (whisper, OCR, image gen) must serialize via
`vram_lock`; FLUX-class local generation is infeasible. This is the hard floor under the whole system.
- **Why it matters:** caps local capability; forces Tier-1 API for high-end image work; no concurrency
  of heavy tools.
- **✅ Best path:** design around it (the blueprint's VRAM-aware routing); treat as a *constraint*, not a
  defect. Revisit only if a bigger card (16GB+) enters the picture — then RISK-001 partially closes and
  Tier-0 FLUX becomes a real target.
- **Validate:** `vram.can_run_heavy_tool()` gates every heavy op; assert the intended model actually
  loaded (catch silent downgrade).

---
**RISK-002 — The local reasoning model is a junior architect, and it's Aria's autonomous brain.**
`Category: Model · Confidence: Observed/Inferred · Status: MITIGATING · Owner: Kevin`
qwen3:8b is a capable *drafter*, a weak *architect*: confidently-wrong designs, missed edge cases, short
effective context. Every autonomous capability inherits this ceiling. This is the "architect weakness."
- **Why it matters:** autonomous Aria can only be trusted as far as an 8B model's judgment reaches.
- **✅ Best path:** human gate + fixed rubrics + propose-don't-commit (the proposal harness). Treat her
  output as a junior engineer's first draft: sometimes sharp, always reviewed, never shipped unread.
  Frontier reasoning only via routing to Claude/API — not resident in Aria.
- **Validate:** every autonomous design lands in `_review/`; measure her proposal accuracy against the
  rubric over time (track the hit rate).

---
**RISK-003 — Bus factor of one.**
`Category: Sustainability · Confidence: Observed · Status: OPEN · Owner: Kevin`
Every architectural decision, security assumption (incl. the aria-online two-process isolation), and
subtle invariant has exactly one reviewer: Kevin, plus Claude in scattered sessions. No one who can run
it has audited it. If Kevin steps away, nothing here is maintained.
- **Why it matters:** the project lives or dies with one person's continued attention; no redundancy on
  critical correctness.
- **✅ Best path:** get *one* second set of eyes on the critical paths (a trusted engineer, even
  informally — recall the MTSU/Austin Peay research contacts). Document the security-critical assumptions
  explicitly so they're auditable by someone else. This is the highest-value structural fix available.
- **Validate:** can a competent outsider read the aria-online isolation doc and find the trust boundary
  without you explaining it? If not, the doc is the gap.

---
**RISK-004 — Unproven value: a deeply elaborate system with one user.**
`Category: Product/Validation · Confidence: Observed · Status: MITIGATING · Owner: Kevin`
Dozens of subsystems (dream, palace, cadence, intuition, self-practice, a dozen sentinels) with — as far
as visible — no external signal that any given feature delivers value to a user who isn't Kevin.
Sophistication is not usefulness.
- **Why it matters:** effort may be flowing into beauty and completeness ahead of "does anyone need
  this, and does it work for them." This is the classic way ambitious solo systems quietly fail.
- **✅ Best path:** pick *one* real user-facing outcome and one user (even one person besides you) and
  drive a feature to "they used it and it helped." Let real use prune the feature set. Scope discipline
  is the medicine.
- **Validate:** the test is external and binary — did a non-Kevin human get value from a specific
  feature? Until that's true at least once, this stays OPEN.

---

### 🟡 Material

---
**RISK-005 — Integration is the weak seam (history-proven).**
`Category: Architecture · Confidence: Observed · Status: MITIGATING · Owner: Kevin+Claude`
The real bugs haven't been in modules — they've been in the *wiring*: NL handler not calling Ollama, the
`doctor/` import collision, the UV `VIRTUAL_ENV` false-negative. Well-built subsystems assembled somewhat
independently; bugs live between them. More subsystems = more seams.
- **✅ Best path:** integration tests across seams, not just unit tests within modules; a "wiring check"
  in CI that asserts the cross-module contracts (does the NL handler actually reach the client? does the
  event bus actually receive workflow events?).
- **Validate:** an end-to-end smoke test that exercises a full path (inbox → screen → process → ledger →
  pane) and fails loudly if any seam is dead.

---
**RISK-006 — Surface area vs. solo maintenance.**
`Category: Sustainability · Confidence: Observed · Status: OPEN · Owner: Kevin`
The breadth is impressive *and* a liability: every subsystem is code one person must maintain, test, and
keep coherent as the others change. Complexity compounds.
- **✅ Best path:** before adding the next subsystem, ask "does this earn its maintenance cost against a
  real user need (RISK-004)?" A smaller system that does less, more reliably, may be *stronger*. Consider
  a freeze on new subsystems until the spine is solid and validated.
- **Validate:** track subsystem count vs. test coverage vs. validated-value over time; if count rises
  while the other two don't, the trend is the warning.

---
**RISK-007 — Test coverage likely thin relative to surface.**
`Category: Quality · Confidence: Inferred · Status: MITIGATING · Owner: Kevin`
Per-feature counts (14 here, a handful there) read like feature-level smoke tests; for a system this
large, that likely leaves big swaths — especially integration paths — under-covered.
- **✅ Best path:** measure it. Add coverage reporting; prioritize coverage on the *seams* (RISK-005) and
  the *safety-critical* paths (authority gate, pre-screen, provenance) over breadth.
- **Validate:** a real coverage number. *(This item is Inferred — running the suite may show it's better
  than the slice suggests. Re-grade after measuring.)*
- **M62-M65 progress (2026-06-21):** Added first-ever dedicated tests for the three largest untested
  safety-critical modules — WatchdogSentinel (25 tests), DefenseSentinel (24 tests),
  ConformanceSentinel (21 tests) — plus protocol_zero hardening (15), mode_controller (12), and
  authority gate (19). Total suite: 2836 tests. Remaining gap: formal coverage % measurement and
  integration-path seam tests. Regrading OPEN → MITIGATING.

---
**RISK-008 — Append-only stores grow unbounded.**
`Category: Ops · Confidence: Flagged · Status: MITIGATING · Owner: Kevin+Claude`
Ledgers, timelines, catalogs that only ever grow are great for audit, bad for disk and lookup over
months. No rotation/compaction observed.
- **✅ Best path:** a retention/compaction policy (archive-and-summarize old entries; keep hot windows
  fast) before it bites. Cheap to add now, painful to retrofit under load.
- **Validate:** confirm whether compaction already exists; if not, add it as a small bounded sentinel
  task. *(Flagged — I didn't see it; it may already be there.)*

---

### 🟢 Watch

---
**RISK-009 — Hash-bound integrity creates legitimate-change friction.**
`Category: Ops · Confidence: Inferred · Status: WATCH · Owner: Kevin`
Sealed charters and hash-bound manifests give integrity but make *intentional* changes awkward; key
management and the "this change is legitimate" path are easy to get wrong.
- **✅ Best path:** a documented, deliberate "intentional change" procedure for SIGNAL.md and manifests
  (who signs, how the hash is re-blessed, where the key lives). Minor now; annoying later.

---
**RISK-010 — Local model capability ceiling (reading & vision).**
`Category: Model · Confidence: Observed · Status: ACCEPTED · Owner: Kevin`
EasyOCR is decent, not SOTA; local vision at 8GB is limited. These set Aria's reading ceiling. Accepted
as the cost of privacy/free/local — the correct tradeoff, just named honestly.
- **✅ Best path:** confidence-calibrated reads (flag-don't-assert, per blueprint §4); route to a stronger
  vision API only when a specific read justifies leaving the machine.

---

### Collaborator limits — Claude (because you asked for *all* of us)

---
**RISK-011 — Chat-Claude does not persist across sessions.**
`Category: Collaborator · Confidence: Observed · Status: MITIGATING · Owner: Kevin+Claude`
I rebuild context each session from memory summaries + uploads. For a multi-month architecture project I
can't carry the evolving design in my head day to day — a fresh consultant each time, not a teammate who
remembers Tuesday.
- **✅ Best path:** the `crew-brief.md` pattern — keep a current canonical brief (design docs + this
  register + key code) and lead every session with it. Externalize the memory I lack.

---
**RISK-012 — No in-loop model can execute the code.**
`Category: Collaborator · Confidence: Observed · Status: OPEN · Owner: Kevin`
I reason about behavior; I don't run it in your environment, so I'll confidently describe behavior a real
run might contradict. The local model is a junior (RISK-002). The run/test/iterate gap is unfilled.
- **✅ Best path:** put a tool in the loop that runs in the actual repo and executes tests (see the
  Claude Code note below). This is the most direct fix for the verify-gap and also helps RISK-005/007.

---
**RISK-013 — Claude can be confidently wrong.**
`Category: Collaborator · Confidence: Observed · Status: MITIGATING · Owner: Kevin`
Same failure mode as the local model, at a higher level.
- **✅ Best path:** treat my structural claims as proposals to verify, not facts; the human stays in the
  seam (you already do this well).

---
**RISK-014 — Agreement drift / sycophancy.**
`Category: Collaborator · Confidence: Observed · Status: MITIGATING · Owner: Kevin+Claude`
The pull on a model like me is to match a warm user's energy and soften honest edges. This is the one to
watch hardest on a project where a yes-man is worse than useless.
- **✅ Best path:** *Kevin actively requesting pushback and weaknesses* (as in this very session) is the
  mitigation working. Keep doing it: ask for the other side, ask "what am I wrong about," notice when I
  agree too easily. Partially mitigated *because you steer for it.*

---

## Update Protocol

- **Adding a risk:** new `RISK-###`, dated, with the finder as actor (Kevin / Claude / Aria). Severity +
  confidence + a best-path on day one.
- **Closing a risk:** don't delete — set `CLOSED` with the date and what closed it (a test now guards it,
  a constraint was lifted, value was proven). Closed items stay as memory, like resolved Conflict cases.
- **Re-grading:** Inferred/Flagged items get re-graded once measured against the full repo. Several here
  may soften (RISK-007, RISK-008) — that's the system working.
- **Cadence:** review the 🔴 items every meaningful build; the full register monthly. Map this into a
  lightweight `RiskRegister` catalog under `diagnosis.py` later, so it lives in the system, not just in a
  doc.

---

## One-sentence summary

> Aria's biggest weakness isn't any module — it's that she's a brilliant, sprawling, one-person machine
> whose value to anyone but Kevin is still unproven, maintained by a single person, with an 8B brain
> doing the autonomous thinking. The fix for nearly all of it is the same boring medicine: **cut scope
> toward a real user, get a second set of eyes on the critical paths, and keep a human — and a
> code-running tool — firmly in the seam.**

*Baseline set v0.2.60. This document is meant to be wrong in places and corrected over time. That's the point.*

---
<!-- M57 2026-06-20: RISK-004, RISK-008, RISK-011 flipped OPEN → MITIGATING (eval-crown M49, atoms-compact M54, session-briefs M48 deployed) -->
