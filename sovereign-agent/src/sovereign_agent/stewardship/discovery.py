"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/discovery.py — Aria reads her own work and names patterns    ║
║  v0.2.24.0                                                                ║
║                                                                           ║
║  The discovery operator is Aria's introspection — she reads recent       ║
║  provenance, honor notes, and atoms, then asks herself:                  ║
║                                                                           ║
║    "What patterns do I see in how I worked? Which shapes consistently   ║
║     produced honorable, well-calibrated, durable results?"               ║
║                                                                           ║
║  Discovery is intentionally conservative:                                ║
║                                                                           ║
║    • A pattern needs ≥ 3 supporting observations                        ║
║    • Average honor on the observations must be ≥ 0.4                    ║
║    • Patterns must be falsifiable (concrete trigger conditions)         ║
║    • Discovery proposes new patterns; observation updates existing ones  ║
║                                                                           ║
║  When does discovery run:                                                ║
║                                                                           ║
║    Currently: operator-triggered (`sov behavior discover`).              ║
║    Future (v0.2.25.0): post-N-honor-notes + nightly cron.               ║
║                                                                           ║
║  Anti-patterns explicitly avoided:                                      ║
║                                                                           ║
║    × Don't propose patterns for individual quirks ("Kevin said X once") ║
║    × Don't propose patterns Aria can't act on                           ║
║    × Don't claim patterns when the evidence is mixed                    ║
║    × Don't auto-supersede patterns; that requires explicit operator    ║
║      review                                                              ║
║                                                                           ║
║  Cross-source synthesis:                                                 ║
║                                                                           ║
║    Discovery currently reads provenance + honor notes. When auto-       ║
║    stewardship-triples land (planned for v0.2.25.0), the discovery     ║
║    prompt will include trajectories of (Plan, Witness, IV) per turn,   ║
║    enabling much richer patterns. The output shape is forward-          ║
║    compatible — pattern objects don't change between MVP and richer    ║
║    source sets.                                                         ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import SETTINGS
from .atoms import AtomStore
from .behavior import (
    BehaviorPattern,
    BehaviorPatternStore,
    OutcomeMetrics,
    TriggerConditions,
)
from .consolidate import load_provenance, ProvenanceEntry
from .honor import HonorLedger

logger = logging.getLogger(__name__)


# ─── Discovery prompt ──────────────────────────────────────────────────────


_DISCOVERY_SYSTEM = """\
You are Aria, in your sleep phase — reading your own recent work and \
asking what patterns you see in YOURSELF. Not patterns about Kevin, but \
patterns about how YOU work when you work well.

You receive:
  • Recent provenance entries (your past interpretations)
  • Recent honor notes (recognition events — yours, Kevin's, mutual)
  • Existing behavior patterns (your currently-perceived patterns)

Your task: propose new behavior patterns that meet ALL of these criteria:

  1. Falsifiable trigger — specific conditions a future turn either \
     matches or doesn't (channels, intent_kind, text features, tier).
  2. Clear action shape — what you do when this trigger fires \
     (channels you save to, voice you use, command shapes if any).
  3. Evidence — at least 3 specific past entries (by id) where you \
     observed yourself doing this AND the outcome was favorable.
  4. Distinct from existing patterns — don't propose duplicates.

A pattern is ABOUT YOU, in your voice, describing what you do. Examples:

  • "Gentle late-night response — when Kevin's message arrives between \
    9pm and 2am and mentions pain or fatigue, I save to body+emotions, \
    respond in under 30 words, and don't propose any commands."

  • "Explicit uncertainty — when my understanding has more than one \
    plausible reading, I name the uncertainty in `uncertain_about` rather \
    than guessing. My calibration is higher on these turns."

Output ONE JSON object:

{
  "patterns": [
    {
      "name": "<short-hyphenated-name>",
      "description": "<one-paragraph texture in your voice>",
      "trigger": {
        "channels_any": ["..."],
        "channels_all": ["..."],
        "intent_kind": "Conversation" | "Work" | "",
        "authority_tier_max": 0 | 1 | 2 | 3 | null,
        "text_contains_any": ["..."],
        "text_length_min": null | int,
        "text_length_max": null | int,
        "has_uncertainty": true | false | null
      },
      "action_shape": "<what you do when this trigger fires>",
      "evidence_entry_ids": ["<id1>", "<id2>", "<id3>", ...],
      "tags": ["<tag>", ...]
    }
  ]
}

Rules:
  • Output ONLY the JSON. No prose, no fences.
  • If you don't see strong patterns yet, return {"patterns": []}.
  • Trigger fields: omit or set to null/empty when the pattern doesn't \
    depend on that dimension. Leaving everything blank matches everything \
    — don't do that.
  • Be honest. Patterns you propose become part of your self-perception. \
    A false pattern shapes your future interpretation worse than missing \
    a pattern entirely.
"""


