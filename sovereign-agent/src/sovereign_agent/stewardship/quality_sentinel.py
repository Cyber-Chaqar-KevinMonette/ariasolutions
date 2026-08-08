"""stewardship/quality_sentinel.py — QualitySentinel. (Quality round · Q1)

`qa/hardening.py` + `qa/quality_score.py` were real and deterministic but
NEVER WATCHED — no sentinel, no gate, no standing audit ever called them.
This sentinel closes that: it periodically runs a real quality pass
(`quality.ledger.record_quality_pass`) over recently-touched files and
reports the persisted result — propose-only, like every sentinel here.

"Recently touched" = files changed since this sentinel's own last scan
(git diff, bookmarked in its own catalog), falling back to the newest
applied module's payload files on a fresh install (nothing scanned yet).

Kill switch: SOV_NO_QUALITY_SENTINEL=1 (via Sentinel.is_enabled();
master: SOV_NO_SENTINELS=1).
"""
from __future__ import annotations

import subprocess

import sovereign_agent.stewardship  # noqa: F401 — resolve circularity first
from datetime import datetime, timezone
from pathlib import Path

from sovereign_agent.stewardship.base import HealthStatus, Sentinel, SentinelReport
from sovereign_agent.stewardship.registry import register_sentinel

MARK = "quality-sentinel-d"
_GIT_TIMEOUT = 15


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _git(args: list[str], cwd: Path) -> tuple[bool, str]:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                           text=True, errors="replace", timeout=_GIT_TIMEOUT)
        return r.returncode == 0, (r.stdout or "").strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False, ""


def _src_root() -> Path:
    import sovereign_agent

    return Path(sovereign_agent.__file__).parent


def _repo_root(src_root: Path) -> Path | None:
    ok, out = _git(["rev-parse", "--show-toplevel"], src_root)
    return Path(out) if ok and out else None


def _project_root(src_root: Path) -> Path | None:
    """Where `aria-*/` staged folders and pyproject.toml actually live —
    NOT necessarily `git rev-parse --show-toplevel`. This repo is nested
    (sovereign-agent/ sits inside a larger AA-Erebo git checkout), so the
    git top-level and the project root are different directories; using
    the wrong one here means `_newest_applied_module_files` silently
    finds nothing (empty aria-*/ glob), not an error — exactly the kind
    of quiet failure this sentinel exists to catch elsewhere. Mirrors
    `qa/hardening.py:harden_module()`'s own walk-up-for-pyproject.toml
    convention exactly, so both agree on what "the project" means."""
    cur = src_root.parent
    for _ in range(8):
        if (cur / "pyproject.toml").is_file():
            return cur
        cur = cur.parent
    return None


def _recently_touched(src_root: Path, since_commit: str) -> list[Path]:
    """Files changed since `since_commit`, or [] if that fails (repo
    unavailable, bad commit, shallow clone edge cases — never a crash)."""
    root = _repo_root(src_root)
    if root is None:
        return []
    ok, out = _git(["diff", "--name-only", since_commit, "--", "*.py"], root)
    if not ok:
        return []
    out_files = []
    for rel in out.splitlines():
        p = root / rel
        if p.is_file() and "src/sovereign_agent" in str(p):
            out_files.append(p)
    return out_files


