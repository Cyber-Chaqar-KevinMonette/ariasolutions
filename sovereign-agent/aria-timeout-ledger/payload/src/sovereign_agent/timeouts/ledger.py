"""timeouts/ledger.py — the persisted timeout classification. (Timeout round · T1)

Kevin: "make sure timeouts become gates and justified... a god tier
timeout system." Research found the exact gap: `vram.py:117-161`'s
`vram_lock()` is the ONE mechanism in this whole tree that both times out
AND emits a durable ledger event on timeout (`emit_event("vram-lock-
timeout-d", ...)`, persisted into `events.jsonl`) — but nothing ever
reads that event back. It's written once and forgotten. This module
closes exactly that gap: it reads the SAME existing event log (no new
storage — same "don't duplicate storage" discipline `grounding/ledger.py`
already established) and classifies each timeout event as `justified`
(a known, catalogued, bounded timeout site, within its own declared
bound) or `unexplained` (an uncatalogued source, or one that exceeded its
own catalogued bound).

`TIMEOUT_CATALOG` documents every known-bounded timeout site this
round's research found (git tools, the resilience scanner's SIGALRM,
`vram_lock` itself, LLM/Ollama-call timeouts, subprocess tool timeouts) —
most of these do NOT currently emit a timeout event (`vram_lock` is the
only real emitter today), so the catalog is honest reference material for
"this timeout is bounded and known, by design" even where this ledger
can't yet observe it happening. As other call sites are wired to emit
their own timeout events (a natural future extension, not required by
this round), they slot into the same catalog and become observable for
free.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MARK = "timeout-ledger-d"

# source (matches an event's flag, or its payload["tool"]) -> declared
# bound in seconds. Reference material for every known-bounded timeout
# site this round's research found — not all of these currently emit an
# event; `vram-lock-timeout-d` is the only real emitter today.
TIMEOUT_CATALOG: dict[str, float] = {
    "vram-lock-timeout-d": 60.0,       # vram.py:118 default
    "git_tools": 15.0,                 # tools/git_tools.py _GIT_TIMEOUT
    "git_write": 15.0,                 # tools/git_write.py _SAFE_TIMEOUT
    "resilience_scan": 2.0,            # resilience_scan/scanner.py SIGALRM default
    "run_python": 120.0,               # tools/runner.py Field bound (le=120)
    "run_shell": 300.0,                # tools/runner.py Field bound (le=300)
    "run_pytest": 600.0,               # tools/runner.py Field bound (le=600)
    "command_master": 300.0,           # tools/command_master.py Field bound
    "ollama_liveness": 3.0,            # ollama_client.py default
    "llm_call": 60.0,                  # interpreter.py/consolidate.py/discovery.py/architect.py's widest default
}


@dataclass
class TimeoutEvent:
    flag: str
    tool: str
    timeout_seconds: float | None
    trace_id: str
    ts: str
    catalogued_bound: float | None
    verdict: str   # "justified" | "unexplained"

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class TimeoutScanResult:
    scan_id: str
    ts: str
    events: list[TimeoutEvent] = field(default_factory=list)

    @property
    def unexplained_count(self) -> int:
        return sum(1 for e in self.events if e.verdict == "unexplained")

    @property
    def verdict(self) -> str:
        """Worst-of: any unexplained event fails the pass. Vacuously
        "justified" when nothing was found — "no timeouts happened" and
        "a timeout happened and nobody can explain it" must never look
        the same to a caller deciding whether to gate or alarm (the same
        honesty fix every other round's own verdict property needed)."""
        if not self.events:
            return "justified"
        return "unexplained" if self.unexplained_count else "justified"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["unexplained_count"] = self.unexplained_count
        d["verdict"] = self.verdict
        return d


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_id() -> str:
    from ulid import ULID

    return f"ts-{str(ULID())[:12]}"


def _ledger_path(data_dir: Path | None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    p = Path(data_dir) / "timeouts"
    p.mkdir(parents=True, exist_ok=True)
    return p / "ledger.ndjson"


def _recent_raw_events(data_dir: Path | None, *, window: int = 300) -> list[dict]:
    """(source, event) pairs from events-*.jsonl newer than nothing in
    particular — the newest `window` events, mirroring companion_tools.
    _load_recent_events_for_report()'s exact glob/read pattern (the real,
    canonical event log is daily-rotated `events-{day}.jsonl`, never
    `*.ndjson`). [] on any failure — never a crash."""
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        base = SETTINGS.paths.data_dir
    else:
        base = Path(data_dir)
    events: list[dict] = []
    events_dir = base / "events"
    if not events_dir.is_dir():
        return events
    for f in sorted(events_dir.glob("events-*.jsonl"))[-3:]:
        try:
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    events.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return events[-window:]


def _classify(raw: dict) -> TimeoutEvent:
    flag = str(raw.get("flag", ""))
    payload = raw.get("payload") or {}
    tool = str(payload.get("tool", flag))
    timeout_seconds = payload.get("timeout_seconds")

    bound = TIMEOUT_CATALOG.get(flag) or TIMEOUT_CATALOG.get(tool)
    if bound is None:
        verdict = "unexplained"  # uncatalogued source
    elif timeout_seconds is not None and float(timeout_seconds) > bound:
        verdict = "unexplained"  # exceeded its own declared bound
    else:
        verdict = "justified"

    return TimeoutEvent(
        flag=flag, tool=tool,
        timeout_seconds=float(timeout_seconds) if timeout_seconds is not None else None,
        trace_id=str(raw.get("trace_id", "")), ts=str(raw.get("ts", "")),
        catalogued_bound=bound, verdict=verdict,
    )


def record_timeout_scan(data_dir: Path | None = None, *, window: int = 300) -> TimeoutScanResult:
    """Scan recent events for any flag containing "timeout", classify each
    against TIMEOUT_CATALOG, append ONE fsync'd record. A malformed event
    is skipped — noted, never a crash."""
    raw_events = _recent_raw_events(data_dir, window=window)
    # Match the real per-occurrence naming convention (flag ENDS with
    # "-timeout-d", e.g. "vram-lock-timeout-d") rather than a bare
    # substring match on "timeout" — this module's own emitted
    # "timeout-scan-d" summary event contains the word "timeout" too but
    # is not itself a timeout occurrence; a substring match would make
    # every scan recursively (mis)classify its own prior summary events
    # as unexplained timeouts, forever.
    timeout_events = [
        _classify(r) for r in raw_events
        if str(r.get("flag", "")).lower().endswith("-timeout-d")
    ]

    result = TimeoutScanResult(scan_id=_new_id(), ts=_now(), events=timeout_events)
    path = _ledger_path(data_dir)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(result.as_dict(), separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    try:
        from sovereign_agent.events import emit_event

        emit_event("timeout-scan-d", plane="control", trace_id=result.scan_id,
                   payload={"verdict": result.verdict, "unexplained_count": result.unexplained_count,
                            "events_scanned": len(timeout_events)})
    except Exception:  # noqa: BLE001
        pass
    return result


def latest_timeout_scan(data_dir: Path | None = None) -> dict | None:
    from sovereign_agent.read_repair import read_ndjson_tolerant

    records = read_ndjson_tolerant(_ledger_path(data_dir), store="timeouts",
                                   emit=False).records
    return records[-1] if records else None


def timeout_trend(n: int = 10, data_dir: Path | None = None) -> str:
    """From STORED scans only — the honest kind (mirrors every other
    round's own *_trend() function)."""
    from sovereign_agent.read_repair import read_ndjson_tolerant

    records = read_ndjson_tolerant(_ledger_path(data_dir), store="timeouts",
                                   emit=False).records[-n:]
    values = [r.get("unexplained_count", 0) for r in records]
    if len(values) < 2:
        return "insufficient-history"
    if values[-1] > values[0]:
        return "worsening"
    if values[-1] < values[0]:
        return "improving"
    return "stable"


__all__ = ["TIMEOUT_CATALOG", "TimeoutEvent", "TimeoutScanResult",
          "record_timeout_scan", "latest_timeout_scan", "timeout_trend"]
