"""workflow_sentinel — Aria's execution nervous system.

A persistent, *observing* awareness layer for running workflows. It watches the
event stream a workflow / demo / practice run emits and moves through five
states, acting intelligently on each signal:

    IDLE  →  WATCHING  →  ALERT  →  LEARNING  →  EXPANDING
      ↑__________________________________________________|

  - IDLE       nothing is running; the Sentinel rests.
  - WATCHING   a run started; it follows each step.
  - ALERT      it noticed a stall, an error, or a hesitation pattern, and says so.
  - LEARNING   a run completed; it distils a short lesson from what happened.
  - EXPANDING  it has seen the same novel pattern enough times to *propose* a new
               workflow card — an INERT draft for a human to review.

The safety contract (mirrors the rest of the sentinel family): the Workflow
Sentinel **only observes and advises.** It never executes a workflow, never
modifies code, values, or the charter, and the workflows it "expands" into are
**proposals, not capabilities** — drafts with status ``proposed`` that a human
reads and accepts. Nothing here auto-grows what Aria can *do*; it grows what she
*notices* and what she can *suggest*. It is bounded (a small ring buffer of
recent signals), observable (every transition returns an Advisory), and halt-able
(``reset()`` returns it to IDLE at any time).

Kill switch: none — predates the unified Sentinel registry; invoked directly by its callers, NOT gated by SOV_NO_SENTINELS or any per-sentinel SOV_NO_* env var.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Iterable, Optional

__all__ = [
    "STATES", "SIGNAL_KINDS",
    "WorkflowSignal", "Advisory", "WorkflowProposal", "WorkflowSentinel",
]

STATES = ("idle", "watching", "alert", "learning", "expanding")
SIGNAL_KINDS = ("start", "step", "stall", "error", "hesitation", "done", "pattern")

# How many of the same novel pattern we must see before proposing a workflow.
_EXPAND_THRESHOLD = 3
# Ring-buffer size — bounded memory; the Sentinel never hoards.
_HISTORY = 64


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class WorkflowSignal:
    """One thing the Sentinel observed about a run."""
    kind: str                       # one of SIGNAL_KINDS
    workflow: str = ""              # which workflow/run it concerns
    detail: str = ""
    at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Advisory:
    """What the Sentinel surfaces after a signal — never an action, just a word."""
    state: str
    headline: str
    detail: str = ""
    proposal: "Optional[WorkflowProposal]" = None
    at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.proposal is not None:
            d["proposal"] = self.proposal.to_dict()
        return d


@dataclass
class WorkflowProposal:
    """An INERT draft of a possible new workflow. status stays 'proposed' until a
    human reviews and accepts it; the Sentinel never makes it runnable itself."""
    name: str
    rationale: str
    observed_pattern: str
    steps: list[str] = field(default_factory=list)
    suggested_tier: int = 1
    status: str = "proposed"        # proposed -> (human) accepted / declined
    at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)


class WorkflowSentinel:
    """A bounded, observing state machine over a run's event stream.

    Drive it by feeding signals to ``observe``; read ``state`` and the returned
    Advisory. It never acts on the workflow — it watches, warns, learns, and
    proposes. Reset to IDLE whenever you like.
    """

    def __init__(self, *, expand_threshold: int = _EXPAND_THRESHOLD):
        self.state: str = "idle"
        self._history: deque[WorkflowSignal] = deque(maxlen=_HISTORY)
        self._advisories: list[Advisory] = []
        self._proposals: list[WorkflowProposal] = []
        self._pattern_counts: dict[str, int] = {}
        self._expand_threshold = max(2, int(expand_threshold))
        self._proposed_patterns: set[str] = set()

    # -- the one entry point ----------------------------------------------
    def observe(self, signal: WorkflowSignal) -> Advisory:
        """Take in one signal, transition, and return the Advisory it produces."""
        if signal.kind not in SIGNAL_KINDS:
            raise ValueError(f"unknown signal kind: {signal.kind!r}")
        self._history.append(signal)
        adv = self._transition(signal)
        self._advisories.append(adv)
        return adv

    def observe_event(self, kind: str, workflow: str = "", detail: str = "") -> Advisory:
        """Convenience: build + observe a signal in one call."""
        return self.observe(WorkflowSignal(kind=kind, workflow=workflow, detail=detail))

    # -- transitions -------------------------------------------------------
    def _transition(self, sig: WorkflowSignal) -> Advisory:
        wf = sig.workflow or "a workflow"
        if sig.kind == "start":
            self.state = "watching"
            return Advisory("watching", f"watching {wf}",
                            "following each step; I'll flag a stall or error.")
        if sig.kind == "step":
            # Stay in whatever non-idle state we're in (watching, usually).
            if self.state == "idle":
                self.state = "watching"
            return Advisory(self.state, f"{wf}: {sig.detail or 'step'}")
        if sig.kind in ("stall", "error", "hesitation"):
            self.state = "alert"
            word = {"stall": "stalled", "error": "errored",
                    "hesitation": "looks uncertain"}[sig.kind]
            return Advisory("alert", f"{wf} {word}",
                            sig.detail or "surfacing it rather than pushing on.")
        if sig.kind == "done":
            self.state = "learning"
            lesson = self._lesson_from_history(wf, sig.detail)
            return Advisory("learning", f"{wf} finished",
                            f"lesson noted: {lesson}")
        if sig.kind == "pattern":
            return self._maybe_expand(sig)
        # fallback (never reached given the guard in observe)
        return Advisory(self.state, f"{wf}: {sig.kind}")

    def _lesson_from_history(self, wf: str, detail: str) -> str:
        recent = [s.kind for s in self._history][-6:]
        had_trouble = any(k in ("stall", "error", "hesitation") for k in recent)
        if detail:
            return detail
        if had_trouble:
            return f"{wf} completed after some friction — worth a calmer rerun."
        return f"{wf} ran clean — a good exemplar to keep."

    def _maybe_expand(self, sig: WorkflowSignal) -> Advisory:
        """A novel repeated pattern → propose a new workflow card (inert)."""
        key = (sig.detail or sig.workflow or "pattern").strip().lower()
        self._pattern_counts[key] = self._pattern_counts.get(key, 0) + 1
        count = self._pattern_counts[key]
        if count >= self._expand_threshold and key not in self._proposed_patterns:
            self._proposed_patterns.add(key)
            self.state = "expanding"
            proposal = WorkflowProposal(
                name=f"(proposed) {sig.workflow or key}",
                rationale=(f"seen this pattern {count} times — it looks like a "
                           "repeatable workflow worth a card."),
                observed_pattern=key,
                steps=["(draft) capture the steps you took",
                       "(draft) name the inputs + the finished result",
                       "(draft) review + accept to make it a real workflow"],
                suggested_tier=1)
            self._proposals.append(proposal)
            return Advisory("expanding", f"new workflow worth proposing: {key}",
                            "drafted an inert card for you to review + accept.",
                            proposal=proposal)
        # not yet enough times, or already proposed — stay where we are
        return Advisory(self.state, f"noticed pattern: {key}",
                        f"seen {count}x (proposes at {self._expand_threshold}).")

    # -- control -----------------------------------------------------------
    def reset(self) -> None:
        """Return to IDLE. (Counts + proposals persist; only the live state resets.)"""
        self.state = "idle"

    # -- read --------------------------------------------------------------
    def proposals(self, *, pending_only: bool = True) -> list[WorkflowProposal]:
        if pending_only:
            return [p for p in self._proposals if p.status == "proposed"]
        return list(self._proposals)

    def advisories(self) -> list[Advisory]:
        return list(self._advisories)

    def history(self) -> list[WorkflowSignal]:
        return list(self._history)

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "signals_seen": len(self._history),
            "advisories": len(self._advisories),
            "pending_proposals": len(self.proposals()),
            "pattern_counts": dict(self._pattern_counts),
        }

    def render(self) -> str:
        glyph = {"idle": "\u25cb", "watching": "\u25c9", "alert": "\u25b2",
                 "learning": "\u25c6", "expanding": "\u2726"}.get(self.state, "\u25cb")
        s = self.snapshot()
        lines = [
            f"[b]{glyph} Workflow Sentinel \u2014 {self.state.upper()}[/b]  "
            f"[dim]({s['signals_seen']} signals \u00b7 {s['pending_proposals']} "
            f"pending proposal(s))[/dim]",
        ]
        for p in self.proposals():
            lines.append(f"[dim]  proposed: {p.name} \u2014 {p.rationale}[/dim]")
        if not self.proposals():
            lines.append("[dim]  observing only \u2014 it watches, warns, learns, and "
                         "proposes; it never runs or changes anything.[/dim]")
        return "\n".join(lines)
