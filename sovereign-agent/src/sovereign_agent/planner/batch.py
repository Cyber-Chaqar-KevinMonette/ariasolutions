"""
planner/batch.py — two-pass plan-then-execute for N-item batches.

API contract:

    planner = BatchPlanner(
        analyze=lambda item: ItemPlan(...),       # phase 1: per-item
        synthesize=lambda plans: CrossCuttingPlan,# phase 2: cross-cutting
        execute=lambda item, plan: ExecutionResult, # phase 3: per-item act
    )
    report = planner.run(items)

Each phase is the caller's choice — the planner is structure, not policy.
The defaults for ``synthesize`` find: duplicates (same content hash),
strong tags shared across items, and explicit dependencies declared in
the per-item plans (an ItemPlan can list ``depends_on`` ids).

The synthesized order respects dependencies. Within a dependency band,
items are grouped by shared tags so similar work runs in cache locality.
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Iterable, TypeVar


ItemT = TypeVar("ItemT")
PlanT = TypeVar("PlanT")


@dataclass
class ItemPlan:
    """The per-item plan written in phase 1.

    Fields are intentionally generic — the planner does not interpret
    ``payload``; it only uses ``item_id``, ``depends_on``, ``tags``,
    ``content_fingerprint``, and ``cost_estimate`` for synthesis.
    """
    item_id: str
    summary: str                                 # one-line description
    strategy: str = ""                           # how to handle this item
    tags: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)   # other item_ids
    content_fingerprint: str = ""                # for dedup detection
    cost_estimate: float = 1.0                   # relative cost (caller's units)
    payload: dict[str, Any] = field(default_factory=dict)
    skip: bool = False                           # phase 1 may decide to skip
    skip_reason: str = ""

    def render(self) -> str:
        head = f"{self.item_id}  {self.summary}"
        bits = []
        if self.tags:
            bits.append("tags=" + ",".join(self.tags))
        if self.depends_on:
            bits.append("depends_on=" + ",".join(self.depends_on))
        if self.skip:
            bits.append(f"SKIP: {self.skip_reason}")
        tail = "  ".join(bits)
        return f"{head}   {tail}" if tail else head


@dataclass
class CrossCuttingPlan:
    """Phase 2 output. Describes the batch as a whole."""
    ordered_item_ids: list[str]                  # execution order
    duplicate_groups: list[list[str]] = field(default_factory=list)
    tag_clusters: dict[str, list[str]] = field(default_factory=dict)
    dependency_chains: list[list[str]] = field(default_factory=list)
    estimated_total_cost: float = 0.0
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"cross-cutting plan · {len(self.ordered_item_ids)} item(s) · "
            f"est. cost {self.estimated_total_cost:.1f}",
        ]
        if self.duplicate_groups:
            lines.append(f"  duplicate groups: {len(self.duplicate_groups)}")
            for g in self.duplicate_groups[:5]:
                lines.append(f"    · {g}")
        if self.dependency_chains:
            lines.append(f"  dependency chains: {len(self.dependency_chains)}")
            for c in self.dependency_chains[:5]:
                lines.append(f"    · {' → '.join(c)}")
        if self.tag_clusters:
            lines.append(f"  tag clusters: {len(self.tag_clusters)}")
            top = sorted(self.tag_clusters, key=lambda k: -len(self.tag_clusters[k]))[:5]
            for t in top:
                lines.append(f"    · {t}: {len(self.tag_clusters[t])} items")
        if self.notes:
            lines.append("  notes:")
            for n in self.notes:
                lines.append(f"    · {n}")
        return "\n".join(lines)


@dataclass
class ExecutionResult:
    """Phase 3 output for one item."""
    item_id: str
    success: bool
    duration_s: float
    output: Any = None
    error: str | None = None
    notes: str = ""


@dataclass
class BatchReport:
    """End-to-end record of one batch run."""
    item_plans: list[ItemPlan] = field(default_factory=list)
    cross_cutting: CrossCuttingPlan | None = None
    results: list[ExecutionResult] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    total_duration_s: float = 0.0

    @property
    def total(self) -> int:
        return len(self.item_plans)

    @property
    def executed(self) -> int:
        return len(self.results)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.success)

    @property
    def skipped(self) -> int:
        return sum(1 for p in self.item_plans if p.skip)

    def render(self) -> str:
        lines = [
            "batch report",
            "─" * 40,
            f"  items planned:  {self.total}",
            f"  skipped:        {self.skipped}",
            f"  executed:       {self.executed}",
            f"  succeeded:      {self.succeeded}",
            f"  failed:         {self.failed}",
            f"  duration:       {self.total_duration_s:.2f}s",
        ]
        if self.cross_cutting:
            lines.append("")
            lines.append(self.cross_cutting.render())
        if self.failed:
            lines.append("")
            lines.append("failures:")
            for r in self.results:
                if not r.success:
                    lines.append(f"  · {r.item_id}: {r.error or '(no error message)'}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "total": self.total, "executed": self.executed,
            "succeeded": self.succeeded, "failed": self.failed,
            "skipped": self.skipped,
            "duration_s": round(self.total_duration_s, 3),
            "started_at": self.started_at, "finished_at": self.finished_at,
            "results": [
                {"item_id": r.item_id, "success": r.success,
                 "duration_s": round(r.duration_s, 3), "error": r.error,
                 "notes": r.notes}
                for r in self.results
            ],
        }


# ─── Default cross-cutting synthesizer ────────────────────────────────────


def _default_synthesize(plans: list[ItemPlan]) -> CrossCuttingPlan:
    """Find duplicates, tag clusters, dependency chains; order accordingly.

    Order rules:
      1. Topological sort by ``depends_on``. Cycles → break by first-id wins.
      2. Within a topo band, group by primary tag (first tag in tags list)
         for cache locality.
      3. Skip items keep their original index but are filtered from execute.
    """
    by_id = {p.item_id: p for p in plans}

    # Duplicate detection by content_fingerprint
    fp_groups: dict[str, list[str]] = defaultdict(list)
    for p in plans:
        if p.content_fingerprint:
            fp_groups[p.content_fingerprint].append(p.item_id)
    duplicates = [ids for ids in fp_groups.values() if len(ids) > 1]

    # Tag clusters
    tag_clusters: dict[str, list[str]] = defaultdict(list)
    for p in plans:
        for t in p.tags:
            tag_clusters[t].append(p.item_id)

    # Topological sort with cycle break
    remaining = {p.item_id: set(p.depends_on) & set(by_id.keys()) for p in plans}
    ordered: list[str] = []
    bands: list[list[str]] = []
    guard = 0
    while remaining:
        ready = [iid for iid, deps in remaining.items() if not deps]
        if not ready:
            # Cycle: take first remaining id, break the dep
            stuck = sorted(remaining.keys())[0]
            remaining[stuck] = set()
            ready = [stuck]
        # Group ready items by primary tag for locality
        ready_by_tag: dict[str, list[str]] = defaultdict(list)
        for iid in ready:
            primary = by_id[iid].tags[0] if by_id[iid].tags else ""
            ready_by_tag[primary].append(iid)
        band = []
        for tag in sorted(ready_by_tag.keys()):
            band.extend(sorted(ready_by_tag[tag]))
        bands.append(band)
        for iid in band:
            ordered.append(iid)
            del remaining[iid]
            for deps in remaining.values():
                deps.discard(iid)
        guard += 1
        if guard > len(plans) + 5:
            break

    # Surface dependency chains as the longest paths through depends_on
    chains: list[list[str]] = []
    for p in plans:
        if p.depends_on:
            chains.append(p.depends_on + [p.item_id])

    notes: list[str] = []
    if duplicates:
        notes.append(f"{len(duplicates)} group(s) of duplicates — "
                     "consider shared cache for repeated work")
    if any(p.skip for p in plans):
        notes.append("some items marked skip in phase 1 — they will not execute")

    return CrossCuttingPlan(
        ordered_item_ids=ordered,
        duplicate_groups=duplicates,
        tag_clusters=dict(tag_clusters),
        dependency_chains=chains,
        estimated_total_cost=sum(p.cost_estimate for p in plans if not p.skip),
        notes=notes,
    )


# ─── Planner ──────────────────────────────────────────────────────────────


@dataclass
class BatchPlanner(Generic[ItemT]):
    """Two-pass plan/execute for a sequence of items.

    The callers supply:
      * ``analyze(item)`` -> ItemPlan          — phase 1 (per-item)
      * ``synthesize(plans)`` -> CrossCuttingPlan — phase 2 (optional; default provided)
      * ``execute(item, plan)`` -> ExecutionResult — phase 3 (per-item)

    The planner enforces the structure: phase 1 runs to completion before
    phase 2 begins, and phase 2 completes before phase 3 begins. Phase 3
    runs in the order returned by phase 2.
    """
    analyze: Callable[[Any], ItemPlan]
    execute: Callable[[Any, ItemPlan], ExecutionResult]
    synthesize: Callable[[list[ItemPlan]], CrossCuttingPlan] = None  # type: ignore
    stop_on_failure: bool = False

    def __post_init__(self):
        if self.synthesize is None:
            self.synthesize = _default_synthesize

    def run(self, items: Iterable[ItemT]) -> BatchReport:
        from datetime import datetime, timezone
        items = list(items)
        report = BatchReport(started_at=datetime.now(timezone.utc).isoformat())
        t0 = time.monotonic()

        # Phase 1 — read all, plan each
        item_by_id: dict[str, ItemT] = {}
        for it in items:
            plan = self.analyze(it)
            report.item_plans.append(plan)
            item_by_id[plan.item_id] = it

        # Phase 2 — synthesize across all plans
        report.cross_cutting = self.synthesize(report.item_plans)

        # Phase 3 — execute in synthesized order, skipping items flagged skip
        plan_by_id = {p.item_id: p for p in report.item_plans}
        for iid in report.cross_cutting.ordered_item_ids:
            plan = plan_by_id[iid]
            if plan.skip:
                continue
            t_start = time.monotonic()
            try:
                result = self.execute(item_by_id[iid], plan)
            except Exception as e:
                result = ExecutionResult(
                    item_id=iid, success=False,
                    duration_s=time.monotonic() - t_start,
                    error=f"{type(e).__name__}: {e}",
                )
            # If the execute fn forgot to set duration, fill it in
            if result.duration_s == 0:
                object.__setattr__(result, "duration_s", time.monotonic() - t_start) \
                    if hasattr(result, "__dataclass_fields__") else None
            report.results.append(result)
            if not result.success and self.stop_on_failure:
                break

        report.total_duration_s = time.monotonic() - t0
        report.finished_at = datetime.now(timezone.utc).isoformat()
        return report


# ─── Convenience: fingerprint helpers ─────────────────────────────────────


def fingerprint_text(s: str) -> str:
    """Stable content fingerprint for dedup detection."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def fingerprint_path(p) -> str:
    """Fingerprint a file by its content. Returns empty on read failure."""
    try:
        from pathlib import Path
        return fingerprint_text(Path(p).read_text(errors="replace"))
    except OSError:
        return ""
