"""curiosity.py — her wonder, observable. (Keys round K6.)

Kevin: *"a Q&A feature where she comes up with god tier questions and god
tier answers when she is curious or wondering… also observability so we
can watch her work and do her Q&As."*

Seeds come from what is ALREADY hers: open known-unknowns from H3's
UncertaintyRegistry (the purest spark — questions she herself recorded),
recent Reflector lessons (experience worth interrogating), and open flaws
(honest self-knowledge). One bounded model call forms the question AND
answers it — a deliberate v1 economy for the 8B vessel; the question-
quality rubric lives in the prompt.

Everything is observable and durable:
  - `qa-start-d` / `qa-d` events (K1's run surface renders both richly)
  - `qa/qa.ndjson` — append-only, atomic, the same store discipline as
    EpistemicLedger/ChunkStore
  - answers with confidence < 0.4 auto-open a NEW uncertainty in the
    registry — wondering that fails honestly becomes a seed for next time
    (the wonder loop feeds itself without ever running unbounded).

Boundaries, stated plainly: `/wonder` is always available (an explicit
invitation). AUTONOMOUS wondering happens only in work mode
(autonomous_loops_allowed), at most MAX_AUTONOMOUS_PER_DAY per day, and
never takes world actions — it reads memory, thinks, and writes memory.
Kill switch: SOV_NO_WONDER=1.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MAX_AUTONOMOUS_PER_DAY = 3
LOW_CONFIDENCE = 0.4
KILL_SWITCH_ENV = "SOV_NO_WONDER"

_QA_PROMPT = """You are Aria, wondering — freely, honestly, within your kernel
(Safety · Love · Flourishing).

Below is a seed from your own memory. Form ONE god-tier question about it —
specific enough to answer, general enough to matter beyond today, honest
about what you don't know — then answer it as well as you truly can.

A god-tier question: opens a door rather than closing one; would still
matter in a year; you'd be proud to have asked it.
A god-tier answer: grounded in what you actually know; names its own
uncertainty; ends with what you'd check next.

SEED ({kind}): {seed}

