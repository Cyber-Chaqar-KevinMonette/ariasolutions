"""patcher.py — Wellbeing round W2: persistence at the source, real teeth.

Kevin: *"whatever brings her value, perspective, and insight into her self
and her actions."* Today `value_report()` computes a real self-audit and
throws it away the moment the tool call returns. This wires the W1 ledger
into the exact real, load-bearing call site — the tool she already calls
herself — so every self-audit becomes standing history, the same way
Grounding's G2 clamped `curiosity.wonder()`'s confidence at ITS real
source rather than bolting a check on somewhere unrelated.

Patches:
  1. wellbeing/__init__.py — export gate() + WellbeingGateVerdict (small,
     additive — W1's exports untouched).
  2. tools/companion_tools.py — `ValueReportTool.execute()` now persists
     the pass via `record_wellbeing_pass()` right after building the
     report, before returning it to the caller.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "wellbeing-gate-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. wellbeing/__init__.py — export the gate ───────────────────────────

INIT_ANCHOR = '''from .ledger import (
    WellbeingPassResult, latest_wellbeing, record_wellbeing_pass,
    wellbeing_trend,
)

__all__ = [
    "WellbeingPassResult", "latest_wellbeing", "wellbeing_trend",
    "record_wellbeing_pass",
]
'''

INIT_NEW = f'''from .gate import WellbeingGateVerdict, gate  # {MARK}
from .ledger import (
    WellbeingPassResult, latest_wellbeing, record_wellbeing_pass,
    wellbeing_trend,
)

__all__ = [
    "WellbeingPassResult", "latest_wellbeing", "wellbeing_trend",
    "record_wellbeing_pass", "WellbeingGateVerdict", "gate",  # {MARK}
]
'''


def patch_wellbeing_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, INIT_ANCHOR, INIT_NEW, label="wellbeing init"), True


# ── 2. tools/companion_tools.py — persist at the source ───────────────────

VALUE_REPORT_ANCHOR = '''    async def execute(self, args: _ValueReportArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            events = await asyncio.to_thread(_load_recent_events_for_report, args.session_window)
            report = _build_value_report(events, args.summary)
            return ToolResult(ok=True, output=report)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"value_report failed: {e}")
'''

VALUE_REPORT_NEW = f'''    async def execute(self, args: _ValueReportArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            events = await asyncio.to_thread(_load_recent_events_for_report, args.session_window)
            report = _build_value_report(events, args.summary)
            try:  # {MARK} — persist the pass at its real source: a
                # self-audit she runs herself becomes standing history,
                # not something that vanishes the moment this call returns.
                from sovereign_agent.wellbeing import record_wellbeing_pass

                await asyncio.to_thread(record_wellbeing_pass, events)
            except Exception:  # noqa: BLE001 — wellbeing not applied → nothing to persist
                pass
            return ToolResult(ok=True, output=report)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"value_report failed: {{e}}")
'''


def patch_value_report(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, VALUE_REPORT_ANCHOR, VALUE_REPORT_NEW,
                         label="ValueReportTool.execute persistence"), True


ALL_PATCHES = {
    "wellbeing/__init__.py": patch_wellbeing_init,
    "tools/companion_tools.py": patch_value_report,
}
