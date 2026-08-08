"""
╔══════════════════════════════════════════════════════════════════════════╗
║  capabilities.py — subsystem awareness, gap analysis, variant routing      ║
║                                                                            ║
║  This is the layer that lets Aria reason about her *own* toolset: which    ║
║  subsystems (action-kind handlers) she has, which a goal will need, which  ║
║  are missing, and — when several variants of a capability exist — which    ║
║  one best fits a given flow.                                               ║
║                                                                            ║
║  Authority posture (read this before extending):                          ║
║    • This module PROPOSES. It never writes code into the live package and  ║
║      never auto-registers a handler. Missing subsystems are drafted as     ║
║      *proposals* under <data_dir>/proposals/capabilities/ for a human to   ║
║      review and activate. That boundary is the whole point: a system that  ║
║      silently rewrites itself can't be reasoned about or rolled back.      ║
║    • Reversible, read-only, internal decisions (variant selection, gap     ║
║      analysis, reading) are self-answerable — no human needed.             ║
║    • Consequential / irreversible / self-modifying actions require a       ║
║      human. AuthorityPolicy makes that explicit and tunable.               ║
║                                                                            ║
║  v0.2.35.0                                                                 ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from sovereign_agent.workflow.agentic_loop import AgenticLoop, PlanStep

logger = logging.getLogger(__name__)


# ─── Event helper (fail-safe; observability must never break a run) ────────


def _emit(flag: str, *, trace_id: str, parent_id: Optional[str] = None,
          payload: Optional[dict[str, Any]] = None) -> Optional[str]:
    try:
        from sovereign_agent.events import emit_event
        return emit_event(flag, plane="control", trace_id=trace_id,
                          parent_id=parent_id, payload=payload or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("capability event %s failed to emit: %r", flag, exc)
        return None


def _new_trace_id() -> str:
    try:
        from ulid import ULID
        return str(ULID())
    except Exception:  # noqa: BLE001
        import uuid
        return uuid.uuid4().hex


def _tokens(text: str) -> set[str]:
    """Lowercase word tokens, for flow/tag overlap scoring."""
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) > 2}


# ─── Capability ────────────────────────────────────────────────────────────


CapabilityStatus = str  # "available" | "missing" | "stub"


@dataclass(frozen=True)
class Capability:
    """One subsystem Aria can (or could) use to act.

    A capability maps to an ``action_kind`` the agentic loop dispatches on.
    Several capabilities may share an action_kind — those are *variants*,
    distinguished by ``name`` and ``flow_tags`` so the router can pick the
    right one for a given flow.
    """
    name: str                       # unique, e.g. "shell.default" or "shell.git"
    action_kind: str                # the loop's dispatch key, e.g. "shell"
    summary: str
    flow_tags: frozenset[str] = frozenset()
    status: CapabilityStatus = "available"
    variant_of: Optional[str] = None     # base capability name, if a variant
    selector_hints: frozenset[str] = frozenset()  # extra routing keywords

    def fit_score(self, flow: str) -> tuple[float, str]:
        """Score 0..1 how well this capability fits a free-text flow, plus a
        plain-English reason. Overlap of flow tokens with tags + hints."""
        flow_tok = _tokens(flow)
        if not flow_tok:
            return (0.0, "no flow descriptor given")
        vocab = {t.lower() for t in (self.flow_tags | self.selector_hints)}
        hits = sorted(flow_tok & vocab)
        if not hits:
            return (0.0, "no tag overlap with the flow")
        score = min(1.0, len(hits) / max(3, len(flow_tok)) + 0.15 * len(hits))
        return (round(score, 3), "matches " + ", ".join(hits))


# Baseline catalog: the action kinds the loop knows how to dispatch, with the
# flows each naturally serves. `from_loop` marks which are actually wired.
#
# Variants share an action_kind (and therefore the same underlying handler)
# but carry flow-specific tags so the router can pick the best-fitting label
# for a flow. Registering a *distinct* handler under a variant name is the
# upgrade path — until then a variant routes to the shared handler.
DEFAULT_CATALOG: tuple[Capability, ...] = (
    Capability("note.default", "note",
               "Record a thought or placeholder step; no side effects.",
               frozenset({"reflection", "logging", "placeholder", "planning"})),

    # ── shell + flow variants ──────────────────────────────────────────
    Capability("shell.default", "shell",
               "Run an allow-listed shell command (general).",
               frozenset({"system", "execution", "filesystem", "command", "run"})),
    Capability("shell.git", "shell",
               "Shell flow tuned for version control.",
               frozenset({"git", "commit", "branch", "merge", "rebase",
                          "clone", "push", "pull", "stage", "checkout"}),
               variant_of="shell.default"),
    Capability("shell.build", "shell",
               "Shell flow tuned for building/packaging.",
               frozenset({"build", "compile", "make", "cmake", "install",
                          "package", "bundle", "setup"}),
               variant_of="shell.default"),
    Capability("shell.test", "shell",
               "Shell flow tuned for testing/linting.",
               frozenset({"test", "pytest", "unittest", "lint", "check",
                          "coverage", "verify"}),
               variant_of="shell.default"),

    # ── file_write + flow variants ─────────────────────────────────────
    Capability("file_write.default", "file_write",
               "Write a file inside the sandbox root (general).",
               frozenset({"authoring", "filesystem", "scaffolding", "config"})),
    Capability("file_write.docs", "file_write",
               "Writing flow tuned for documentation.",
               frozenset({"documentation", "readme", "markdown", "docs",
                          "changelog", "notes", "guide"}),
               variant_of="file_write.default"),
    Capability("file_write.code", "file_write",
               "Writing flow tuned for source code.",
               frozenset({"codegen", "code", "source", "module", "script",
                          "implementation"}),
               variant_of="file_write.default"),

    # ── file_read + flow variants ──────────────────────────────────────
    Capability("file_read.default", "file_read",
               "Read a file inside the sandbox root (general).",
               frozenset({"inspection", "filesystem", "context", "read"})),
    Capability("file_read.audit", "file_read",
               "Reading flow tuned for review/audit.",
               frozenset({"audit", "review", "inspect", "scan", "analysis",
                          "security"}),
               variant_of="file_read.default"),

    # ── known-but-unwired kind (a real gap to demonstrate) ─────────────
    Capability("timer_schedule.default", "timer_schedule",
               "Schedule a delayed reminder/message.",
               frozenset({"scheduling", "reminder", "cadence", "followup"})),
)


# ─── Registry ──────────────────────────────────────────────────────────────


class CapabilityRegistry:
    """What Aria can do right now, and what she knows about but lacks."""

    def __init__(self) -> None:
        self._caps: dict[str, Capability] = {}

    def register(self, cap: Capability) -> None:
        self._caps[cap.name] = cap

    def get(self, name: str) -> Optional[Capability]:
        return self._caps.get(name)

    def all(self) -> list[Capability]:
        return sorted(self._caps.values(), key=lambda c: c.name)

    def by_action_kind(self, action_kind: str) -> list[Capability]:
        return [c for c in self._caps.values() if c.action_kind == action_kind]

    def variants_of(self, base_name: str) -> list[Capability]:
        base = self.get(base_name)
        kind = base.action_kind if base else base_name
        return [c for c in self._caps.values()
                if c.action_kind == kind or c.variant_of == base_name]

    def available_kinds(self) -> set[str]:
        return {c.action_kind for c in self._caps.values() if c.status == "available"}

    def missing_kinds(self) -> set[str]:
        avail = self.available_kinds()
        return {c.action_kind for c in self._caps.values()
                if c.status != "available" and c.action_kind not in avail}

    @classmethod
    def from_loop(
        cls,
        loop: AgenticLoop,
        *,
        catalog: Iterable[Capability] = DEFAULT_CATALOG,
        extra: Iterable[Capability] = (),
    ) -> "CapabilityRegistry":
        """Build a registry from a loop's *actually registered* handlers.

        A catalog capability whose action_kind is registered on the loop is
        marked ``available``; one that isn't is marked ``missing``. Any
        ``extra`` capabilities (e.g. registered variants) are added as-is.
        """
        reg = cls()
        wired = set(loop.registered_kinds())
        for cap in catalog:
            status = "available" if cap.action_kind in wired else "missing"
            reg.register(Capability(
                name=cap.name, action_kind=cap.action_kind, summary=cap.summary,
                flow_tags=cap.flow_tags, status=status,
                variant_of=cap.variant_of, selector_hints=cap.selector_hints,
            ))
        # Any registered kind the catalog didn't mention → record it available.
        known = {c.action_kind for c in catalog}
        for kind in wired - known:
            reg.register(Capability(f"{kind}.default", kind,
                                    f"Registered handler for {kind!r}.",
                                    status="available"))
        for cap in extra:
            reg.register(cap)
        return reg


# ─── Variant routing ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class RankedVariant:
    capability: Capability
    score: float
    reason: str


class VariantRouter:
    """Given a flow, pick the best-fitting variant of a capability.

    This is a self-answerable decision: it only chooses among capabilities
    that already exist, and choosing wrong is reversible (re-run with a
    different flow descriptor), so no human is required.
    """

    def rank(self, base: str, flow: str, registry: CapabilityRegistry) -> list[RankedVariant]:
        candidates = registry.variants_of(base)
        ranked = []
        for cap in candidates:
            score, reason = cap.fit_score(flow)
            # Tiny tie-break toward the explicit default so behavior is stable.
            if cap.name.endswith(".default"):
                score += 0.01
            ranked.append(RankedVariant(cap, round(score, 3), reason))
        ranked.sort(key=lambda r: r.score, reverse=True)
        return ranked

    def best(self, base: str, flow: str, registry: CapabilityRegistry) -> Optional[RankedVariant]:
        ranked = self.rank(base, flow, registry)
        return ranked[0] if ranked else None


# ─── Scaffold proposals (drafts only — never auto-activated) ───────────────


def _camel(action_kind: str) -> str:
    return "".join(p.capitalize() for p in re.split(r"[^a-zA-Z0-9]+", action_kind) if p)


@dataclass(frozen=True)
class ScaffoldSpec:
    """A *proposed* new (or variant) subsystem. Rendering produces a handler
    stub for a human to review, implement, and register. Nothing here touches
    the live package."""
    action_kind: str
    class_name: str
    summary: str
    flow_tags: frozenset[str] = frozenset()
    variant_of: Optional[str] = None
    goal_context: str = ""

    @classmethod
    def for_missing_kind(cls, action_kind: str, *, goal: str = "",
                         flow_tags: frozenset[str] = frozenset()) -> "ScaffoldSpec":
        return cls(action_kind=action_kind,
                   class_name=f"{_camel(action_kind)}Handler",
                   summary=f"Handler for the {action_kind!r} action kind.",
                   flow_tags=flow_tags, goal_context=goal)

    @classmethod
    def variant(cls, base: Capability, *, variant_suffix: str,
                flow_tags: frozenset[str], goal: str = "") -> "ScaffoldSpec":
        cls_name = f"{_camel(base.action_kind)}{_camel(variant_suffix)}Handler"
        return cls(action_kind=base.action_kind, class_name=cls_name,
                   summary=f"{variant_suffix} variant of {base.name} for a specific flow.",
                   flow_tags=flow_tags, variant_of=base.name, goal_context=goal)

    @property
    def filename(self) -> str:
        # e.g. timer_schedule__proposed.py  or  shell__cadence_variant.py
        tag = "variant" if self.variant_of else "proposed"
        return f"{self.action_kind}__{tag}.py"

    def render(self) -> str:
        """A self-documenting handler stub. Its __call__ returns a *blocked*
        outcome until a human implements it, so even if it were registered by
        mistake it would do nothing — it can never silently act."""
        tags = ", ".join(sorted(self.flow_tags)) or "(none yet)"
        variant_line = (f"    Variant of: {self.variant_of}\n"
                        if self.variant_of else "")
        return f'''"""
