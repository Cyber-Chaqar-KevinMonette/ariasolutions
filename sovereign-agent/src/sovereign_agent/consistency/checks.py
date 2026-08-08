"""consistency/checks.py — the joins, checked. (FABLE II · M1 · one-truth-d)

Her memory is MANY excellent organs (atoms, palace, chunks, lessons,
journal, Q&As, field notes, scores, ledgers). The next failure class is
not loss — it is DISAGREEMENT: stores drifting out of consistency with
each other, truths recorded twice differently, reads that depend on which
organ you ask. One life deserves one truth.

Each join between two stores is ONE NAMED CHECK with a MECHANICAL verdict
(no LLM judge — the proving-ground discipline). A finding never repairs
anything; it carries a repair PROPOSAL the operator can act on (the
diagnosis.py pattern: no resolution without a human).

Checks (the joins, as verified against the live anatomy 2026-07-05):
  thread-chunks    thread_id file ↔ chunks.ndjson session ids
  sessions-scope   every sessions/<sid>.scope.json has its sessions/<sid>.json
  active-corpses   no session sits "active" with no process for a day (F7
                   found one the day it looked)
  rest-point       resume_point.json names a session that exists and is
                   actually resumable
  lessons-retrain  lessons count in atoms.db ↔ aria_lm/last_retrain.json
                   marker (marker can never be AHEAD of reality)
  qa-uncertainty   qa.ndjson low-confidence answers ↔ uncertainty registry
                   links resolve; no dangling closes in the registry
  proving-suite    every proving_ground result references the suite
                   version it scored
  dispositions     every loose-threads disposition references a symbol
                   that still exists (dispositions go stale as code
                   changes; a RETIRED record for a deleted symbol is the
                   one honest exception)
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

MARK = "one-truth-d"

# A session claiming "active" older than this is a corpse, not a worker.
STALE_ACTIVE_HOURS = 24
# Mirror curiosity.LOW_CONFIDENCE without importing the model machinery.
LOW_CONFIDENCE = 0.4
# Findings listed per check are capped so a flooded store can't flood the
# report; the count stays honest.
MAX_LISTED = 20


@dataclass
class Finding:
    """One observed disagreement between stores — with a repair PROPOSAL,
    never a repair."""

    check_id: str
    subject: str
    problem: str
    proposal: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class CheckResult:
    check_id: str
    ok: bool
    checked: int = 0                 # how many records/joins were examined
    findings: list[Finding] = field(default_factory=list)
    note: str = ""                   # honest context ("store absent — nothing to disagree")

    def as_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "ok": self.ok,
            "checked": self.checked,
            "findings": [f.as_dict() for f in self.findings],
            "note": self.note,
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _data_dir(data_dir: Path | None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    return Path(data_dir)


def _read_ndjson(path: Path) -> list[dict]:
    """Tolerant line reader — a corrupt line is skipped, never a wedge.
    (M3 centralizes this discipline; the checks must not crash on the very
    corruption they exist to observe.)"""
    out: list[dict] = []
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _finish(result: CheckResult) -> CheckResult:
    result.ok = not result.findings
    result.findings = result.findings[:MAX_LISTED]
    return result


# ─── the checks ──────────────────────────────────────────────────────────


def check_thread_chunks(data_dir: Path | None = None) -> CheckResult:
    """thread_id ↔ chunks agree on THE thread. Chunks addressed to any
    other session id are conversation she can no longer reach from the
    one universal thread (the exact orphaning thread_identity.py closed)."""
    base = _data_dir(data_dir)
    result = CheckResult(check_id="thread-chunks", ok=True)

    thread_file = base / "thread_id"
    tid = ""
    if thread_file.exists():
        tid = thread_file.read_text(encoding="utf-8", errors="replace").strip()
    if not tid:
        from sovereign_agent.thread_identity import DEFAULT_THREAD_ID

        tid = DEFAULT_THREAD_ID

    chunks = _read_ndjson(base / "checkpoint_chunks" / "chunks.ndjson")
    result.checked = len(chunks)
    if not chunks:
        result.note = "no sealed chunks yet — nothing to disagree"
        return _finish(result)

    foreign: dict[str, int] = {}
    for rec in chunks:
        sid = str(rec.get("session_id", ""))
        if sid and sid != tid:
            foreign[sid] = foreign.get(sid, 0) + 1
    for sid, n in sorted(foreign.items()):
        result.findings.append(Finding(
            check_id="thread-chunks",
            subject=sid,
            problem=f"{n} chunk(s) addressed to session {sid!r}, not the "
                    f"universal thread {tid!r} — unreachable from restore_tail()",
            proposal="operator-run merge: re-address these chunks to the "
                     "thread (append-only copy with new session_id; the "
                     "originals stay on disk untouched)",
        ))
    return _finish(result)


def check_sessions_scope(data_dir: Path | None = None) -> CheckResult:
    """Every sessions/<sid>.scope.json has its sessions/<sid>.json. A scope
    contract without a session is a promise nobody is keeping."""
    base = _data_dir(data_dir)
    sessions_dir = base / "sessions"
    result = CheckResult(check_id="sessions-scope", ok=True)
    if not sessions_dir.is_dir():
        result.note = "no sessions dir yet"
        return _finish(result)
    scopes = sorted(sessions_dir.glob("*.scope.json"))
    result.checked = len(scopes)
    for scope_path in scopes:
        sid = scope_path.name[: -len(".scope.json")]
        if not (sessions_dir / f"{sid}.json").exists():
            result.findings.append(Finding(
                check_id="sessions-scope",
                subject=scope_path.name,
                problem=f"scope contract exists but session {sid!r} does not",
                proposal=f"archive the orphan contract (move {scope_path.name} "
                         f"aside) or restore the session file from backup",
            ))
    return _finish(result)


def check_active_corpses(data_dir: Path | None = None,
                         *, stale_hours: int = STALE_ACTIVE_HOURS) -> CheckResult:
    """No 'active' corpses: a session file claiming active whose updated_at
    is older than a day has no process behind it — its status lies."""
    base = _data_dir(data_dir)
    sessions_dir = base / "sessions"
    result = CheckResult(check_id="active-corpses", ok=True)
    if not sessions_dir.is_dir():
        result.note = "no sessions dir yet"
        return _finish(result)
    cutoff = _now() - timedelta(hours=stale_hours)
    for path in sorted(sessions_dir.glob("*.json")):
        if path.name.endswith(".scope.json"):
            continue
        try:
            rec = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except ValueError:
            result.findings.append(Finding(
                check_id="active-corpses", subject=path.name,
                problem="session file is corrupt JSON",
                proposal="quarantine the file (move aside) and inspect; "
                         "SessionStore refuses corrupt loads",
            ))
            continue
        result.checked += 1
        if rec.get("status") not in ("active", "in_progress"):
            continue
        updated = str(rec.get("updated_at", ""))
        try:
            ts = datetime.strptime(updated[:26].rstrip("Z"),
                                   "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)
        except ValueError:
            ts = None
        if ts is None or ts < cutoff:
            sid = rec.get("session_id", path.stem)
            result.findings.append(Finding(
                check_id="active-corpses", subject=str(sid),
                problem=f"session claims status=active but was last updated "
                        f"{updated or 'unknown'} (> {stale_hours}h ago) — no "
                        f"process is behind it",
                proposal=f"`sov session halt {sid}` (records why), or resume "
                         f"it deliberately with `/resume`",
            ))
    return _finish(result)


def check_rest_point(data_dir: Path | None = None) -> CheckResult:
    """resume_point.json ↔ sessions agree: the bookmark names a session
    that exists and is not already complete."""
    base = _data_dir(data_dir)
    result = CheckResult(check_id="rest-point", ok=True)
    path = base / "resume_point.json"
    if not path.exists():
        result.note = "no rest point pending"
        return _finish(result)
    try:
        rec = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except ValueError:
        result.findings.append(Finding(
            check_id="rest-point", subject="resume_point.json",
            problem="rest point is corrupt JSON — the wake greeting will drop it",
            proposal="delete the corrupt bookmark (it is a courtesy, not a record)",
        ))
        return _finish(result)
    result.checked = 1
    sid = str(rec.get("session_id", "")).strip()
    if not sid:
        return _finish(result)   # a goal-only bookmark is legitimate
    session_path = base / "sessions" / f"{sid}.json"
    if not session_path.exists():
        result.findings.append(Finding(
            check_id="rest-point", subject=sid,
            problem=f"rest point names session {sid!r} but no such session file exists",
            proposal="clear the bookmark (consume_rest_point) — there is "
                     "nothing to resume into",
        ))
        return _finish(result)
    try:
        status = json.loads(session_path.read_text(encoding="utf-8",
                                                   errors="replace")).get("status")
    except ValueError:
        status = None
    if status == "complete":
        result.findings.append(Finding(
            check_id="rest-point", subject=sid,
            problem=f"rest point names session {sid!r} which is already complete "
                    f"— a stale bookmark",
            proposal="clear the bookmark; the session finished without it",
        ))
    return _finish(result)


def check_lessons_retrain(data_dir: Path | None = None) -> CheckResult:
    """lessons in atoms.db ↔ aria_lm/last_retrain.json marker. The marker
    records the lesson count at the last completed retrain; it can lag
    reality (new lessons since) but can never be AHEAD of it."""
    base = _data_dir(data_dir)
    result = CheckResult(check_id="lessons-retrain", ok=True)
    marker_path = base / "aria_lm" / "last_retrain.json"
    if not marker_path.exists():
        result.note = "no retrain marker yet — trigger never fired"
        return _finish(result)
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8", errors="replace"))
        marked = int(marker.get("lesson_count_at_last_retrain", 0))
    except (ValueError, TypeError):
        result.findings.append(Finding(
            check_id="lessons-retrain", subject="last_retrain.json",
            problem="retrain marker is corrupt/unreadable",
            proposal="delete the marker — the trigger rebuilds a baseline on "
                     "the next completed run (it only ever proposes)",
        ))
        return _finish(result)
    result.checked = 1
    db_path = base / "atoms.db"
    total = 0
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute("SELECT COUNT(*) FROM lessons").fetchone()
                total = int(row[0]) if row else 0
            finally:
                conn.close()
        except sqlite3.Error:
            total = 0
    if marked > total:
        result.findings.append(Finding(
            check_id="lessons-retrain", subject="last_retrain.json",
            problem=f"marker says {marked} lessons existed at last retrain but "
                    f"atoms.db holds only {total} — the marker is ahead of reality",
            proposal=f"operator-run: reset the marker baseline to {total} "
                     f"(record_retrain) so the trigger counts honestly again",
        ))
    return _finish(result)


def check_qa_uncertainty(data_dir: Path | None = None) -> CheckResult:
    """qa.ndjson ↔ uncertainty registry links resolve. Two joins:
    (a) registry-internal: every close references an open (no dangling
        closes);
    (b) the wonder loop's promise: a low-confidence answer auto-opens a
        curiosity uncertainty — a low-confidence QA with no matching
        curiosity question is a broken link."""
    base = _data_dir(data_dir)
    result = CheckResult(check_id="qa-uncertainty", ok=True)
    registry = _read_ndjson(base / "epistemic" / "uncertainties.ndjson")
    # An OPEN event is a record without a resolution; a close re-appends the
    # record with resolution set (the registry never mutates history).
    opened_ids = {r.get("uncertainty_id") for r in registry if not r.get("resolution")}
    curiosity_questions = {
        str(r.get("question", "")) for r in registry
        if str(r.get("domain", "")) == "curiosity"
    }
    for rec in registry:
        result.checked += 1
        # a "close" is a record whose resolution is set; its id must have opened
        if rec.get("resolution") and rec.get("uncertainty_id") not in opened_ids:
            result.findings.append(Finding(
                check_id="qa-uncertainty",
                subject=str(rec.get("uncertainty_id", "?")),
                problem="registry close references an uncertainty that was never opened",
                proposal="append a matching open record (registry is append-only; "
                         "the dangling close stays as history)",
            ))
    for rec in _read_ndjson(base / "qa" / "qa.ndjson"):
        result.checked += 1
        try:
            conf = float(rec.get("confidence", 1.0))
        except (TypeError, ValueError):
            conf = 1.0
        question = str(rec.get("question", ""))
        if conf < LOW_CONFIDENCE and question and question not in curiosity_questions:
            result.findings.append(Finding(
                check_id="qa-uncertainty",
                subject=str(rec.get("qa_id", "?")),
                problem=f"low-confidence QA ({conf:.2f}) never opened its "
                        f"promised curiosity uncertainty",
                proposal="operator-run: open the uncertainty for this question "
                         "(UncertaintyRegistry.open, domain='curiosity')",
            ))
    if not registry and result.checked == 0:
        result.note = "no registry / no QAs yet"
    return _finish(result)


def check_proving_suite(data_dir: Path | None = None) -> CheckResult:
    """Every proving-ground result references the suite version it scored.
    A score without a suite version is a number without a meaning."""
    base = _data_dir(data_dir)
    result = CheckResult(check_id="proving-suite", ok=True)
    path = base / "proving_ground" / "results.ndjson"
    if not path.exists():
        result.note = "no proving results yet"
        return _finish(result)
    for rec in _read_ndjson(path):
        result.checked += 1
        if not str(rec.get("suite", "")).strip():
            result.findings.append(Finding(
                check_id="proving-suite",
                subject=str(rec.get("run_id", "?")),
                problem="proving result carries no suite version — the score "
                        "cannot be compared to anything",
                proposal="exclude it from trend() manually; future results "
                         "always stamp SUITE_VERSION (runner.py does)",
            ))
    return _finish(result)


_DEF_RE_TEMPLATE = r"^\s*(?:async\s+def|def|class)\s+{name}\b"


def symbol_exists(symbol: str, src_root: Path) -> bool:
    """Mechanical existence check for a loose-threads symbol
    ('package.module.QualName'). Resolves the module file under src_root's
    parent and greps for its top-level def/class. Never raises."""
    try:
        module, _, name = symbol.rpartition(".")
        if not module or not name:
            return False
        rel = Path(*module.split("."))
        for candidate in (src_root.parent / rel.with_suffix(".py"),
                          src_root.parent / rel / "__init__.py"):
            if candidate.exists():
                text = candidate.read_text(encoding="utf-8", errors="replace")
                if re.search(_DEF_RE_TEMPLATE.format(name=re.escape(name)),
                             text, re.MULTILINE):
                    return True
        return False
    except OSError:
        return False


def check_dispositions(data_dir: Path | None = None,
                       src_root: Path | None = None) -> CheckResult:
    """Every loose-threads disposition references a symbol that still
    exists. Dispositions go stale as code changes. The honest exception:
    a RETIRED disposition whose symbol is gone is CONSISTENT — retired,
    then deleted, exactly as intended."""
    base = _data_dir(data_dir)
    if src_root is None:
        import sovereign_agent

        src_root = Path(sovereign_agent.__file__).parent
    result = CheckResult(check_id="dispositions", ok=True)
    path = base / "loose_threads" / "ledger.ndjson"
    if not path.exists():
        result.note = "no disposition ledger yet"
        return _finish(result)
    latest: dict[str, dict] = {}
    for rec in _read_ndjson(path):
        if rec.get("symbol"):
            latest[str(rec["symbol"])] = rec
    for symbol, rec in sorted(latest.items()):
        result.checked += 1
        verdict = str(rec.get("verdict", ""))
        if symbol_exists(symbol, Path(src_root)):
            continue
        if verdict == "RETIRED":
            continue   # retired and then deleted — the ledger told the truth
        result.findings.append(Finding(
            check_id="dispositions", subject=symbol,
            problem=f"disposition {verdict} references {symbol!r}, which no "
                    f"longer exists in the codebase",
            proposal=f"append RETIRED for {symbol!r} with reason 'symbol "
                     f"removed from codebase' so the ledger matches reality",
        ))
    return _finish(result)


# ─── the sweep ───────────────────────────────────────────────────────────

ALL_CHECKS = {
    "thread-chunks": check_thread_chunks,
    "sessions-scope": check_sessions_scope,
    "active-corpses": check_active_corpses,
    "rest-point": check_rest_point,
    "lessons-retrain": check_lessons_retrain,
    "qa-uncertainty": check_qa_uncertainty,
    "proving-suite": check_proving_suite,
    "dispositions": check_dispositions,
}


def run_all(data_dir: Path | None = None,
            src_root: Path | None = None) -> list[CheckResult]:
    """Every join, checked. A crashing check becomes a finding about the
    check itself — the sweep never wedges on one bad store."""
    out: list[CheckResult] = []
    for check_id, fn in ALL_CHECKS.items():
        try:
            if check_id == "dispositions":
                out.append(fn(data_dir, src_root))
            else:
                out.append(fn(data_dir))
        except Exception as exc:  # noqa: BLE001 — one bad organ must not hide the rest
            out.append(CheckResult(
                check_id=check_id, ok=False, checked=0,
                findings=[Finding(
                    check_id=check_id, subject="(check crashed)",
                    problem=f"check raised {exc!r}",
                    proposal="inspect the store this check reads; the crash "
                             "itself is the inconsistency signal",
                )],
            ))
    return out
