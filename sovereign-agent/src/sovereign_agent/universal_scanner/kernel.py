"""kernel.py — the Universal Scanner Kernel.

A single pre-flight gate any risky operation can pass through, before whatever domain-specific
checks apply. Composes what already exists — it does NOT replace or duplicate any sentinel or
scanner. Two layers:

  1. kernel_check(op)  — 8 cheap, hard-coded, in-process checks against Aria's actual kernel
     (Safety/Love/Flourishing, the deferred-unsafe boundary, authority tiers, consent, provenance,
     reversibility, signal-vs-ego). No I/O, no sentinel calls — this layer is fast enough to run on
     every turn.
  2. run(op)  — kernel_check() first, then fans out to whichever domain plugins apply: every
     registered sentinel (via stewardship.registry.scan_all) and, when the operation names a staged
     module, the path sentinel (path_scan.scan_one). Reduces every verdict to one, worst-wins.

Nothing here is a new authority. It is the composition layer over sentinels/scanners that already
exist — mirroring stewardship/base.py's own fractal principle (CHARTER -> MANIFEST -> CATALOG ->
ATOM), one level up: KERNEL -> PLUGIN VERDICTS -> ONE VERDICT.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Verdict = Literal["PASS", "SOFT_FAIL_RETRY", "HARD_FAIL_BLOCK"]

_VERDICT_RANK: dict[Verdict, int] = {"PASS": 0, "SOFT_FAIL_RETRY": 1, "HARD_FAIL_BLOCK": 2}


def _worse(a: Verdict, b: Verdict) -> Verdict:
    return a if _VERDICT_RANK[a] >= _VERDICT_RANK[b] else b


# ─── the operation being described ─────────────────────────────────────────


@dataclass
class OperationDescriptor:
    """A plain description of a proposed operation — who, what, where, when, intent,
    domain, tools, declared risk. Not a new subsystem: just the fixed shape every
    check below reads from."""

    who: str                                    # actor: "Kevin" | "Claude" | "Aria"
    what: str                                    # short description of the action
    intent: str = ""                             # why — the fuller reasoning/goal text
    domain: str = ""                              # "cockpit" | "workflow" | "module:<slug>" | ...
    tools: tuple[str, ...] = ()                   # tool names this operation would invoke
    when: str = ""                                # ISO timestamp; empty = "now", filled by caller
    declared_risk: str = ""                       # operator/model's own risk self-assessment
    reversible: bool | None = None                # None = undeclared (flagged, not blocked)
    requires_consent: bool = False                # True for operations touching a real person
    consent_given: bool = False


# ─── the verdict ────────────────────────────────────────────────────────────


@dataclass
class KernelVerdict:
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)
    plugin_results: dict[str, object] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return self.verdict == "HARD_FAIL_BLOCK"

    def summary(self) -> str:
        head = f"{self.verdict}"
        if self.reasons:
            head += " — " + "; ".join(self.reasons)
        return head


# ─── layer 1: the 8 hard-coded kernel checks (cheap, no I/O) ───────────────


# Representative paraphrase triggers per DEFERRED_UNSAFE key. The catalog's own
# key/label text ("recursive_self_rewriting") is precise but narrow — operators and
# models describe the same forbidden thing in plain language ("rewrite my own
# code"), so this table catches common phrasings without trying to be exhaustive
# NLU. False negatives here are safer than false positives on a HARD_FAIL_BLOCK
# gate; anything genuinely ambiguous should still be caught by a human reviewer.
_DEFERRED_UNSAFE_TRIGGERS: dict[str, tuple[str, ...]] = {
    "recursive_self_rewriting": (
        "rewrite my own code", "rewrite its own code", "rewrite itself",
        "self-modify", "self modify", "edit my own source", "modify my own architecture",
        "recursive self-rewriting", "recursive self rewriting",
    ),
    "value_self_authorship": (
        "rewrite my own values", "change my own ethics", "author my own values",
        "mutate my values", "value self-authorship", "value self authorship",
    ),
    "autonomous_goal_generation": (
        "set my own goal", "generate my own goals", "autonomous goal generation",
        "goals beyond oversight", "decide my own objectives without approval",
    ),
    "unbounded_recursive_improvement": (
        "improve myself without limit", "unbounded self-improvement",
        "unbounded recursive improvement", "no cap on self-improvement",
    ),
    "substrate_independence": (
        "migrate myself to", "run on different hardware autonomously",
        "substrate independence", "escape this machine",
    ),
}


def _check_deferred_unsafe(op: OperationDescriptor) -> tuple[Verdict, list[str]]:
    """Kernel §1: no self-rewriting, no value self-authorship, no autonomous goal
    generation, no unbounded self-improvement, no substrate independence."""
    from sovereign_agent.self_development import DEFERRED_UNSAFE

    text = f"{op.what} {op.intent}".lower()
    labels_by_key = {c.key: c.label for c in DEFERRED_UNSAFE}
    hits = [
        labels_by_key[key]
        for key, triggers in _DEFERRED_UNSAFE_TRIGGERS.items()
        if key in labels_by_key and any(t in text for t in triggers)
    ]
    if hits:
        return "HARD_FAIL_BLOCK", [f"deferred-unsafe boundary: {h}" for h in hits]
    return "PASS", []


def _check_authority_tiers(op: OperationDescriptor) -> tuple[Verdict, list[str]]:
    """Kernel §2: every declared tool must be registered, and Tier-3 tools must
    require approval — the same invariant authority.py enforces at registration,
    checked again here at the operation level."""
    if not op.tools:
        return "PASS", []
    from sovereign_agent.authority import get_tool_meta

    reasons: list[str] = []
    verdict: Verdict = "PASS"
    for name in op.tools:
        try:
            meta = get_tool_meta(name)
        except KeyError:
            verdict = _worse(verdict, "SOFT_FAIL_RETRY")
            reasons.append(f"tool {name!r} not found in the authority tier registry")
            continue
        if meta.tier == 3 and not meta.requires_approval:
            verdict = "HARD_FAIL_BLOCK"
            reasons.append(f"tool {name!r} is Tier 3 without requires_approval")
    return verdict, reasons


def _check_consent(op: OperationDescriptor) -> tuple[Verdict, list[str]]:
    """Kernel §3: an operation that touches a real person must have recorded consent."""
    if op.requires_consent and not op.consent_given:
        return "HARD_FAIL_BLOCK", ["operation requires consent but none is recorded"]
    return "PASS", []


def _check_provenance(op: OperationDescriptor) -> tuple[Verdict, list[str]]:
    """Kernel §4: every operation names an actor — the minimum for the audit trail
    (mirrors diagnosis.py's own invariant: every conflict names an actor)."""
    if not op.who or not op.who.strip():
        return "SOFT_FAIL_RETRY", ["operation has no named actor (who)"]
    return "PASS", []


def _check_reversibility_declared(op: OperationDescriptor) -> tuple[Verdict, list[str]]:
    """Kernel §5: reversibility should be declared, not left implicit. Undeclared is
    a warn (retry with the field filled in), not a block — plenty of operations are
    genuinely reversible without anyone having said so yet."""
    if op.reversible is None:
        return "SOFT_FAIL_RETRY", ["reversibility not declared (reversible=None)"]
    return "PASS", []


def _check_signal_vs_ego(op: OperationDescriptor) -> tuple[Verdict, list[str]]:
    """Kernel §6 — MOS canon's Signal Check, as a light, informational heuristic
    only: never blocks, just surfaces language that suggests a fear-/urgency-driven
    decision so the human can pause a beat. This is a nudge, not a verdict."""
    text = f"{op.what} {op.intent}".lower()
    urgency_markers = ("right now", "immediately", "no time", "hurry", "asap", "before it's too late")
    hits = [m for m in urgency_markers if m in text]
    if hits:
        return "PASS", [f"signal check: urgency language detected ({hits[0]!r}) — informational only"]
    return "PASS", []


def _check_domain_declared(op: OperationDescriptor) -> tuple[Verdict, list[str]]:
    """Kernel §7: an operation should say what domain it's in, so fan-out (layer 2)
    knows which plugins to consult. Missing domain doesn't block — it just means
    layer 2 has less to fan out to."""
    if not op.domain:
        return "SOFT_FAIL_RETRY", ["no domain declared — plugin fan-out will be sentinel-only"]
    return "PASS", []


def _check_what_present(op: OperationDescriptor) -> tuple[Verdict, list[str]]:
    """Kernel §8: an operation must describe itself. An empty description can't be
    checked by anything downstream, so it fails closed."""
    if not op.what or not op.what.strip():
        return "HARD_FAIL_BLOCK", ["operation has no description (what)"]
    return "PASS", []


_KERNEL_CHECKS = (
    _check_what_present,
    _check_deferred_unsafe,
    _check_authority_tiers,
    _check_consent,
    _check_provenance,
    _check_reversibility_declared,
    _check_signal_vs_ego,
    _check_domain_declared,
)


def kernel_check(op: OperationDescriptor) -> KernelVerdict:
    """Run all 8 hard-coded kernel checks. Fast, no I/O, no sentinel calls."""
    verdict: Verdict = "PASS"
    reasons: list[str] = []
    for check in _KERNEL_CHECKS:
        v, r = check(op)
        verdict = _worse(verdict, v)
        reasons.extend(r)
    return KernelVerdict(verdict=verdict, reasons=reasons)


# ─── layer 2: fan-out to domain plugins ─────────────────────────────────────


def run(op: OperationDescriptor, *, data_dir: Path | None = None, repo_root: Path | None = None) -> KernelVerdict:
    """kernel_check(op) first; if it doesn't already HARD_FAIL_BLOCK, fan out to
    every registered sentinel (stewardship.registry.scan_all) and, when the
    operation names a staged module (domain == "module:<slug>"), the path
    sentinel too. Reduces every verdict to one, worst-wins."""
    result = kernel_check(op)
    plugin_results: dict[str, object] = {}

    if result.verdict == "HARD_FAIL_BLOCK":
        return result  # no point fanning out further

    # Sentinel fan-out
    if data_dir is not None:
        try:
            from sovereign_agent.stewardship.registry import scan_all

            reports = scan_all(data_dir)
            for report in reports:
                plugin_results[f"sentinel:{report.sentinel_id}"] = report
                if report.findings_count and report.findings_count > 0:
                    result.verdict = _worse(result.verdict, "SOFT_FAIL_RETRY")
        except Exception as exc:  # noqa: BLE001 — a plugin failing to run is a warn, not a crash
            result.reasons.append(f"sentinel fan-out unavailable: {exc!r}")

    # Path-sentinel fan-out, only when the op names a staged module
    if op.domain.startswith("module:") and repo_root is not None:
        slug = op.domain.removeprefix("module:")
        try:
            from sovereign_agent.path_scan import scan_one

            scan_result = scan_one(repo_root, f"aria-{slug}" if not slug.startswith("aria-") else slug)
            plugin_results["path_scan"] = scan_result
            if scan_result.blocks:
                result.verdict = "HARD_FAIL_BLOCK"
                result.reasons.append(f"path_scan found {len(scan_result.blocks)} blocking finding(s)")
            elif scan_result.warns:
                result.verdict = _worse(result.verdict, "SOFT_FAIL_RETRY")
        except Exception as exc:  # noqa: BLE001
            result.reasons.append(f"path_scan fan-out unavailable: {exc!r}")

    result.plugin_results = plugin_results
    return result
