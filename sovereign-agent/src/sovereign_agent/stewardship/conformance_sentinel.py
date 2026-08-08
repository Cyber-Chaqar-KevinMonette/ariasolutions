"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/conformance_sentinel.py — Conformance ("God Speed")        ║
║                                                                           ║
║  This sentinel exists because Kevin asked for two distinct things:      ║
║                                                                           ║
║    • A "Property Naming Enforcer" — prevents drift into vague, lazy,   ║
║      or inconsistent property names across the codebase.                 ║
║    • A "God Speed Standard Sentinel" — checks the system's work        ║
║      against the canonical standards (STANDARDS-CE-2026.05.24.md).      ║
║                                                                           ║
║  These are two faces of the same discipline: enforce the canon. So     ║
║  they live in one sentinel with one shared mechanism (a pluggable list ║
║  of named rules) and two surface checks (naming + standards).          ║
║                                                                           ║
║  How rules work                                                         ║
║                                                                           ║
║    A Rule is a small class with a name, a description, and an evaluate ║
║    method that returns a list of RuleViolation. Rules are pluggable —  ║
║    new rules go in conformance/rules/ and register themselves with the ║
║    sentinel. We ship a small starter set; the system grows over time.  ║
║                                                                           ║
║  Tier 1 discipline                                                       ║
║                                                                           ║
║    Conformance does not auto-fix. It proposes. Auto-fix on naming is   ║
║    exactly the kind of cleverness that breaks more than it fixes (the  ║
║    drift_value_sentinel philosophy applies: aggressive autofix has a   ║
║    high confusion cost). The operator (or, with a lease, the           ║
║    Conductor at R0 only) decides whether to apply.                      ║
║                                                                           ║
║  Catalog file: <data_dir>/sentinels/conformance/catalogs/violations.json║
║  Kill switch: SOV_NO_CONFORMANCE_SENTINEL=1                             ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from ulid import ULID

from sovereign_agent.aegis.incidents import (
    DamageReport,
    DryRunReport,
    Evidence,
    IncidentId,
    RepairPlan,
    RepairResult,
    RepairStep,
)
from sovereign_agent.aegis.leases import RepairLease
from sovereign_agent.aegis.medical import MedicalCapability
from sovereign_agent.aegis.radius import BlastRadius
from sovereign_agent.stewardship.base import (
    HealthStatus,
    Sentinel,
    SentinelReport,
)
from sovereign_agent.stewardship.registry import register_sentinel


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ─── Violation type ──────────────────────────────────────────────────────


@dataclass
class RuleViolation:
    rule_name: str
    severity: Literal["info", "warning", "alert"]
    surface: Literal["naming", "standards", "documentation", "test", "other"]
    summary: str
    detail: str = ""
    path: str = ""
    suggested_fix: str = ""


# ─── Rule base class ─────────────────────────────────────────────────────


