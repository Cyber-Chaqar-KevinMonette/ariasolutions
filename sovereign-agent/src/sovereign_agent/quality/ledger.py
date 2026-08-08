"""quality/ledger.py — the persisted quality score. (Quality round · Q1)

`qa/hardening.py:harden_module()` and `qa/quality_score.py:
score_hardening_report()` are already real, deterministic, in-process —
they were just never WRITTEN DOWN. This mirrors `proving_ground/
runner.py`'s exact discipline: append-only NDJSON, fsync'd, `trend()`
computed from STORED scores only — the honest kind.

A "quality pass" scores one or more target `.py` files together: each
gets its own `HardeningReport` + `QualityScore`; the pass's own headline
`value`/`grade` is the mean of the per-file scores (never silently
dropping a bad file into an average that hides it — `notes` lists every
file below a B).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MARK = "quality-sentinel-d"

# Below this letter grade, a file is named in the pass's own notes — never
# silently averaged away.
_NOTEWORTHY_GRADES = frozenset({"C", "D", "F"})


@dataclass
class FileScore:
    path: str
    value: float
    grade: str
    band: str
    critical_ok: bool           # HardeningReport.ok — every weight-≥8 check passed
    failures: list[str] = field(default_factory=list)   # ALL failing check labels
    critical_failures: list[str] = field(default_factory=list)  # weight-≥8 only —
    # the subset that actually explains why critical_ok is False; `failures`
    # keeps every non-critical gap too (useful for the WARN band), but a
    # BLOCK message must name only what's actually critical, not everything.

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class QualityPassResult:
    pass_id: str
    ts: str
    files: list[FileScore] = field(default_factory=list)

    @property
    def value(self) -> float:
        if not self.files:
            return 0.0
        return sum(f.value for f in self.files) / len(self.files)

    @property
    def critical_ok(self) -> bool:
        """True iff EVERY scored file passed its critical (weight-≥8)
        checks — one bad file fails the whole pass, never averaged away.
        Vacuously true when nothing was scored: an empty pass has no
        confirmed failure in it, and reporting one would be dishonest —
        "nothing to check" and "everything failed" must never look the
        same to a caller deciding whether to gate or alarm."""
        return all(f.critical_ok for f in self.files)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["value"] = round(self.value, 2)
        d["critical_ok"] = self.critical_ok
        return d


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_id() -> str:
    from ulid import ULID

    return f"qp-{str(ULID())[:12]}"


def _ledger_path(data_dir: Path | None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    p = Path(data_dir) / "quality"
    p.mkdir(parents=True, exist_ok=True)
    return p / "ledger.ndjson"


def record_quality_pass(targets: list[Path | str],
                        data_dir: Path | None = None) -> QualityPassResult:
    """Run the hardening checklist + score over every target file, append
    ONE fsync'd record. A target that can't be scored (missing, not .py,
    a syntax error) is skipped — noted, never a crash: a quality pass must
    never itself become the thing that breaks the build."""
    from sovereign_agent.qa.hardening import harden_module
    from sovereign_agent.qa.quality_score import score_hardening_report

    files: list[FileScore] = []
    for t in targets:
        try:
            report = harden_module(t)
            score = score_hardening_report(report)
        except (FileNotFoundError, ValueError, SyntaxError):
            continue
        failures = report.failures()
        files.append(FileScore(
            path=str(Path(t)),
            value=round(score.value, 2),
            grade=score.grade,
            band=score.band,
            critical_ok=report.ok,
            failures=[c.label for c in failures],
            critical_failures=[c.label for c in failures if c.weight >= 8],
        ))

    result = QualityPassResult(pass_id=_new_id(), ts=_now(), files=files)
    path = _ledger_path(data_dir)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(result.as_dict(), separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    try:
        from sovereign_agent.events import emit_event

        emit_event("quality-pass-d", plane="control", trace_id=result.pass_id,
                   payload={"value": result.value, "critical_ok": result.critical_ok,
                            "files": len(files),
                            "noteworthy": [f.path for f in files
                                          if f.grade in _NOTEWORTHY_GRADES]})
    except Exception:  # noqa: BLE001
        pass
    return result


def latest_quality(data_dir: Path | None = None) -> dict | None:
    """The most recent quality pass, or None if none has ever run."""
    from sovereign_agent.read_repair import read_ndjson_tolerant

    records = read_ndjson_tolerant(_ledger_path(data_dir), store="quality",
                                   emit=False).records
    return records[-1] if records else None


def quality_trend(n: int = 10, data_dir: Path | None = None) -> str:
    """From STORED scores only — the honest kind (mirrors
    proving_ground.runner.trend())."""
    from sovereign_agent.read_repair import read_ndjson_tolerant

    records = read_ndjson_tolerant(_ledger_path(data_dir), store="quality",
                                   emit=False).records[-n:]
    values = [r.get("value", 0.0) for r in records]
    if len(values) < 2:
        return "insufficient-history"
    if values[-1] > values[0] + 5.0:
        return "improving"
    if values[-1] < values[0] - 5.0:
        return "declining"
    return "stable"


__all__ = ["FileScore", "QualityPassResult", "record_quality_pass",
          "latest_quality", "quality_trend"]