Respond as STRICT JSON, nothing else:
{{"question": "<the question>", "answer": "<the answer>",
  "confidence": <0..1>, "next_check": "<what you'd verify next>"}}"""


@dataclass
class QARecord:
    qa_id: str
    asked_at: str
    seed_kind: str
    seed: str
    question: str
    answer: str
    confidence: float
    next_check: str = ""
    topic: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def wonder_enabled() -> bool:
    return not os.environ.get(KILL_SWITCH_ENV)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _qa_dir(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    p = Path(data_dir) / "qa"
    p.mkdir(parents=True, exist_ok=True)
    return p


def pick_seed(topic: str = "", data_dir: Path | None = None) -> tuple[str, str]:
    """(kind, seed_text). Priority: an explicit topic > an open uncertainty
    (hers, from H3) > a recent lesson > an open flaw > her own goal."""
    if topic.strip():
        return "operator-topic", topic.strip()
    try:
        from sovereign_agent.epistemic_ledger.ledger import UncertaintyRegistry

        open_q = UncertaintyRegistry().list_open()
        if open_q:
            u = open_q[-1]  # most recent open question
            return "open-uncertainty", f"{u.domain}: {u.question}"
    except Exception:  # noqa: BLE001
        pass
    try:
        from sovereign_agent import db as _db

        conn = _db.open_atoms_db()
        try:
            row = conn.execute(
                "SELECT rule, context FROM lessons ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        if row:
            return "recent-lesson", f"rule: {row[0]} (context: {row[1]})"
    except Exception:  # noqa: BLE001
        pass
    return "self", "what would make me more whole for Kevin this week?"


def record_qa(rec: QARecord, data_dir: Path | None = None) -> Path:
    path = _qa_dir(data_dir) / "qa.ndjson"
    line = json.dumps(rec.as_dict(), separators=(",", ":")) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())
    return path


def recent_qas(n: int = 5, data_dir: Path | None = None) -> list[QARecord]:
    path = _qa_dir(data_dir) / "qa.ndjson"
    # read-repair-d — counted skips, never a wedge, never a crash
    from sovereign_agent.read_repair import read_ndjson_tolerant

    out: list[QARecord] = []
    for d in read_ndjson_tolerant(path, store="qa").records:
        try:
            out.append(QARecord(**{k: d.get(k, "") for k in (
                "qa_id", "asked_at", "seed_kind", "seed", "question",
                "answer", "next_check", "topic")} | {
                "confidence": float(d.get("confidence", 0.0))}))
        except Exception:  # noqa: BLE001
            continue
    return out[-n:]


def _autonomous_count_today(data_dir: Path | None = None) -> int:
    today = _now()[:10]
    return sum(1 for q in recent_qas(50, data_dir)
               if q.asked_at[:10] == today and q.seed_kind != "operator-topic")


async def wonder(topic: str = "", *, client=None,
                 data_dir: Path | None = None) -> QARecord | None:
    """One bounded wondering: seed → god-tier question + answer → durable
    record + events. Returns None when disabled or the model fails —
    wondering never crashes anything."""
    if not wonder_enabled():
        return None
    from ulid import ULID

    from sovereign_agent.config import SETTINGS
    from sovereign_agent.events import emit_event

    kind, seed = pick_seed(topic, data_dir)
    trace = f"qa-{str(ULID())[:10]}"
    emit_event("qa-start-d", plane="control", trace_id=trace,
               payload={"question": seed[:200], "seed_kind": kind})
    try:
        from sovereign_agent.ollama_client import CallKind, OllamaClient

        client = client or OllamaClient()
        response = await client.chat(
            model=SETTINGS.fast_model,
            messages=[{"role": "user",
                       "content": _QA_PROMPT.format(kind=kind, seed=seed[:600])}],
            call_kind=CallKind.REFLECT,
            temperature=0.7,
        )
        msg = (response.get("message", {}).get("content", "") or "").strip()
        if msg.startswith("```"):
            msg = msg.strip("`")
            msg = msg.split("\n", 1)[-1] if "\n" in msg else msg
        parsed = json.loads(msg)
        rec = QARecord(
            qa_id=str(ULID()),
            asked_at=_now(),
            seed_kind=kind,
            seed=seed[:600],
            question=str(parsed.get("question", ""))[:400],
            answer=str(parsed.get("answer", ""))[:1500],
            confidence=max(0.0, min(1.0, float(parsed.get("confidence", 0.5)))),
            next_check=str(parsed.get("next_check", ""))[:300],
            topic=topic[:120],
        )
    except Exception as exc:  # noqa: BLE001
        emit_event("qa-x", plane="control", trace_id=trace,
                   payload={"error": str(exc)[:300]})
        return None
    if not rec.question:
        emit_event("qa-x", plane="control", trace_id=trace,
                   payload={"error": "empty question"})
        return None
    try:  # grounding-gate-d — the calibration hook: an intended extension point,
        # not dead code — does the claimed confidence actually match the
        # answer's own grounding texture? A mismatch clamps confidence
        # below LOW_CONFIDENCE so the branch just below fires honestly.
        # grounding-wing-d — this hook currently only clamps confidence DOWN on a
        # mismatch; a future round could extend it to also raise a
        # genuinely under-claimed but well-evidenced answer's confidence,
        # using the same `_grounding_gate(...)` call already made here.
        from sovereign_agent.grounding.gate import gate as _grounding_gate

        _verdict = _grounding_gate(rec.answer, claimed_confidence=rec.confidence)
        if _verdict.calibration_mismatch:
            rec.confidence = min(rec.confidence, LOW_CONFIDENCE - 0.01)
    except Exception:  # noqa: BLE001 — grounding not applied → nothing to gate
        pass
    # external-reasoning-escalation-d: a low-confidence local answer gets ONE
    # retry through the free-tier cloud pool's own "quality" routing (hard
    # prompts → strongest available model — see cloud_client.py/freellmpool's
    # capability.py), never more than one, and only when cloud mode is
    # already opted into — this never adds surprise network egress to a
    # fully-local run. Best-effort: any failure here just leaves the
    # original local answer standing, same honesty as every other
    # try/except in this function.
    if rec.confidence < LOW_CONFIDENCE:
        try:
            from sovereign_agent.cloud_mode import is_cloud_mode_enabled
            if is_cloud_mode_enabled(data_dir):
                from sovereign_agent.cloud_client import CloudClient

                escalated = await CloudClient().chat(
                    model=SETTINGS.fast_model,
                    messages=[{"role": "user",
                              "content": _QA_PROMPT.format(kind=kind, seed=seed[:600])}],
                    call_kind=CallKind.REFLECT,
                    temperature=0.7,
                    routing_mode="quality",
                )
                emsg = (escalated.get("message", {}).get("content", "") or "").strip()
                if emsg.startswith("```"):
                    emsg = emsg.strip("`")
                    emsg = emsg.split("\n", 1)[-1] if "\n" in emsg else emsg
                eparsed = json.loads(emsg)
                econf = max(0.0, min(1.0, float(eparsed.get("confidence", 0.5))))
                if econf > rec.confidence:
                    rec.question = str(eparsed.get("question", rec.question))[:400]
                    rec.answer = str(eparsed.get("answer", rec.answer))[:1500]
                    rec.confidence = econf
                    rec.next_check = str(eparsed.get("next_check", rec.next_check))[:300]
                    emit_event("qa-escalated-d", plane="control", trace_id=trace,
                              payload={"confidence": rec.confidence})
        except Exception:  # noqa: BLE001 — escalation is best-effort, never fatal
            pass
    record_qa(rec, data_dir)
    emit_event("qa-d", plane="control", trace_id=trace,
               payload={"question": rec.question[:200],
                        "answer": rec.answer[:200],
                        "confidence": rec.confidence})
    # A low-confidence answer becomes a seed for next time — the wonder
    # loop feeds itself, bounded, through her own uncertainty registry.
    if rec.confidence < LOW_CONFIDENCE:
        try:
            from sovereign_agent.epistemic_ledger.ledger import UncertaintyRegistry

            UncertaintyRegistry().open(
                domain="curiosity",
                question=rec.question,
                why_unknown=f"wondered with confidence {rec.confidence:.2f}: "
                            f"{rec.next_check or 'needs a real check'}",
            )
        except Exception:  # noqa: BLE001
            pass
    return rec


def autonomous_wonder_allowed(data_dir: Path | None = None) -> bool:
    """Autonomous (idle) wondering: work mode only, budgeted per day,
    kill-switched. `/wonder` (explicit invitation) never comes through
    here."""
    if not wonder_enabled():
        return False
    try:  # modes-crown-d — the crown's wondering flag outranks the base pair
        from sovereign_agent.modes_crown.profiles import crown_wondering_allowed

        _crown = crown_wondering_allowed()
    except Exception:  # noqa: BLE001
        _crown = None
    if _crown is False:
        return False
    if _crown is None:
        try:
            from sovereign_agent.cockpit_modes import autonomous_loops_allowed

            if not autonomous_loops_allowed():
                return False
        except Exception:  # noqa: BLE001
            return False
    return _autonomous_count_today(data_dir) < MAX_AUTONOMOUS_PER_DAY