def _newest_applied_module_files(repo_root: Path | None) -> list[Path]:
    """Fresh-install fallback: the newest `.applied_ok` module's own
    payload .py files — something real to score even on the first scan."""
    if repo_root is None:
        return []
    candidates = sorted(
        repo_root.glob("aria-*/.applied_ok"),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if not candidates:
        return []
    mod_dir = candidates[0].parent
    payload = mod_dir / "payload" / "src" / "sovereign_agent"
    if not payload.is_dir():
        return []
    return list(payload.rglob("*.py"))


@register_sentinel
class QualitySentinel(Sentinel):
    """Watches whether her own recent work is actually hardened — not
    just whether it imports."""

    @property
    def id(self) -> str:
        return "quality"

    @property
    def title(self) -> str:
        return "Quality — persisted hardening score over recently-touched work"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I. I run the real hardening checklist (qa/hardening.py) over "
            "recently-touched files and PERSIST the score — a score that "
            "vanishes when the call returns was never really kept.",
            "II. I never invent new checks; I compose what already exists "
            "(qa/hardening.py, qa/quality_score.py) rather than duplicate it.",
            "III. I propose, never repair. A critical failure is reported, "
            "never silently fixed.",
            "IV. 'Recently touched' means since my own last look, or the "
            "newest applied module on a fresh install — never the whole "
            "repo at once; a standing sentinel that reruns everything every "
            "time is a standing sentinel nobody can afford to run.",
        ]

    def _bookmark_commit(self) -> str | None:
        cached = self.load_catalog(name="bookmark")
        return cached.get("last_scan_commit") if cached else None

    def scan(self) -> SentinelReport:
        from sovereign_agent.quality.ledger import record_quality_pass

        src_root = _src_root()
        repo_root = _repo_root(src_root)          # for git-diff (the bookmark path)
        project_root = _project_root(src_root)     # for the aria-*/ fallback glob
        bookmark = self._bookmark_commit()

        targets: list[Path] = []
        if repo_root is not None and bookmark:
            targets = _recently_touched(src_root, bookmark)
        if not targets:
            targets = _newest_applied_module_files(project_root)

        result = record_quality_pass(targets, self._data_dir)

        # move the bookmark forward to HEAD, so next scan only looks at
        # what changed since THIS scan — never rescanning the same ground
        new_head = None
        if repo_root is not None:
            ok, head = _git(["rev-parse", "HEAD"], repo_root)
            if ok:
                new_head = head
        if new_head:
            self.save_catalog({"last_scan_commit": new_head, "at": _now()},
                              name="bookmark")

        blob = {
            "pass": result.as_dict(),
            "files_scanned": len(targets),
        }
        cat_path = self.save_catalog(blob, name="quality")
        if not result.files:
            summary = "nothing to score — no recently-touched files found"
        else:
            summary = (f"{len(result.files)} file(s) scored · "
                      f"{result.value:.1f}/100"
                      + ("" if result.critical_ok else " · CRITICAL FAILURE"))
        report = SentinelReport(
            sentinel_id=self.id, observed_at=_now(),
            catalog_name="quality",
            findings_count=len([f for f in result.files if not f.critical_ok]),
            summary=summary,
            catalog_path=str(cat_path),
            details=blob,
        )
        if not result.critical_ok:
            bad = [f.path for f in result.files if not f.critical_ok]
            self.notify(
                severity="warning",
                title="quality pass found a critical hardening failure",
                message=f"{len(bad)} file(s) failed a weight-≥8 hardening "
                        f"check: {', '.join(bad[:5])}",
                addressed_to="operator",
                data={"files": bad},
            )
        # quality-tribunal-d — the standing phase: convene BOTH Tribunal and Advocate
        # Spectrum over this same real recent work, log through the
        # diagnosis catalog — the standing counterpart to TribunalSentinel's
        # narrow hardcoded-string self-check. Best-effort: a scrutiny
        # failure here must never break the quality scan itself.
        try:
            from sovereign_agent.quality.review import build_review_proposal

            proposal = build_review_proposal(self._data_dir)
            if proposal is not None:
                from sovereign_agent.tribunal import convene
                from sovereign_agent.tribunal.tribunal import log_to_diagnosis

                verdict = convene(proposal, include_kernel=False)
                case_id = log_to_diagnosis(proposal, verdict, self._data_dir)
                standing = {"verdict": verdict.verdict, "case_id": case_id}
                try:
                    from sovereign_agent.spectrum import convene_spectrum

                    cv = convene_spectrum(proposal)
                    standing["spectrum_verdict"] = cv.verdict
                    standing["spectrum_opposed"] = cv.opposed
                except Exception:  # noqa: BLE001 — spectrum is optional
                    pass
                self.save_catalog(standing, name="standing-audit")
        except Exception:  # noqa: BLE001 — a scrutiny failure never breaks the scan
            pass
        return report

    def health_status(self) -> HealthStatus:
        cached = self.load_catalog(name="quality")
        if cached is None:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="not yet scanned — `sov sentinels scan quality`",
                                observed_at=_now())
        pass_data = cached.get("pass", {})
        files = pass_data.get("files", [])
        critical_ok = pass_data.get("critical_ok", True)
        value = pass_data.get("value", 0.0)
        if not files:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="nothing to score — no recently-touched files found",
                                observed_at=_now())
        if not critical_ok:
            return HealthStatus(
                sentinel_id=self.id, level="warning",
                summary=f"critical hardening failure in last pass ({value:.1f}/100)",
                observed_at=_now())
        return HealthStatus(sentinel_id=self.id, level="ok",
                            summary=f"quality {value:.1f}/100 — no critical failures",
                            observed_at=_now())

    def proposals(self, report: SentinelReport) -> list[dict]:
        out = []
        for f in report.details.get("pass", {}).get("files", []):
            if not f.get("critical_ok", True):
                out.append({
                    "file": f.get("path"),
                    "summary": f"critical hardening check(s) failed: "
                              f"{', '.join(f.get('failures', []))}",
                    "remediation": "harden the module — see `sov quality show` "
                                  "for the full checklist",
                })
        return out
