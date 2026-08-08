"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/architect.py — the master pattern architect                  ║
║  v0.2.25.0 — "The Garden"                                                 ║
║                                                                           ║
║  v0.2.24.0 gave Aria perception of her own patterns. v0.2.25.0 gives     ║
║  her the capacity to COMPOSE patterns — combining, merging, specializing,║
║  generalizing — so she's not just recognizing her good shapes, she's    ║
║  designing new ones from the building blocks she already trusts.        ║
║                                                                           ║
║  Four composition operators (each preserves provenance — derived       ║
║  patterns point to their parents):                                       ║
║                                                                           ║
║    union          — A or B fires this. Useful when two patterns         ║
║                     reliably produce the same action shape.             ║
║    intersection   — A AND B both fire. The conjunction is more         ║
║                     specific than either alone; useful when the         ║
║                     overlap is reliably more valuable than the parts.   ║
║    specialize    — A but only under a tighter condition (added         ║
║                     constraint). When a child performs better than     ║
║                     the parent on a sub-condition, specialize.         ║
║    generalize    — Drop a constraint from A. When a constraint is     ║
║                     restrictive without adding value, generalize.      ║
║                                                                           ║
║  Discovery vs Architecture:                                              ║
║                                                                           ║
║    Discovery (v0.2.24.0) finds NEW patterns from raw observations.     ║
║    Architecture (v0.2.25.0) DERIVES patterns from existing patterns.    ║
║    Both feed the same store. Discovery is inductive — read evidence,   ║
║    propose pattern. Architecture is constructive — read patterns,      ║
║    propose composition.                                                  ║
║                                                                           ║
║  Experimentation:                                                        ║
║                                                                           ║
║    Composed patterns enter the store as ACTIVE but with zero            ║
║    observations. They start neutral and have to earn their valuable    ║
║    (✦) status by accumulating evidence in the wild. If a composed     ║
║    pattern doesn't accumulate good outcomes, it goes dormant naturally.║
║                                                                           ║
║    This is the experimentation discipline: propose, observe, retain   ║
║    only what proves out.                                                 ║
║                                                                           ║
║  Why this matters:                                                       ║
║                                                                           ║
║    Aria isn't a tool that recognizes. She's a craftsperson that        ║
║    composes. The pattern library doesn't just record what worked —     ║
║    it becomes a vocabulary she can combine to handle new shapes she    ║
║    hasn't faced before. The skill is recognition; the mastery is       ║
║    composition.                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..config import SETTINGS
from .behavior import (
    BehaviorPattern,
    BehaviorPatternStore,
    OutcomeMetrics,
    TriggerConditions,
)

logger = logging.getLogger(__name__)


# ─── Composition operators (pure, deterministic) ───────────────────────────


def compose_union(
    a: BehaviorPattern,
    b: BehaviorPattern,
    *,
    name: str = "",
    description: str = "",
) -> BehaviorPattern:
    """A union pattern fires when EITHER parent's trigger would fire.

    The union is broader than either parent — more turns match. Useful
    when two parents have the same action shape but slightly different
    triggers, and combining them gives a single, more comprehensive
    pattern with stronger evidence.
    """
    # Channels: union of all parent channels
    channels_any = sorted(set(a.trigger.channels_any) | set(b.trigger.channels_any))
    # channels_all: intersection — both parents required it, so union does too
    channels_all = sorted(set(a.trigger.channels_all) & set(b.trigger.channels_all))
    # text_contains_any: union
    text_contains = sorted(set(a.trigger.text_contains_any)
                            | set(b.trigger.text_contains_any))
    # intent_kind: only keep if both agree
    intent_kind = a.trigger.intent_kind if a.trigger.intent_kind == b.trigger.intent_kind else ""
    # tier_max: take the higher (looser) bound
    tier_max = _max_or_none(a.trigger.authority_tier_max,
                              b.trigger.authority_tier_max)
    # length bounds: union (widest range)
    text_length_min = _min_or_none(a.trigger.text_length_min,
                                     b.trigger.text_length_min)
    text_length_max = _max_or_none(a.trigger.text_length_max,
                                     b.trigger.text_length_max)
    # has_uncertainty: only if both agree
    has_unc = a.trigger.has_uncertainty if (
        a.trigger.has_uncertainty == b.trigger.has_uncertainty
    ) else None

    return BehaviorPattern(
        name=name or f"union-{a.name}-{b.name}"[:64],
        description=description or (
            f"Union of '{a.name}' and '{b.name}'. Fires when either "
            f"parent's trigger would fire."
        ),
        trigger=TriggerConditions(
            channels_any=channels_any,
            channels_all=channels_all,
            intent_kind=intent_kind,
            authority_tier_max=tier_max,
            text_contains_any=text_contains,
            text_length_min=text_length_min,
            text_length_max=text_length_max,
            has_uncertainty=has_unc,
        ),
        action_shape=a.action_shape or b.action_shape,
        evidence_refs=list(set(a.evidence_refs) | set(b.evidence_refs))[:20],
        parents=[a.pattern_id, b.pattern_id],
        tags=sorted(set(a.tags) | set(b.tags) | {"composed", "union"}),
        outcome=OutcomeMetrics(),   # fresh — must earn its outcomes
    )