class ConformanceRule(ABC):
    """A pluggable check. Subclass and add to DEFAULT_RULES below."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def surface(self) -> str: ...

    @abstractmethod
    def evaluate(self, repo_root: Path) -> list[RuleViolation]: ...


# ─── A small starter set of rules ────────────────────────────────────────


class NoVagueNameRule(ConformanceRule):
    """Flags variable/property names that fail the 'meaningful' test.

    Vague set is conservative on purpose: 'data', 'info', 'temp', 'thing',
    'obj', 'val'. Real codebases use these legitimately in narrow scopes
    (a `data` field in a dataclass is fine), so we only flag occurrences
    inside .py files at module level OR as standalone identifiers in a
    class body — never inside function locals.
    """

    name = "no-vague-name"
    description = "module-level identifiers should be specific, not vague"
    surface = "naming"

    VAGUE_NAMES = frozenset({"data", "info", "temp", "thing", "obj", "val", "x", "y", "stuff"})
    # Match top-level assignments: '<name> = ' or '<name>: ' at column 0
    RE = re.compile(r"^([a-z_][a-z0-9_]*)\s*[:=]", re.MULTILINE)

    def evaluate(self, repo_root: Path) -> list[RuleViolation]:
        out: list[RuleViolation] = []
        for py in repo_root.rglob("*.py"):
            if any(part in {".venv", "__pycache__", "build", "dist", "backups"}  # cockpit-hardening-d
                  for part in py.parts):
                continue
            try:
                text = py.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in self.RE.finditer(text):
                name = m.group(1)
                if name in self.VAGUE_NAMES:
                    out.append(RuleViolation(
                        rule_name=self.name,
                        severity="warning",
                        surface="naming",
                        summary=f"vague module-level identifier '{name}' in {py.name}",
                        detail=f"line context: {m.group(0)}",
                        path=str(py),
                        suggested_fix=f"rename '{name}' to something domain-specific",
                    ))
        return out


class ManifestArticlesRule(ConformanceRule):
    """STANDARDS canon §2: every Sentinel must declare ≥3 articles.

    A Sentinel with fewer than 3 articles hasn't articulated its self-
    constitution in enough depth. Three is the minimum for a meaningful
    contract (what I do / what I don't do / how I fail).
    """

    name = "manifest-articles-min"
    description = "every Sentinel must declare at least 3 articles"
    surface = "standards"

    def evaluate(self, repo_root: Path) -> list[RuleViolation]:
        out: list[RuleViolation] = []
        # Walk sentinel manifests in the data dir if we can reach it; otherwise
        # this is a static-analysis rule walking *_sentinel.py for articles() bodies.
        for py in repo_root.rglob("*_sentinel.py"):
            try:
                text = py.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            # Find the articles() method body and count list elements (rough heuristic).
            m = re.search(
                r"def articles\(self\)[^\n]*:\s*\n\s*return \[(.*?)\]",
                text, re.DOTALL,
            )
            if not m:
                continue
            body = m.group(1)
            # Count quoted strings (single or double, including triple-quoted).
            article_count = len(re.findall(r"['\"][^'\"]*['\"]", body))
            if article_count < 3:
                out.append(RuleViolation(
                    rule_name=self.name,
                    severity="warning",
                    surface="standards",
                    summary=f"{py.name} declares only {article_count} article(s); "
                            f"STANDARDS canon §2 requires ≥3",
                    path=str(py),
                    suggested_fix="add articles for (a) what the sentinel does, "
                                  "(b) what it refuses, and (c) how it fails honestly",
                ))
        return out


class KillSwitchDocumentedRule(ConformanceRule):
    """STANDARDS canon §4: every Sentinel must document its kill switch."""

    name = "kill-switch-documented"
    description = "every Sentinel module must mention its kill switch env var"
    surface = "documentation"

    def evaluate(self, repo_root: Path) -> list[RuleViolation]:
        out: list[RuleViolation] = []
        # bloodwork-d: scope to the LIVE tree and skip test files. Staged
        # aria-*/ copies get conformance-checked when they become live;
        # test files are not sentinels. Falls back to repo_root when no
        # src/ exists (synthetic test dirs).
        search_root = repo_root / "src" if (repo_root / "src").is_dir() else repo_root
        for py in search_root.rglob("*_sentinel.py"):
            if py.name.startswith("test_"):
                continue
            try:
                text = py.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "SOV_NO_" not in text:
                out.append(RuleViolation(
                    rule_name=self.name,
                    severity="warning",
                    surface="documentation",
                    summary=f"{py.name} does not mention its kill switch env var",
                    path=str(py),
                    suggested_fix=f"add 'Kill switch: SOV_NO_<ID>_SENTINEL=1' to module docstring",
                ))
        return out


DEFAULT_RULES: list[ConformanceRule] = [
    NoVagueNameRule(),
    ManifestArticlesRule(),
    KillSwitchDocumentedRule(),
]


# ─── The Sentinel ────────────────────────────────────────────────────────


@register_sentinel
class ConformanceSentinel(Sentinel, MedicalCapability):
    """Enforces the canon. Naming + standards in one place.

    Construct optionally with `rules=None` to use DEFAULT_RULES; pass a
    custom list for tests or for the operator who wants to extend.
    """

    def __init__(self, data_dir: Path, rules: list[ConformanceRule] | None = None,
                 repo_root: Path | None = None):
        super().__init__(data_dir)
        self._rules = rules or list(DEFAULT_RULES)
        # Default repo_root is the parent of data_dir's grandparent if it
        # contains 'sovereign-agent', else just cwd. Configurable in tests.
        self._repo_root = repo_root or Path.cwd()

    @property
    def id(self) -> str:
        return "conformance"

    @property
    def title(self) -> str:
        return "Conformance — naming discipline + standards adherence"

    @property
    def tier(self) -> int:
        return 1

    @property
    def voice_persona(self) -> str:
        return ("crisp, specific, generous with the fix — never punitive. "
                "Names the rule, explains why it matters, suggests the fix.")

    def articles(self) -> list[str]:
        return [
            "I. I check the codebase against the canonical STANDARDS document "
            "(STANDARDS-CE-2026.05.24.md). Each rule maps to a named canon clause.",
            "II. I cover both naming discipline (no vague property names, "
            "consistent schemas) and structural standards (sentinel manifest "
            "completeness, kill switch documentation, article minimums).",
            "III. I propose fixes — I never auto-apply them. Naming auto-fix is "
            "exactly the cleverness that breaks more than it fixes.",
            "IV. New rules are pluggable. Adding a rule does not require modifying "
            "this Sentinel; it requires writing a ConformanceRule subclass and "
            "registering it in DEFAULT_RULES (or passing it at construction).",
            "V. I report violations as DamageReports when severity is alert. "
            "Warning-level violations stay in the catalog for operator review.",
            "VI. When the canon changes, I expect the rules to be updated. A rule "
            "without a canon clause is a rule without authority.",
        ]

    # ─── Scan ───────────────────────────────────────────────────────────

    def scan(self) -> SentinelReport:
        violations: list[RuleViolation] = []
        for rule in self._rules:
            try:
                violations.extend(rule.evaluate(self._repo_root))
            except Exception as e:
                violations.append(RuleViolation(
                    rule_name=rule.name,
                    severity="warning",
                    surface="other",
                    summary=f"rule '{rule.name}' raised: {type(e).__name__}",
                    detail=str(e),
                ))

        cat_dir = self.sentinel_dir / "catalogs"
        cat_dir.mkdir(parents=True, exist_ok=True)
        cat_path = cat_dir / "violations.json"
        blob = {
            "written_at": _iso_now(),
            "repo_root": str(self._repo_root),
            "rules_evaluated": [r.name for r in self._rules],
            "violations": [asdict(v) for v in violations],
        }
        tmp = cat_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(blob, indent=2, sort_keys=True), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, cat_path)

        alerts = sum(1 for v in violations if v.severity == "alert")
        warnings = sum(1 for v in violations if v.severity == "warning")

        return SentinelReport(
            sentinel_id=self.id,
            observed_at=_iso_now(),
            catalog_name="violations",
            findings_count=len(violations),
            summary=(
                f"evaluated {len(self._rules)} rule(s); "
                f"{alerts} alert / {warnings} warning / "
                f"{len(violations) - alerts - warnings} info"
            ),
            catalog_path=str(cat_path),
            details={
                "alerts": alerts, "warnings": warnings,
                "violations": [asdict(v) for v in violations[:50]],
            },
        )

    def health_status(self) -> HealthStatus:  # cockpit-hardening-d
        """Reads the last CACHED violations.json -- never re-scans fresh.
        Before this fix, health_status() called self.scan() (all 4 rules,
        each walking the whole repo with repo_root.rglob("*.py")) on EVERY
        call. gather_health() runs this every 5s in a background thread
        (cockpit/app.py's _refresh_status_worker) -- the same class of bug
        diagnosed live via py-spy in canon_embodiment/sentinel.py
        (2026-07-20), fixed here identically: only scan() (explicitly
        invoked, e.g. `sov sentinels scan`) does the expensive walk."""
        cat_path = self.sentinel_dir / "catalogs" / "violations.json"
        if not cat_path.is_file():
            return HealthStatus(
                sentinel_id=self.id, level="ok",
                summary="not yet scanned — run `sov sentinels scan` for a first pass",
                observed_at=_iso_now(),
            )
        try:
            blob = json.loads(cat_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return HealthStatus(
                sentinel_id=self.id, level="ok",
                summary="cached catalog unreadable — run `sov sentinels scan`",
                observed_at=_iso_now(),
            )
        violations = blob.get("violations", [])
        alerts = sum(1 for v in violations if v.get("severity") == "alert")
        warnings = sum(1 for v in violations if v.get("severity") == "warning")
        if alerts:
            level = "error"
            summary = f"{alerts} alert-level conformance violations"
        elif warnings:
            level = "warning"
            summary = f"{warnings} warning-level conformance violations"
        else:
            level = "ok"
            summary = "no conformance violations"
        return HealthStatus(
            sentinel_id=self.id, level=level, summary=summary,
            observed_at=_iso_now(),
        )

    # ─── MedicalCapability ──────────────────────────────────────────────

    def damage_estimate(self) -> DamageReport:
        report = self.scan()
        alerts = [v for v in report.details.get("violations", [])
                  if v.get("severity") == "alert"]
        if not alerts:
            return DamageReport(
                incident_id=IncidentId(str(ULID())),
                sentinel_id=self.id,
                radius=BlastRadius.R0_ARTIFACT,
                severity="info",
                confidence=0.9,
                summary="no alert-level conformance violations",
            )
        return DamageReport(
            incident_id=IncidentId(str(ULID())),
            sentinel_id=self.id,
            radius=BlastRadius.R1_SURFACE,
            severity="alert",
            confidence=0.85,
            summary=f"{len(alerts)} alert-level conformance violation(s)",
            evidence=[
                Evidence(
                    kind="other",
                    summary=v.get("summary", ""),
                    detail=v.get("detail", ""),
                    source_path=v.get("path", ""),
                )
                for v in alerts[:30]
            ],
            affected_paths=[v.get("path", "") for v in alerts if v.get("path")],
        )

    def repair_plan(self, damage: DamageReport) -> RepairPlan:
        return RepairPlan(
            incident_id=damage.incident_id,
            sentinel_id=self.id,
            radius=damage.radius,
            summary="conformance violations require human judgment; "
                    "Conformance proposes, operator decides",
            steps=[
                RepairStep(
                    ordinal=i,
                    description=ev.summary,
                    action_kind="operator-action-required",
                    target_path=ev.source_path,
                    reversible=True,
                )
                for i, ev in enumerate(damage.evidence, start=1)
            ],
        )

    def repair_dry_run(self, plan: RepairPlan) -> DryRunReport:
        return DryRunReport(
            incident_id=plan.incident_id,
            plan_hash=plan.plan_hash(),
            sentinel_id=self.id,
            would_succeed=True,
            would_modify=[], would_create=[], would_delete=[],
            opaque_steps=[s.ordinal for s in plan.steps],
            warnings=["Conformance never auto-fixes; all steps are operator-action-required"],
        )

    def _execute_repair_internal(
        self,
        plan: RepairPlan,
        lease: RepairLease | None,
    ) -> RepairResult:
        return RepairResult(
            incident_id=plan.incident_id,
            lease_id=lease.lease_id if lease else "",  # type: ignore[arg-type]
            sentinel_id=self.id,
            plan_hash=plan.plan_hash(),
            succeeded=True,
            steps_completed=[],
            steps_failed=[],
            paths_actually_modified=[],
            paths_actually_created=[],
            paths_actually_deleted=[],
            error_summary="Conformance delegates fixes to the operator; no action taken",
        )


__all__ = [
    "ConformanceSentinel",
    "ConformanceRule",
    "RuleViolation",
    "NoVagueNameRule",
    "ManifestArticlesRule",
    "KillSwitchDocumentedRule",
    "DEFAULT_RULES",
]
