# The Workflow System — Sentinel, Hub, Tiers, Tutorials, Expansion

> Built from Kevin's Workflow Sentinel concept. This documents what shipped in
> v0.2.56 and what's designed-next, kept honest: the engines + safety + the
> `▸ flows` catalog are live; richer cockpit panels are roadmap **D7**.

The goal is the one Kevin named: **a user should be able to see what she can do,
and learn how to work with her fluently.** Three pieces serve that — a *hub* to
browse, *tiers + tutorials* to understand and learn, and a *Sentinel* that
watches runs and helps the system grow.

---

## 🌌 The Workflow Hub — `▸ flows`

The `▸ flows` button (and `/workflows`, `/workflows list`) opens a live,
categorized catalog generated from a single source of truth
(`workflow/catalog.py`), so it can never lie about what she actually does. Each
entry is a **card** showing: title, **tier badge**, a one-line summary, the
step-by-step *how-to*, a `try:` line you can paste, an optional **tutorial**
walkthrough, what subsystems it uses, its authority tier, and its safety note.
Demoable cards are marked `✦` — proven live by the demonstration.

Categories today: Inspect & Diagnose, Memory & Recall, Plan & Build,
Collaborate, Safety & Recovery, Self-knowledge & Calibration, Visual &
Expression, Skills & Mastery, and Voice & Vision (gated).

---

## 📐 The Four Workflow Tiers

A workflow's **tier** describes how elaborate the *flow itself* is (distinct
from its authority tier, which is about permission/risk). Shown as a badge on
each card:

| Tier | Name | Character |
|------|------|-----------|
| **T0** | Basic | single-step, instant |
| **T1** | Standard | a few steps, one subsystem |
| **T2** | Advanced | branching / tool-use / conditional |
| **T3** | God Tier | multi-step, self-checking, Sentinel-watched |

All four are represented in the catalog today; most workflows are T1, with
exemplars seeded across the rest (e.g. the Beacon Showcase and the Workflow
Sentinel are T3).

---

## 📖 The Tutorial System

A card can carry a **tutorial** — a short Guided walkthrough rendered right under
its how-to. The concept names five *modes* of teaching, which map to how Aria
already adapts:

- **Guided** — numbered steps (the form shipped on the cards now).
- **Express** — the `try:` one-liner: paste and go.
- **Interactive** — drive it live in the cockpit and watch the panes react.
- **Reference** — the full card (uses, authority, safety) as a lookup.
- **Debug** — when something stalls, the Workflow Sentinel's ALERT + the
  Conflict Logic Catalog (`diagnosis.py`) are the debugging path.

Tutorials grow over time — today's exemplars are seeds; the Expansion Protocol
below is how the rest get drafted.

---

## 🛡 The Workflow Sentinel — `workflow_sentinel.py`

A persistent, *observing* awareness layer over a run's event stream. It moves
through five states and acts intelligently on each signal:

```
IDLE → WATCHING → ALERT → LEARNING → EXPANDING
  ↑________________________________________|
```

- **IDLE** — nothing running; it rests.
- **WATCHING** — a run started; it follows each step.
- **ALERT** — it noticed a stall, error, or hesitation, and *surfaces it instead
  of pushing on*.
- **LEARNING** — a run finished; it distils a one-line lesson.
- **EXPANDING** — it has seen a novel pattern enough times to **propose** a new
  workflow card.

**Safety contract (the load-bearing part):** the Sentinel *only observes and
advises.* It never executes a workflow, never modifies code/values/charter, and
the workflows it "expands" into are **proposals, not capabilities** — inert
drafts (`status: proposed`) that a human reviews and accepts. It grows what she
*notices* and can *suggest*, never what she can silently *do*. It is bounded (a
small ring buffer), observable (every transition returns an Advisory), and
halt-able (`reset()`). The live `✦ demo` proves all of this in-process.

---

## ∞ The Expansion Protocol

The system is designed to grow without ever growing its own authority:

1. The Sentinel watches runs and counts repeated novel patterns.
2. When a pattern crosses a threshold, it drafts an **inert** `WorkflowProposal`
   — a name, a rationale, and stub steps.
3. A human reviews the draft and, if it's good, turns it into a real catalog
   card (with a tutorial stub).
4. The card joins `▸ flows`; the demo can later gain a probe for it.

Nothing auto-promotes a draft to a runnable capability. Growth is proposed by the
machine and *accepted* by a person — the same shape as the capability gap
proposals and the deferred-unsafe boundary.

---

## What's shipped vs. next

- **Shipped (v0.2.56):** the `▸ flows` hub, tier badges, tutorial walkthroughs on
  exemplar cards, the Workflow Sentinel engine (+ a live demo probe), and the
  inert expansion-proposal mechanism.
- **Next (roadmap D7):** a cockpit **Workflow Hub panel** (search/filter, the
  Run · Tutorial · Favorite · Edit · Clone actions), a **Sentinel status panel**
  (live state + pending proposals to accept), and per-card tutorials filled out
  across the whole catalog.