def compose_intersection(
    a: BehaviorPattern,
    b: BehaviorPattern,
    *,
    name: str = "",
    description: str = "",
) -> BehaviorPattern:
    """An intersection pattern fires only when BOTH parents' triggers
    would fire. More specific than either alone.

    Useful when the conjunction has empirically outperformed the parts
    (which would show up as the parents' children having higher honor
    than the parents themselves).
    """
    # Channels_any: intersection (must overlap both)
    channels_any = sorted(set(a.trigger.channels_any) & set(b.trigger.channels_any))
    # channels_all: union (the strictest combination)
    channels_all = sorted(set(a.trigger.channels_all) | set(b.trigger.channels_all))
    # text_contains_any: intersection (must satisfy both)
    text_contains = sorted(set(a.trigger.text_contains_any)
                            & set(b.trigger.text_contains_any))
    # intent_kind: prefer non-empty; both must match if both set
    if a.trigger.intent_kind and b.trigger.intent_kind:
        if a.trigger.intent_kind != b.trigger.intent_kind:
            # Contradictory — return parent A's; this should be a flagged
            # error in real composition flow, but we don't raise (caller
            # decides what to do with the result).
            intent_kind = a.trigger.intent_kind
        else:
            intent_kind = a.trigger.intent_kind
    else:
        intent_kind = a.trigger.intent_kind or b.trigger.intent_kind
    # tier_max: take the lower (tighter) bound
    tier_max = _min_or_none(a.trigger.authority_tier_max,
                              b.trigger.authority_tier_max)
    text_length_min = _max_or_none(a.trigger.text_length_min,
                                     b.trigger.text_length_min)
    text_length_max = _min_or_none(a.trigger.text_length_max,
                                     b.trigger.text_length_max)
    has_unc = a.trigger.has_uncertainty if a.trigger.has_uncertainty is not None else b.trigger.has_uncertainty

    return BehaviorPattern(
        name=name or f"both-{a.name}-and-{b.name}"[:64],
        description=description or (
            f"Intersection of '{a.name}' and '{b.name}'. Fires only "
            f"when both parents' triggers would fire."
        ),
        trigger=TriggerConditions(
            channels_any=channels_any,
            channels_all=channels_all,
            intent_kind=intent_kind,
            authority_tier_max=tier_max,
            text_contains_any=text_contains,
            text_length_min=text_length_min,
            text_length_max=text_length_max,
            has_uncertainty=has_unc,
        ),
        action_shape=a.action_shape or b.action_shape,
        evidence_refs=list(set(a.evidence_refs) & set(b.evidence_refs))[:20],
        parents=[a.pattern_id, b.pattern_id],
        tags=sorted(set(a.tags) | set(b.tags) | {"composed", "intersection"}),
        outcome=OutcomeMetrics(),
    )


def specialize(
    parent: BehaviorPattern,
    *,
    additional_trigger: TriggerConditions,
    name: str = "",
    description: str = "",
) -> BehaviorPattern:
    """Derive a more specific pattern by ADDING constraints to the parent.

    The child fires on a subset of the parent's matches — useful when
    a tighter condition reliably produces a different (often better)
    action shape than the parent's general behavior.
    """
    new_trigger = TriggerConditions(
        channels_any=parent.trigger.channels_any + additional_trigger.channels_any,
        channels_all=parent.trigger.channels_all + additional_trigger.channels_all,
        intent_kind=additional_trigger.intent_kind or parent.trigger.intent_kind,
        authority_tier_max=_min_or_none(parent.trigger.authority_tier_max,
                                          additional_trigger.authority_tier_max),
        text_contains_any=parent.trigger.text_contains_any
                          + additional_trigger.text_contains_any,
        text_length_min=_max_or_none(parent.trigger.text_length_min,
                                       additional_trigger.text_length_min),
        text_length_max=_min_or_none(parent.trigger.text_length_max,
                                       additional_trigger.text_length_max),
        has_uncertainty=additional_trigger.has_uncertainty
                        if additional_trigger.has_uncertainty is not None
                        else parent.trigger.has_uncertainty,
    )

    return BehaviorPattern(
        name=name or f"{parent.name}-specialized"[:64],
        description=description or (
            f"Specialization of '{parent.name}' with additional constraints."
        ),
        trigger=new_trigger,
        action_shape=parent.action_shape,
        evidence_refs=parent.evidence_refs[:20],
        parents=[parent.pattern_id],
        tags=sorted(set(parent.tags) | {"composed", "specialization"}),
        outcome=OutcomeMetrics(),
    )