PROPOSED SUBSYSTEM — NOT ACTIVE.

{self.summary}

    action_kind : {self.action_kind!r}
    flow tags   : {tags}
{variant_line}    drafted for goal: {self.goal_context!r}

This file was drafted by Aria's gap analyzer. It is a starting point, not a
working handler. To bring it to life:
  1. Implement the body of __call__ (parse task.description's JSON for
     action_input; do the work; return a StepOutcome).
  2. Move this file into  src/sovereign_agent/workflow/handlers/.
  3. Register it where the loop is built:
       loop.register_tool_handler({self.action_kind!r}, {self.class_name}(...))
  4. Add it to the capability catalog so the router knows its flows.

Until step 3 happens, this subsystem does not exist as far as the loop is
concerned — by design.
"""
from __future__ import annotations

import json

from sovereign_agent.workflow.agentic_loop import StepOutcome
from sovereign_agent.persistence.projects import Task


class {self.class_name}:
    """Proposed handler for {self.action_kind!r}. Implement __call__."""

    def __call__(self, task: Task) -> StepOutcome:
        # action_input rides along in the task description as JSON.
        try:
            spec = json.loads(task.description or "{{}}")
            action_input = spec.get("action_input", {{}})
        except Exception:  # noqa: BLE001
            action_input = {{}}

        # TODO(human): implement {self.action_kind!r}. Until then, refuse safely.
        return StepOutcome(
            succeeded=False,
            summary="{self.action_kind} handler is a scaffold — not implemented",
            error="awaiting human implementation",
            extra={{"action_input": action_input, "proposed": True}},
        )
'''

    def write_proposal(self, proposals_root: Path) -> Path:
        """Write the stub under proposals_root (NOT the package). Returns path."""
        proposals_root.mkdir(parents=True, exist_ok=True)
        dest = proposals_root / self.filename
        dest.write_text(self.render(), encoding="utf-8")
        return dest


# ─── Gap analysis ──────────────────────────────────────────────────────────


@dataclass
class GapReport:
    needed: list[str] = field(default_factory=list)
    available: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    proposals: list[ScaffoldSpec] = field(default_factory=list)

    @property
    def has_gaps(self) -> bool:
        return bool(self.missing)

    def summary_text(self) -> str:
        if not self.needed:
            return "This goal needs no special subsystems."
        parts = [f"needs: {', '.join(self.needed)}"]
        if self.available:
            parts.append(f"have: {', '.join(self.available)}")
        if self.missing:
            parts.append(f"missing: {', '.join(self.missing)}")
        return "; ".join(parts)


def analyze_gaps(steps: list[PlanStep], registry: CapabilityRegistry, *,
                 goal: str = "") -> GapReport:
    """Compare what a plan needs against what Aria has. Builds scaffold
    proposals for anything missing. Pure analysis — no side effects."""
    seen: list[str] = []
    for s in steps:
        if s.action_kind not in seen:
            seen.append(s.action_kind)
    available_kinds = registry.available_kinds()
    available = [k for k in seen if k in available_kinds]
    missing = [k for k in seen if k not in available_kinds]
    proposals = [
        ScaffoldSpec.for_missing_kind(
            k, goal=goal,
            flow_tags=frozenset().union(
                *[c.flow_tags for c in registry.by_action_kind(k)] or [frozenset()]),
        )
        for k in missing
    ]
    return GapReport(needed=seen, available=available, missing=missing,
                     proposals=proposals)


# ─── Authority policy ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class AuthorityDecision:
    requires_human: bool
    self_answerable: bool
    reason: str


class AuthorityPolicy:
    """Explicit, tunable rules for when Aria may act on her own judgment.

    The two hard lines:
      • Anything that modifies Aria's own code/config ALWAYS needs a human —
        even in --yes mode. There is no flag to bypass this.
      • Consequential / irreversible action kinds need a human by default;
        the command layer may batch-approve task steps, but not self-mods.

    Reversible, read-only, internal decisions are self-answerable.
    """
    # Kinds whose effects are not trivially reversible.
    CONSEQUENTIAL_KINDS: frozenset[str] = frozenset({"shell", "file_write"})
    # Kinds that are read-only or trivially reversible.
    REVERSIBLE_KINDS: frozenset[str] = frozenset({"note", "file_read"})

    def assess(self, action_kind: str, *, modifies_self: bool = False) -> AuthorityDecision:
        if modifies_self:
            return AuthorityDecision(
                requires_human=True, self_answerable=False,
                reason="changes to Aria's own code or configuration always need your review")
        if action_kind in self.REVERSIBLE_KINDS:
            return AuthorityDecision(
                requires_human=False, self_answerable=True,
                reason=f"{action_kind} is read-only or trivially reversible")
        if action_kind in self.CONSEQUENTIAL_KINDS:
            return AuthorityDecision(
                requires_human=True, self_answerable=False,
                reason=f"{action_kind} has side effects that aren't trivially undone")
        # Unknown kind → be conservative.
        return AuthorityDecision(
            requires_human=True, self_answerable=False,
            reason=f"{action_kind!r} is unclassified; defaulting to your review")


# Heuristic: does a step touch Aria's own code/config? The FileWriteHandler is
# already sandboxed to the sandbox root, so a self-targeting write is blocked
# there too — this is an extra, explicit guard at the planning layer.
def looks_self_modifying(step: PlanStep, *, self_roots: list[Path]) -> bool:
    blob = (str(step.action_input) + " " + step.title + " " + step.description).lower()
    for root in self_roots:
        if str(root).lower() in blob:
            return True
    # Common self-reference tokens even without an absolute path.
    return any(tok in blob for tok in (
        "sovereign_agent", "src/sovereign", "aria_values.yaml", "pyproject.toml"))


__all__ = [
    "Capability", "CapabilityStatus", "DEFAULT_CATALOG", "CapabilityRegistry",
    "RankedVariant", "VariantRouter",
    "ScaffoldSpec", "GapReport", "analyze_gaps",
    "AuthorityDecision", "AuthorityPolicy", "looks_self_modifying",
]
