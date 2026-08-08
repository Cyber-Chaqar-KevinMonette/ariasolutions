"""resilience_scan/scanner.py — probe any callable with the edge battery; certify graceful degradation.

Works on BOTH layers: pass a classical function/tool OR a non-classical entry point (the superposition
processor, the PEIG brain). A target is RESILIENT if every edge input returns a value/status WITHOUT an
unhandled crash. A target may legitimately raise a *declared* exception (e.g. ValueError on bad input) —
that is graceful (handled) IF it's a controlled exception type, not a wedge (hang) or an unexpected crash.
"""
from __future__ import annotations

import signal
from dataclasses import dataclass, field

from . import probes

# Exceptions that represent GRACEFUL, intentional rejection (not a resilience failure).
_GRACEFUL_EXC = (ValueError, TypeError, KeyError, FileNotFoundError, NotImplementedError, PermissionError)


@dataclass
class ProbeResult:
    target: str
    total: int = 0
    survived: int = 0          # returned a value OR raised a graceful exception
    wedged: list = field(default_factory=list)   # inputs that caused an UNgraceful crash
    note: str = ""

    @property
    def score(self) -> float:
        return self.survived / self.total if self.total else 1.0

    @property
    def resilient(self) -> bool:
        return not self.wedged

    def to_dict(self) -> dict:
        return {"target": self.target, "score": round(self.score, 3), "resilient": self.resilient,
                "survived": self.survived, "total": self.total, "wedged": self.wedged[:8], "note": self.note}


class _Timeout(Exception):
    pass


def _with_timeout(fn, arg, seconds: float = 2.0):
    """Run fn(arg) with a hard timeout so a hang is caught as a wedge (not an infinite block)."""
    def _handler(signum, frame):  # noqa: ARG001
        raise _Timeout()
    had = signal.getsignal(signal.SIGALRM)
    try:
        signal.signal(signal.SIGALRM, _handler)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        return fn(arg)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, had)


def probe_callable(fn, *, name: str = "", cases: list | None = None, kind: str = "any") -> ProbeResult:
    """Probe a single-arg callable with the edge battery. Returns a ProbeResult."""
    cases = cases if cases is not None else {
        "string": probes.edge_strings, "list": probes.edge_lists,
        "number": probes.edge_numbers, "any": probes.edge_any,
    }.get(kind, probes.edge_any)()
    res = ProbeResult(target=name or getattr(fn, "__name__", repr(fn)))
    for case in cases:
        res.total += 1
        try:
            _with_timeout(fn, case, seconds=2.0)
            res.survived += 1                       # returned cleanly
        except _GRACEFUL_EXC:
            res.survived += 1                       # graceful, declared rejection — fine
        except _Timeout:
            res.wedged.append(f"TIMEOUT on {_short(case)}")
        except Exception as exc:  # noqa: BLE001 — any other crash is an ungraceful wedge
            res.wedged.append(f"{type(exc).__name__} on {_short(case)}")
    res.note = ("resilient — degrades gracefully on every edge input" if res.resilient
                else f"{len(res.wedged)} edge input(s) wedge it — harden these")
    return res


def _short(x) -> str:
    s = repr(x)
    return s[:40] + "…" if len(s) > 40 else s