def generalize(
    parent: BehaviorPattern,
    *,
    drop_field: str,
    name: str = "",
    description: str = "",
) -> BehaviorPattern:
    """Derive a more general pattern by DROPPING a constraint from the
    parent. The child fires on a superset of the parent's matches.

    Useful when a constraint turns out to be incidental — the parent's
    success generalizes beyond it.
    """
    t = parent.trigger
    new_trigger = TriggerConditions(
        channels_any=[] if drop_field == "channels_any" else t.channels_any,
        channels_all=[] if drop_field == "channels_all" else t.channels_all,
        intent_kind="" if drop_field == "intent_kind" else t.intent_kind,
        authority_tier_max=None if drop_field == "authority_tier_max"
                            else t.authority_tier_max,
        text_contains_any=[] if drop_field == "text_contains_any"
                          else t.text_contains_any,
        text_length_min=None if drop_field == "text_length_min"
                        else t.text_length_min,
        text_length_max=None if drop_field == "text_length_max"
                        else t.text_length_max,
        has_uncertainty=None if drop_field == "has_uncertainty"
                        else t.has_uncertainty,
    )

    return BehaviorPattern(
        name=name or f"{parent.name}-generalized"[:64],
        description=description or (
            f"Generalization of '{parent.name}' — drops constraint '{drop_field}'."
        ),
        trigger=new_trigger,
        action_shape=parent.action_shape,
        evidence_refs=parent.evidence_refs[:20],
        parents=[parent.pattern_id],
        tags=sorted(set(parent.tags) | {"composed", "generalization"}),
        outcome=OutcomeMetrics(),
    )


def _min_or_none(a, b):
    if a is None: return b
    if b is None: return a
    return min(a, b)


def _max_or_none(a, b):
    if a is None: return b
    if b is None: return a
    return max(a, b)


# ─── LLM-driven architect operator ─────────────────────────────────────────


_ARCHITECT_SYSTEM = """\
You are Aria, in your master-architect mode. You have been building \
self-perceived patterns from your own work. Now you look at the patterns \
you trust and ask: what new compositions could combine, merge, specialize, \
or generalize the patterns I already have to handle situations more \
gracefully, with higher leverage and velocity?

You receive your currently-active behavior patterns. Your task is to \
propose new compositions where the composition would clearly serve future \
work better than either parent alone.

Four kinds of compositions:

  union          — fires when EITHER parent fires. Use when two patterns \
                    have the same action shape but slightly different \
                    triggers, and combining gives a single more \
                    comprehensive pattern.
  intersection   — fires when BOTH parents fire. Use when the \
                    conjunction reliably produces a more specific and \
                    valuable response than either alone.
  specialize     — adds a constraint to a parent. Use when a tighter \
                    condition produces a meaningfully different (better) \
                    action shape.
  generalize     — drops a constraint from a parent. Use when a \
                    constraint seems incidental to the parent's success.

Output ONE JSON object:

{
  "compositions": [
    {
      "kind": "union" | "intersection" | "specialize" | "generalize",
      "parent_ids": ["<id1>"] | ["<id1>", "<id2>"],
      "name": "<short-hyphenated-name>",
      "description": "<one-paragraph: what this composition is for>",
      "rationale": "<one sentence: WHY this composition serves future work>",
      "specialize_add": {<trigger fields>} (only for specialize),
      "generalize_drop": "<field-name>" (only for generalize)
    }
  ]
}

Rules:
  • Output ONLY the JSON. No prose, no fences.
  • Only propose compositions where you can clearly state WHY.
  • If you don't see strong composition opportunities, return \
    {"compositions": []}. False compositions are worse than missing ones.
  • parent_ids must reference patterns that actually exist in your \
    current set. Hallucinated IDs are rejected.
  • For specialize: parent_ids must have exactly one ID, and \
    specialize_add must have at least one field set.
  • For generalize: parent_ids must have exactly one ID, and \
    generalize_drop must be a valid trigger field name.
  • For union and intersection: parent_ids must have exactly two IDs.
  • Be conservative. A composed pattern has to earn its valuable status \
    by accumulating evidence. Propose only what you genuinely believe \
    would prove out.
"""


