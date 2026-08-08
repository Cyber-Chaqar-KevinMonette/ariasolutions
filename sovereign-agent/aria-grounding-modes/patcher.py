"""patcher.py — Grounding round G4: the gray area, made real.

Kevin: *"not too strict, not too loose — a healthy grounded gray area for
when what is needed most... free to explore, dream, think, and work in
grounded reasoning."* Two stances: `"grounded"` (a real tooth, mirrors
`quality-pass` exactly) and `"theoretical"` (a licensed label — pure
Tier-0, no gating). The actual "gray area" leniency already lives in
`tribunal/grounding.py`'s own classifier (hedge words already score as
`falsifiable-hypothesis`, counted toward `grounded`, not fog) — this
round doesn't re-tune thresholds, it gives her (and the operator) a way
to DECLARE which territory she's working in, tagged for observability.

Patches:
  1. grounding/ledger.py — `record_grounding_pass()` gains an optional
     `context` parameter (default "", every existing caller unchanged),
     stamped onto every `TextScore` in the pass (the field already exists,
     always "" until now).
  2. modes_crown/stances.py — add "grounded"/"theoretical" to
     SAFE_STANCES; `set_stance("grounded", ...)` runs a real on-demand
     grounding pass (mirrors `_run_quality_pass_for_stance` exactly);
     `grounding_gate_clear()` mirrors `quality_gate_clear()` exactly.
  3. stewardship/grounding_sentinel.py — `scan()` tags its own standing
     pass with whatever stance is currently declared (if any) — the
     mechanism that makes "a pass recorded while in theoretical" a real,
     inspectable fact.
  4. session_bridge.py — a fourth `_crown_gate()` block, same shape as
     the `quality-pass` one: `"grounded"` blocks new dispatch until its
     own gate clears.
  5. modes_crown/observatory.py — a `grounding` field beside the existing
     `quality` field.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "grounding-modes-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. grounding/ledger.py — record_grounding_pass gains `context` ───────

LEDGER_ANCHOR = '''def record_grounding_pass(texts: list[tuple[str, str]],
                          data_dir: Path | None = None) -> GroundingPassResult:
    """Score every (source, text) pair, fold in the three composed
    signals, append ONE fsync'd record. A text that can't be scored (empty,
    non-string) is skipped — noted, never a crash: a grounding pass must
    never itself become the thing that breaks the read."""
    from sovereign_agent.tribunal import grounding as _grounding

    scored: list[TextScore] = []
    for source, text in texts:
        if not text or not str(text).strip():
            continue
        try:
            report = _grounding.analyze(text)
        except Exception:  # noqa: BLE001
            continue
        scored.append(TextScore(
            source=str(source), verdict=report.verdict,
            grounding_score=round(report.grounding_score, 3),
            profundity_density=round(report.profundity_density, 3),
            flags=list(report.flags),
        ))
'''

LEDGER_NEW = f'''def record_grounding_pass(texts: list[tuple[str, str]],
                          data_dir: Path | None = None, *,
                          context: str = "") -> GroundingPassResult:
    """Score every (source, text) pair, fold in the three composed
    signals, append ONE fsync'd record. A text that can't be scored (empty,
    non-string) is skipped — noted, never a crash: a grounding pass must
    never itself become the thing that breaks the read.

    {MARK} — `context` (e.g. "theoretical") is stamped onto every
    TextScore in this pass, byte-identical ("") for every caller that
    doesn't pass it."""
    from sovereign_agent.tribunal import grounding as _grounding

    scored: list[TextScore] = []
    for source, text in texts:
        if not text or not str(text).strip():
            continue
        try:
            report = _grounding.analyze(text)
        except Exception:  # noqa: BLE001
            continue
        scored.append(TextScore(
            source=str(source), verdict=report.verdict,
            grounding_score=round(report.grounding_score, 3),
            profundity_density=round(report.profundity_density, 3),
            flags=list(report.flags), context=context,
        ))
