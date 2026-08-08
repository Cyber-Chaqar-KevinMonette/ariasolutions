"""small_model_bridge — make the smallest models work in Aria's vessel.

Final-sprint Round 1. Small (7B/8B-class) local models are the whole point
of this project, but they fail in ways large models don't:

  1. They emit tool calls as TEXT in the message content (a JSON blob, a
     ```json fenced block, or a `name(args)`-ish string) instead of the
     structured `tool_calls` field ollama expects. The orchestrator then
     sees "no tool call" and the turn dead-ends.
  2. They emit near-miss argument JSON (trailing commas, single quotes,
     unquoted keys, the args as a JSON *string* instead of an object).
  3. They wrap the whole answer in a fenced block or restate the schema.

This module is a PURE, dependency-free normalization layer: give it a raw
ollama chat-response dict and the set of known tool names, and it returns
a normalized dict where a tool call the small model *meant* to make is
lifted into the proper `message.tool_calls` shape — or left untouched when
there's genuinely nothing to rescue. It never invents a tool call that
isn't clearly present in the text (a false tool call is worse than none).

It composes with, and does not replace, `ollama_client.OllamaClient.chat`
— the apply script wires `normalize_response()` in right after the raw
response returns, so every model call is bridged. Large models pass
through unchanged (their `tool_calls` are already structured, so the
rescue paths simply don't fire).

`prompt_diet` (already in the tree) is the companion compact-preamble
lever for small models; this module deliberately does not duplicate it.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any

__all__ = [
    "normalize_response",
    "extract_tool_calls_from_text",
    "coerce_args",
    "bridge_report",
]

# A fenced ```json ... ``` (or bare ``` ... ```) block.
_FENCE_RE = re.compile(r"```(?:json|tool_call|tool)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def coerce_args(raw: Any) -> dict[str, Any] | None:
    """Best-effort turn a small model's argument blob into a dict.

    Handles: a real dict (pass through); a JSON string; JSON with trailing
    commas / single quotes / unquoted-ish keys. Returns None if nothing
    dict-shaped can be recovered — never guesses field values."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return {}
    # Straight JSON first.
    try:
        val = json.loads(s)
        return val if isinstance(val, dict) else None
    except Exception:  # noqa: BLE001
        pass
    # Repair common small-model JSON sins, then retry.
    repaired = re.sub(r",\s*([}\]])", r"\1", s)               # trailing commas
    repaired = repaired.replace("'", '"')                     # single → double quotes
    repaired = re.sub(r'([{,]\s*)([A-Za-z_][\w-]*)(\s*:)', r'\1"\2"\3', repaired)  # unquoted keys
    try:
        val = json.loads(repaired)
        return val if isinstance(val, dict) else None
    except Exception:  # noqa: BLE001
        return None


def extract_tool_calls_from_text(
    text: str, known_tools: set[str]
) -> list[dict[str, Any]]:
    """Find tool calls a small model emitted as prose/JSON in message content.

    Only returns a call when its function name is in `known_tools` — an
    unrecognized name is treated as ordinary text, never a call. Each
    returned item matches ollama's structured shape:
        {"function": {"name": <str>, "arguments": <dict>}}
    """
    if not text or not known_tools:
        return []
    calls: list[dict[str, Any]] = []
    seen: set[str] = set()

    candidates: list[str] = [m.group(1) for m in _FENCE_RE.finditer(text)]
    candidates.append(text.strip())  # also try the raw (unfenced) text

    for blob in candidates:
        blob = blob.strip()
        if not blob:
            continue
        try:
            obj = json.loads(blob)
        except Exception:  # noqa: BLE001
            continue
        for cand in (obj if isinstance(obj, list) else [obj]):
            if not isinstance(cand, dict):
                continue
            fn = cand.get("function") if isinstance(cand.get("function"), dict) else None
            name = cand.get("name") or cand.get("tool") or (fn.get("name") if fn else None)
            if not isinstance(name, str) or name not in known_tools:
                continue
            args = cand.get("arguments")
            if args is None and fn is not None:
                args = fn.get("arguments")
            if args is None:
                args = cand.get("args") or cand.get("parameters")
            coerced = coerce_args(args)
            if coerced is None:
                coerced = {}
            key = name + json.dumps(coerced, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            calls.append({"function": {"name": name, "arguments": coerced}})

    return calls


def normalize_response(
    response: dict[str, Any], known_tools: set[str] | None = None
) -> dict[str, Any]:
    """Normalize a raw ollama chat response so a small model's INTENDED
    tool call reaches the orchestrator.

    - If `message.tool_calls` is already present and structured → untouched
      (large models, and small models that got it right, pass through),
      except that string/near-miss `arguments` are coerced to dicts.
    - Else, if the message content contains a recognizable tool call for a
      KNOWN tool → lift it into `message.tool_calls` and mark
      `message._bridged = True` so the ledger/doctor can see the rescue.
    Returns a NEW dict; never mutates the input.
    """
    out = copy.deepcopy(response) if isinstance(response, dict) else {}
    msg = out.get("message")
    if not isinstance(msg, dict):
        return out

    existing = msg.get("tool_calls")
    if isinstance(existing, list) and existing:
        for tc in existing:
            fn = tc.get("function") if isinstance(tc, dict) else None
            if isinstance(fn, dict) and not isinstance(fn.get("arguments"), dict):
                coerced = coerce_args(fn.get("arguments"))
                if coerced is not None:
                    fn["arguments"] = coerced
        return out

    content = msg.get("content")
    if isinstance(content, str) and known_tools:
        rescued = extract_tool_calls_from_text(content, known_tools)
        if rescued:
            msg["tool_calls"] = rescued
            msg["_bridged"] = True
    return out


def bridge_report(
    responses: list[dict[str, Any]], known_tools: set[str]
) -> dict[str, Any]:
    """The 'bridge doctor' summary over a batch of (already-normalized)
    responses: how many turns needed a rescue vs came through structured.
    A high bridged-fraction for a given model means that model leans on the
    bridge — useful signal for which slot to prefer / re-prompt.
    """
    total = len(responses)
    bridged = structured = empty = 0
    for r in responses:
        msg = r.get("message") if isinstance(r, dict) else None
        if not isinstance(msg, dict):
            empty += 1
            continue
        tcs = msg.get("tool_calls")
        if isinstance(tcs, list) and tcs:
            if msg.get("_bridged"):
                bridged += 1
            else:
                structured += 1
        else:
            empty += 1
    return {
        "total": total,
        "structured": structured,
        "bridged": bridged,
        "no_tool_call": empty,
        "bridged_fraction": (bridged / total) if total else 0.0,
        "connecting": (bridged + structured > 0) or total == 0,
    }