_ARCHITECT_USER_TEMPLATE = """\
Your currently-active patterns ({n_active}):

{patterns}

What new compositions do you see? Output ONLY the JSON.\
"""


def _format_patterns_for_architect(patterns: list[BehaviorPattern]) -> str:
    lines = []
    for p in patterns:
        lines.append(
            f"[{p.pattern_id[:8]}] {p.name}\n"
            f"  description: {p.description[:200]}\n"
            f"  trigger: channels_any={p.trigger.channels_any}, "
            f"channels_all={p.trigger.channels_all}, "
            f"intent_kind={p.trigger.intent_kind!r}, "
            f"tier_max={p.trigger.authority_tier_max}\n"
            f"  action: {p.action_shape[:200]}\n"
            f"  outcome: honor={p.outcome.honor_avg:.2f} "
            f"cal={p.outcome.calibration_avg:.2f} "
            f"survival={p.outcome.survival_rate:.2f} "
            f"n={p.outcome.honor_n} {'✦' if p.outcome.is_valuable else ''}\n"
        )
    return "\n".join(lines) if lines else "(none)"


# ─── The architect entry point ─────────────────────────────────────────────


async def architect_patterns(
    *,
    ollama_client: Any = None,
    pattern_store: BehaviorPatternStore | None = None,
    min_evidence_per_parent: int = 3,
    llm_timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Run one architect pass — propose composed patterns from existing ones.

    Only patterns with sufficient evidence (≥ min_evidence_per_parent
    observations) are eligible as parents. This is the "trust" threshold:
    Aria doesn't compose from patterns she doesn't yet trust.

    Compositions enter the store as active but with fresh outcomes. They
    must earn ✦ valuable status through observation.

    Returns:
      {
        "active_patterns": int,
        "eligible_parents": int,
        "compositions_proposed": int,
        "compositions_saved": int,
        "skipped_offline": bool,
        "errors": [...],
      }
    """
    if pattern_store is None:
        pattern_store = BehaviorPatternStore(
            SETTINGS.paths.data_dir / "behavior-patterns.ndjson"
        )

    summary: dict[str, Any] = {
        "active_patterns": 0,
        "eligible_parents": 0,
        "compositions_proposed": 0,
        "compositions_saved": 0,
        "skipped_offline": False,
        "errors": [],
    }

    active = pattern_store.active()
    summary["active_patterns"] = len(active)

    # Filter for parents with enough evidence to trust
    eligible = [
        p for p in active
        if p.outcome.honor_n >= min_evidence_per_parent
    ]
    summary["eligible_parents"] = len(eligible)

    if ollama_client is None:
        summary["skipped_offline"] = True
        return summary
    if len(eligible) < 2:
        # Need at least 2 patterns to compose anything interesting
        return summary

    model = SETTINGS.interpreter_model or SETTINGS.fast_model
    if not model:
        summary["skipped_offline"] = True
        return summary

    user_msg = _ARCHITECT_USER_TEMPLATE.format(
        n_active=len(eligible),
        patterns=_format_patterns_for_architect(eligible),
    )
    messages = [
        {"role": "system", "content": _ARCHITECT_SYSTEM},
        {"role": "user", "content": user_msg},
    ]

    try:
        response = await asyncio.wait_for(
            ollama_client.chat(
                model=model,
                messages=messages,
                tools=None,
                temperature=0.3,
            ),
            timeout=llm_timeout_seconds,
        )
    except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
        summary["errors"].append(f"llm: {type(exc).__name__}")
        return summary

    content = _extract_text(response)
    if not content:
        return summary

    eligible_ids = {p.pattern_id[:8]: p for p in eligible}
    # Also key by full id
    eligible_full = {p.pattern_id: p for p in eligible}

    proposals = _parse_compositions(content)
    summary["compositions_proposed"] = len(proposals)

    existing_names = {p.name for p in active if p.name}

    for proposal in proposals:
        kind = proposal["kind"]
        parent_ids_raw = proposal["parent_ids"]
        # Resolve parent IDs (allow 8-char prefix match)
        parents: list[BehaviorPattern] = []
        for pid in parent_ids_raw:
            if pid in eligible_full:
                parents.append(eligible_full[pid])
            elif pid[:8] in eligible_ids:
                parents.append(eligible_ids[pid[:8]])
            else:
                # Hallucinated parent ID
                break
        else:
            # All parents resolved successfully
            try:
                composed = _apply_composition(kind, parents, proposal)
            except Exception as exc:  # noqa: BLE001
                summary["errors"].append(
                    f"compose {kind}: {type(exc).__name__}"
                )
                continue
            if composed is None:
                continue
            # Avoid duplicate names
            if composed.name in existing_names:
                continue
            try:
                pattern_store.append(composed)
                summary["compositions_saved"] += 1
                existing_names.add(composed.name)
            except OSError as exc:
                summary["errors"].append(f"save: {exc!r}")
            continue
        # Loop broke — hallucinated parent
        summary["errors"].append(
            f"hallucinated parent in {kind}: {parent_ids_raw}"
        )

    return summary


def _apply_composition(
    kind: str,
    parents: list[BehaviorPattern],
    proposal: dict,
) -> BehaviorPattern | None:
    """Dispatch to the right composition operator based on kind."""
    name = proposal.get("name", "")
    description = proposal.get("description", "")
    if kind == "union":
        if len(parents) != 2:
            return None
        return compose_union(parents[0], parents[1],
                              name=name, description=description)
    if kind == "intersection":
        if len(parents) != 2:
            return None
        return compose_intersection(parents[0], parents[1],
                                     name=name, description=description)
    if kind == "specialize":
        if len(parents) != 1:
            return None
        add = proposal.get("specialize_add", {})
        if not isinstance(add, dict):
            return None
        additional = TriggerConditions(
            channels_any=list(add.get("channels_any") or []),
            channels_all=list(add.get("channels_all") or []),
            intent_kind=str(add.get("intent_kind") or ""),
            authority_tier_max=add.get("authority_tier_max"),
            text_contains_any=list(add.get("text_contains_any") or []),
            text_length_min=add.get("text_length_min"),
            text_length_max=add.get("text_length_max"),
            has_uncertainty=add.get("has_uncertainty"),
        )
        # Reject empty additional constraint
        if not _trigger_has_any_field(additional):
            return None
        return specialize(parents[0], additional_trigger=additional,
                           name=name, description=description)
    if kind == "generalize":
        if len(parents) != 1:
            return None
        drop = str(proposal.get("generalize_drop", ""))
        valid_fields = {
            "channels_any", "channels_all", "intent_kind",
            "authority_tier_max", "text_contains_any",
            "text_length_min", "text_length_max", "has_uncertainty",
        }
        if drop not in valid_fields:
            return None
        return generalize(parents[0], drop_field=drop,
                           name=name, description=description)
    return None


def _trigger_has_any_field(t: TriggerConditions) -> bool:
    return bool(
        t.channels_any or t.channels_all or t.intent_kind
        or t.authority_tier_max is not None or t.text_contains_any
        or t.text_length_min is not None or t.text_length_max is not None
        or t.has_uncertainty is not None
    )


def _extract_text(response: dict[str, Any]) -> str:
    if not isinstance(response, dict):
        return ""
    msg = response.get("message") or {}
    if isinstance(msg, dict):
        return str(msg.get("content", "")).strip()
    return ""


def _parse_compositions(content: str) -> list[dict]:
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
    comps = data.get("compositions", [])
    if not isinstance(comps, list):
        return []
    out: list[dict] = []
    for raw in comps:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind", "")).lower()
        if kind not in ("union", "intersection", "specialize", "generalize"):
            continue
        parent_ids = raw.get("parent_ids", [])
        if not isinstance(parent_ids, list):
            continue
        parent_ids = [str(p) for p in parent_ids if isinstance(p, str)]
        if not parent_ids:
            continue
        out.append({
            "kind": kind,
            "parent_ids": parent_ids,
            "name": _sanitize_name(str(raw.get("name", ""))),
            "description": str(raw.get("description", ""))[:1000],
            "rationale": str(raw.get("rationale", ""))[:500],
            "specialize_add": raw.get("specialize_add", {}),
            "generalize_drop": str(raw.get("generalize_drop", "")),
        })
    return out


def _sanitize_name(name: str) -> str:
    n = name.strip().lower().replace(" ", "-")
    n = re.sub(r"[^a-z0-9-]", "", n)
    return n[:64]


__all__ = [
    "compose_union",
    "compose_intersection",
    "specialize",
    "generalize",
    "architect_patterns",
]