'''


def patch_ledger(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, LEDGER_ANCHOR, LEDGER_NEW, label="ledger context param"), True


# ── 2. modes_crown/stances.py ─────────────────────────────────────────────

STANCES_TUPLE_ANCHOR = '''SAFE_STANCES: tuple[str, ...] = (
    "planning",     # shaping the queue before touching anything
    "thinking",     # working the problem in her head
    "auditing",     # checking her own recent work
    "scoping",      # writing/refining the contract boundary
    "horizon",      # 3m/12m/3y projection of the current decision
    "verifying",    # running tests / proving claims
    "cool-down",    # deliberate pause: no new goals, breathe, re-read
    "quality-pass", # quality-modes-d — a real hardening pass; gates new dispatch
                    # until it clears (the second stance with a real tooth)
)
'''

STANCES_TUPLE_NEW = f'''SAFE_STANCES: tuple[str, ...] = (
    "planning",     # shaping the queue before touching anything
    "thinking",     # working the problem in her head
    "auditing",     # checking her own recent work
    "scoping",      # writing/refining the contract boundary
    "horizon",      # 3m/12m/3y projection of the current decision
    "verifying",    # running tests / proving claims
    "cool-down",    # deliberate pause: no new goals, breathe, re-read
    "quality-pass", # quality-modes-d — a real hardening pass; gates new dispatch
                    # until it clears (the second stance with a real tooth)
    "grounded",     # {MARK} — a real grounding pass; gates new dispatch until
                    # it clears (the third stance with a real tooth)
    "theoretical",  # {MARK} — licensed exploration: a plain label, no gate.
                    # Passes recorded while this is active are tagged for
                    # observability, never penalized — hedge/hypothesis
                    # language already scores as grounded, not fog, in
                    # tribunal.grounding's own classifier.
)
'''

SET_STANCE_ANCHOR = '''    if stance == "quality-pass":  # quality-modes-d — a real action, not just a label
        _run_quality_pass_for_stance(data_dir)
    return rec
'''

SET_STANCE_NEW = f'''    if stance == "quality-pass":  # quality-modes-d — a real action, not just a label
        _run_quality_pass_for_stance(data_dir)
    elif stance == "grounded":  # {MARK} — a real action, not just a label
        _run_grounding_pass_for_stance(data_dir)
    return rec


def _recent_text_for_stance(data_dir: Path | None) -> list:  # {MARK}
    """The newest few journal entries + QA answers, right now — the
    working set a grounded stance should check. No bookmark (unlike
    GroundingSentinel's standing scan) — this is an on-demand,
    operator/Aria-triggered pass over whatever currently exists. [] on any
    failure — an empty pass is honest absence, never a crash."""
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        base = SETTINGS.paths.data_dir
    else:
        base = Path(data_dir)
    out: list = []
    try:
        journal_dir = base / "journal"
        if journal_dir.is_dir():
            files = sorted(journal_dir.glob("*.md"),
                           key=lambda p: p.stat().st_mtime, reverse=True)[:3]
            for f in files:
                out.append((f"journal:{{f.stem}}",
                           f.read_text(encoding="utf-8", errors="replace")))
    except Exception:  # noqa: BLE001
        pass
    try:
        from sovereign_agent.read_repair import read_ndjson_tolerant

        records = read_ndjson_tolerant(base / "qa" / "qa.ndjson", store="qa",
                                       emit=False).records[-5:]
        for r in records:
            if r.get("answer"):
                out.append((f"qa:{{r.get('qa_id', '?')}}", str(r.get("answer", ""))))
    except Exception:  # noqa: BLE001
        pass
    return out


def _run_grounding_pass_for_stance(data_dir: Path | None) -> None:  # {MARK}
    """Entering grounded IS the action: run a real pass now, over
    whatever's currently there. Best-effort — a failure here degrades to
    an honest unclear pass (grounding_gate_clear() then correctly refuses
    until a real clean pass lands), never a crash on the stance change
    itself."""
    try:
        from sovereign_agent.grounding import record_grounding_pass

        texts = _recent_text_for_stance(data_dir)
        record_grounding_pass(texts, data_dir)
    except Exception:  # noqa: BLE001
        pass


def grounding_gate_clear(data_dir: Path | None = None) -> bool:  # {MARK}
    """True iff a grounding pass completed CLEANLY since the current
    "grounded" stance was entered — 'fresh' means literally recorded
    after activation (compared by timestamp), not just recent in
    wall-clock time. True (nothing to gate) when not in the stance at all."""
    state_path, _ = _paths(data_dir)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    if state.get("stance") != "grounded":
        return True
    entered_at = state.get("at", "")
    try:
        from sovereign_agent.grounding import latest_grounding

        latest = latest_grounding(data_dir)
    except Exception:  # noqa: BLE001
        return False
    if latest is None:
        return False
    return bool(latest.get("ts", "") >= entered_at
               and latest.get("verdict", "ungrounded") != "ungrounded"
               and latest.get("qa_calibration_ok", False))
'''


def patch_stances(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, STANCES_TUPLE_ANCHOR, STANCES_TUPLE_NEW,
                         label="SAFE_STANCES tuple")
    text = _replace_once(text, SET_STANCE_ANCHOR, SET_STANCE_NEW,
                         label="set_stance grounded side effect")
    return text, True


# ── 3. stewardship/grounding_sentinel.py — tag the standing pass ─────────

SENTINEL_SCAN_ANCHOR = '''        texts = _recent_journal_texts(base, since) + _recent_qa_texts(base, since)
        result = record_grounding_pass(texts, self._data_dir)