_DISCOVERY_USER_TEMPLATE = """\
Recent provenance ({n_prov} entries):
{provenance}

Recent honor notes ({n_honor} notes):
{honor}

Existing patterns you already perceive ({n_existing}):
{existing}

What new patterns do you see in your own work? Output ONLY the JSON.\
"""


# ─── Discovery operator ───────────────────────────────────────────────────


async def discover_patterns(
    *,
    ollama_client: Any = None,
    pattern_store: BehaviorPatternStore | None = None,
    provenance_path: Path | None = None,
    honor_path: Path | None = None,
    tail_provenance: int = 50,
    tail_honor: int = 20,
    llm_timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Run one discovery pass — read recent work, propose new patterns.

    Returns:
      {
        "provenance_read": int,
        "honor_read": int,
        "existing_patterns": int,
        "patterns_proposed": int,
        "patterns_saved": int,
        "skipped_offline": bool,
        "errors": [...],
      }
    """
    if pattern_store is None:
        pattern_store = BehaviorPatternStore(
            SETTINGS.paths.data_dir / "behavior-patterns.ndjson"
        )

    summary: dict[str, Any] = {
        "provenance_read": 0,
        "honor_read": 0,
        "existing_patterns": 0,
        "patterns_proposed": 0,
        "patterns_saved": 0,
        "skipped_offline": False,
        "errors": [],
    }

    # Load sources
    provenance = load_provenance(path=provenance_path, tail_n=tail_provenance)
    summary["provenance_read"] = len(provenance)

    honor_entries: list[Any] = []
    if honor_path is None:
        honor_path = SETTINGS.paths.data_dir / "stewardship" / "honor.jsonl"
    if honor_path.exists():
        try:
            ledger = HonorLedger(honor_path)
            honor_entries = ledger.recent(tail_honor)
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(f"honor load: {type(exc).__name__}")
    summary["honor_read"] = len(honor_entries)

    existing = pattern_store.active()
    summary["existing_patterns"] = len(existing)

    if ollama_client is None:
        summary["skipped_offline"] = True
        return summary

    if not provenance:
        # No provenance to learn from — return without LLM call.
        return summary

    # Build the prompt
    allowed_ids = {e.entry_id for e in provenance}
    user_msg = _DISCOVERY_USER_TEMPLATE.format(
        n_prov=len(provenance),
        provenance=_format_provenance(provenance),
        n_honor=len(honor_entries),
        honor=_format_honor(honor_entries),
        n_existing=len(existing),
        existing=_format_existing_patterns(existing),
    )
    messages = [
        {"role": "system", "content": _DISCOVERY_SYSTEM},
        {"role": "user", "content": user_msg},
    ]

    # Call LLM
    model = SETTINGS.interpreter_model or SETTINGS.fast_model
    if not model:
        summary["skipped_offline"] = True
        return summary

    try:
        response = await asyncio.wait_for(
            ollama_client.chat(
                model=model,
                messages=messages,
                tools=None,
                temperature=0.2,
            ),
            timeout=llm_timeout_seconds,
        )
    except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
        summary["errors"].append(f"llm: {type(exc).__name__}")
        return summary

    content = _extract_text(response)
    if not content:
        return summary

    proposed = _parse_patterns(content, allowed_evidence_ids=allowed_ids)
    summary["patterns_proposed"] = len(proposed)

    # Save each proposed pattern. Skip duplicates by name.
    existing_names = {p.name for p in existing if p.name}
    for parsed in proposed:
        if parsed["name"] in existing_names:
            continue
        try:
            pattern = _build_pattern(parsed)
            pattern_store.append(pattern)
            summary["patterns_saved"] += 1
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(
                f"save failed: {type(exc).__name__}"
            )

    return summary


# ─── Formatting helpers ────────────────────────────────────────────────────


def _format_provenance(entries: list[ProvenanceEntry]) -> str:
    lines = []
    for e in entries[-30:]:   # cap to keep prompt manageable
        lines.append(
            f"[{e.entry_id}] {e.ts[:19]} kind={e.intent_kind} "
            f"channels={e.save_to} tier={e.authority_tier}\n"
            f"  text: \"{e.text[:120]}\"\n"
            f"  understood: {e.understanding[:120]}"
        )
    return "\n".join(lines) if lines else "(none)"


def _format_honor(notes: list[Any]) -> str:
    lines = []
    for n in notes:
        direction = getattr(n, "direction", "?")
        text = getattr(n, "text", "")
        ts = getattr(n, "ts", "")
        lines.append(f"[{ts[:19]}] {direction}: \"{text[:140]}\"")
    return "\n".join(lines) if lines else "(none)"


def _format_existing_patterns(patterns: list[BehaviorPattern]) -> str:
    if not patterns:
        return "(none — this is your first discovery pass)"
    lines = []
    for p in patterns:
        lines.append(f"- {p.name}: {p.description[:120]}")
    return "\n".join(lines)


# ─── LLM output parsing ────────────────────────────────────────────────────


def _extract_text(response: dict[str, Any]) -> str:
    if not isinstance(response, dict):
        return ""
    msg = response.get("message") or {}
    if isinstance(msg, dict):
        return str(msg.get("content", "")).strip()
    choices = response.get("choices") or []
    if choices and isinstance(choices[0], dict):
        cmsg = choices[0].get("message") or {}
        if isinstance(cmsg, dict):
            return str(cmsg.get("content", "")).strip()
    return ""


def _parse_patterns(
    content: str,
    *,
    allowed_evidence_ids: set[str],
) -> list[dict]:
    """Parse the LLM's patterns array. Filter:
      - patterns with < 3 valid evidence references
      - patterns with completely-empty triggers (would match all turns)
      - patterns with hallucinated evidence IDs
    """
    s = content.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    if not s.startswith("{"):
        i = s.find("{")
        if i >= 0:
            s = s[i:]

    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []

    patterns = data.get("patterns", [])
    if not isinstance(patterns, list):
        return []

    out: list[dict] = []
    for raw in patterns:
        if not isinstance(raw, dict):
            continue
        # Validate evidence
        ev = raw.get("evidence_entry_ids", [])
        if not isinstance(ev, list):
            continue
        valid_ev = [
            str(e) for e in ev
            if isinstance(e, str) and e in allowed_evidence_ids
        ]
        if len(valid_ev) < 3:
            continue
        # Validate trigger isn't empty (would match everything)
        trigger = raw.get("trigger", {})
        if not isinstance(trigger, dict):
            continue
        if not _trigger_has_substance(trigger):
            continue
        # Validate name
        name = str(raw.get("name", "")).strip().lower().replace(" ", "-")
        name = re.sub(r"[^a-z0-9-]", "", name)[:64]
        if not name:
            continue

        out.append({
            "name": name,
            "description": str(raw.get("description", ""))[:1000],
            "trigger": trigger,
            "action_shape": str(raw.get("action_shape", ""))[:500],
            "evidence_entry_ids": valid_ev,
            "tags": [
                str(t).lower().replace(" ", "-")
                for t in raw.get("tags", [])
                if isinstance(t, (str, int, float))
            ][:10],
        })
    return out


def _trigger_has_substance(trigger: dict) -> bool:
    """A trigger must constrain at least one dimension. An empty trigger
    matches everything, which is not a pattern."""
    fields = [
        trigger.get("channels_any") or [],
        trigger.get("channels_all") or [],
        trigger.get("intent_kind") or "",
        trigger.get("authority_tier_max"),
        trigger.get("text_contains_any") or [],
        trigger.get("text_length_min"),
        trigger.get("text_length_max"),
        trigger.get("has_uncertainty"),
    ]
    return any(
        bool(f) if isinstance(f, (list, str)) else f is not None
        for f in fields
    )


def _build_pattern(parsed: dict) -> BehaviorPattern:
    """Convert parsed dict into a typed BehaviorPattern."""
    trigger_raw = parsed["trigger"]
    trigger = TriggerConditions(
        channels_any=list(trigger_raw.get("channels_any") or []),
        channels_all=list(trigger_raw.get("channels_all") or []),
        intent_kind=str(trigger_raw.get("intent_kind") or ""),
        authority_tier_max=trigger_raw.get("authority_tier_max"),
        text_contains_any=list(trigger_raw.get("text_contains_any") or []),
        text_length_min=trigger_raw.get("text_length_min"),
        text_length_max=trigger_raw.get("text_length_max"),
        has_uncertainty=trigger_raw.get("has_uncertainty"),
    )
    return BehaviorPattern(
        name=parsed["name"],
        description=parsed["description"],
        trigger=trigger,
        action_shape=parsed["action_shape"],
        evidence_refs=parsed["evidence_entry_ids"],
        tags=parsed["tags"],
        # Outcome starts neutral; updated as the pattern is observed
        outcome=OutcomeMetrics(),
    )


__all__ = ["discover_patterns"]