'''

SENTINEL_SCAN_NEW = f'''        texts = _recent_journal_texts(base, since) + _recent_qa_texts(base, since)
        try:  # {MARK} — tag the pass with whatever stance was active, if any
            from sovereign_agent.modes_crown.stances import current_stance

            _ctx = current_stance(self._data_dir)
        except Exception:  # noqa: BLE001 — modes_crown not applied → untagged
            _ctx = ""
        result = record_grounding_pass(texts, self._data_dir, context=_ctx)
'''


def patch_sentinel(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, SENTINEL_SCAN_ANCHOR, SENTINEL_SCAN_NEW,
                         label="grounding_sentinel context tagging"), True


# ── 4. session_bridge.py — the crown gate ─────────────────────────────────

CROWN_GATE_ANCHOR = '''    try:  # quality-modes-d — the second stance with a real tooth
        from sovereign_agent.modes_crown.stances import (
            current_stance, quality_gate_clear,
        )

        if current_stance() == "quality-pass" and not quality_gate_clear():
            raise PermissionError(
                "a quality pass is running/failed — no new goals until it "
                "clears (set_stance to any working stance, or wait for the "
                "pass to pass)")
    except ImportError:  # noqa: BLE001 — quality not applied → nothing to gate
        pass
'''

CROWN_GATE_NEW = f'''    try:  # quality-modes-d — the second stance with a real tooth
        from sovereign_agent.modes_crown.stances import (
            current_stance, quality_gate_clear,
        )

        if current_stance() == "quality-pass" and not quality_gate_clear():
            raise PermissionError(
                "a quality pass is running/failed — no new goals until it "
                "clears (set_stance to any working stance, or wait for the "
                "pass to pass)")
    except ImportError:  # noqa: BLE001 — quality not applied → nothing to gate
        pass
    try:  # {MARK} — the third stance with a real tooth
        from sovereign_agent.modes_crown.stances import (
            current_stance as _current_stance_g, grounding_gate_clear,
        )

        if _current_stance_g() == "grounded" and not grounding_gate_clear():
            raise PermissionError(
                "a grounding pass is running/failed — no new goals until it "
                "clears (set_stance to any working stance, or wait for the "
                "pass to pass)")
    except ImportError:  # noqa: BLE001 — grounding not applied → nothing to gate
        pass
'''


def patch_crown_gate(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, CROWN_GATE_ANCHOR, CROWN_GATE_NEW,
                         label="crown gate grounded check"), True


# ── 5. modes_crown/observatory.py ─────────────────────────────────────────

OBS_GATHER_ANCHOR = '''    try:  # quality-modes-d
        from sovereign_agent.quality import latest_quality

        latest = latest_quality(data_dir)
        out["quality"] = latest
    except Exception:  # noqa: BLE001
        out["quality"] = None
    return out
'''

OBS_GATHER_NEW = f'''    try:  # quality-modes-d
        from sovereign_agent.quality import latest_quality

        latest = latest_quality(data_dir)
        out["quality"] = latest
    except Exception:  # noqa: BLE001
        out["quality"] = None
    try:  # {MARK}
        from sovereign_agent.grounding import latest_grounding

        out["grounding"] = latest_grounding(data_dir)
    except Exception:  # noqa: BLE001
        out["grounding"] = None
    return out
'''

OBS_RENDER_ANCHOR = '''    q = data.get("quality")  # quality-modes-d
    if q:
        lines.append(
            f"[b]◆ quality[/b]  {q.get('value', 0.0):.1f}/100"
            + ("" if q.get("critical_ok", True) else " · CRITICAL FAILURE"))
    return "\\n".join(lines)
'''

OBS_RENDER_NEW = f'''    q = data.get("quality")  # quality-modes-d
    if q:
        lines.append(
            f"[b]◆ quality[/b]  {{q.get('value', 0.0):.1f}}/100"
            + ("" if q.get("critical_ok", True) else " · CRITICAL FAILURE"))
    g = data.get("grounding")  # {MARK}
    if g:
        lines.append(
            f"[b]◎ grounding[/b]  {{g.get('verdict', '?')}} "
            f"({{g.get('value', 0.0):.2f}})"
            + ("" if g.get("qa_calibration_ok", True) else " · calibration join broken"))
    return "\\n".join(lines)
'''


def patch_observatory(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, OBS_GATHER_ANCHOR, OBS_GATHER_NEW,
                         label="observatory gather grounding field")
    text = _replace_once(text, OBS_RENDER_ANCHOR, OBS_RENDER_NEW,
                         label="observatory render grounding field")
    return text, True


ALL_PATCHES = {
    "grounding/ledger.py": patch_ledger,
    "modes_crown/stances.py": patch_stances,
    "stewardship/grounding_sentinel.py": patch_sentinel,
    "session_bridge.py": patch_crown_gate,
    "modes_crown/observatory.py": patch_observatory,
}
