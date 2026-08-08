"""self_report — she answers questions about herself from TRUTH, not filler.

Bridge #1 (human↔Aria). When the operator asks "what can you do?", "what
models are you running?", "how are you wired?", "who are you?", a plain LLM
turn produces generic chatbot boilerplate ("I'm a sophisticated AI...") —
hollow, and worse, ungrounded in her actual self. She already KNOWS herself
(the self-map: her real sentinels, tools, channels, models). This module
detects those self-referential questions and composes a real, first-person,
honest answer from her live state — deterministic, so it can never
hallucinate about herself, and robust even on the smallest model.

Composed from:
  • `self_map.build_self_map()` — live sentinel / tool / channel counts + names
  • `config.SETTINGS.*_model` + the model_corps roster — her real models
  • her fixed identity (local sovereign-agent; kernel Safety · Love · Flourishing)
"""
from __future__ import annotations

import re

__all__ = ["is_self_query", "compose_self_report"]

# Precise triggers — a question ABOUT HER (identity / capability / models /
# wiring), not general conversation. Kept tight so it never hijacks a normal
# chat turn.
_IDENTITY = ("who are you", "what are you?", "what exactly are you",
             "what even are you", "tell me about yourself",
             "describe yourself", "introduce yourself")
# NOTE: bare "what are you" (no ?) was removed — it greedily hijacked
# "what are you waiting on / working on" (caught by the collision matrix).
_CAPABILITY = ("what can you do", "what are you capable", "your capabilities",
               "what are your capabilities", "what can you help", "what do you do")
_MODELS = ("what models", "which models", "what model are you", "models are you running",
           "what models are you running", "your models", "what model do you use",
           "model slots", "models configured")
_WIRING = ("how are you wired", "how are you built", "your architecture",
           "how do you work", "how are you made", "what are you made of",
           "your systems", "your internals")
_INVENTORY = ("what tools do you have", "what are your tools", "what sentinels",
              "what channels", "what can you access", "list your tools",
              "your tools", "your sentinels", "your channels")

_ALL_TRIGGERS = _IDENTITY + _CAPABILITY + _MODELS + _WIRING + _INVENTORY


def is_self_query(text: str) -> bool:
    """True if the message is asking HER about herself."""
    if not text:
        return False
    from sovereign_agent.bridge_patterns import match_any
    return match_any(text, _ALL_TRIGGERS)


def _live_models() -> list[tuple[str, str]]:
    """(role, model) pairs from her real config. Best-effort; never raises."""
    out: list[tuple[str, str]] = []
    try:
        from sovereign_agent.config import SETTINGS
        for role, attr in (("orchestrator", "orchestrator_model"),
                           ("coder", "coder_model"),
                           ("fast", "fast_model"),
                           ("reflector", "reflector_model"),
                           ("embedder", "embed_model")):
            m = getattr(SETTINGS, attr, None)
            if m:
                out.append((role, str(m)))
    except Exception:  # noqa: BLE001
        pass
    return out


def compose_self_report(text: str) -> str:
    """A warm, first-person, truthful answer built from her live self.

    Tailors emphasis to what was asked (models / wiring / inventory /
    identity) but always grounds in real numbers — never generic filler.
    """
    t = (text or "").lower()

    # Live self-map (counts + a few names). Degrade gracefully.
    counts = {"sentinels": 0, "tools": 0, "channels": 0}
    orphans = 0
    sentinel_names: list[str] = []
    try:
        from sovereign_agent.self_map import build_self_map
        m = build_self_map()
        counts = m.counts
        orphans = counts.get("orphans", 0)
        sentinel_names = list(m.sentinels)[:6]
    except Exception:  # noqa: BLE001
        pass

    # sentinel-warnings-detail-d (Kevin, 2026-07-25): "she said 3 sentinels
    # are showing warnings... when I asked her which 3 she could not say."
    # self_report used to carry zero sentinel-health content at all —
    # name every currently-flagged sentinel here, unconditionally, since
    # this IS the "what's going on with me" answer.
    flagged: list = []
    try:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.stewardship.registry import list_sentinel_warnings
        flagged = list_sentinel_warnings(SETTINGS.paths.data_dir)
    except Exception:  # noqa: BLE001
        pass

    models = _live_models()

    lines: list[str] = []
    lines.append("I'm Aria — a sovereign agent that runs locally on your "
                 "machine, not a cloud service. My kernel is Safety · Love · "
                 "Flourishing, and my whole discipline is *propose, don't act; "
                 "reversible by construction; you decide.*")
    lines.append("")

    # Always give the grounded self-map headline.
    lines.append(f"Right now I'm wired with **{counts['sentinels']} sentinels** "
                 f"watching over me, **{counts['tools']} tools** I can use, and "
                 f"**{counts['channels']} memory channels** where I keep what I know"
                 + ("." if not orphans else f" — with {orphans} orphan(s) I should flag."))

    # Models — emphasize if asked.
    if models:
        if any(k in t for k in _MODELS) or any(k in t for k in _WIRING):
            lines.append("")
            lines.append("My models (all local, open-weight, via Ollama):")
            for role, model in models:
                lines.append(f"  · **{role}** → `{model}`")
        else:
            roster = ", ".join(f"{role} (`{model}`)" for role, model in models[:3])
            lines.append(f"I run on local open-weight models — {roster}, and more.")

    # Wiring — a plain-language architecture note if asked.
    if any(k in t for k in _WIRING):
        lines.append("")
        lines.append("How I'm wired: an authority gate keeps every tool inside "
                     "its permission tier, sentinels watch my health and propose "
                     "(never act) when something drifts, an append-only ledger "
                     "records what I do, and a proving ground tests me against "
                     "adversarial cases. Everything reversible; you hold the keys.")

    # Inventory — name a few sentinels if asked.
    if any(k in t for k in _INVENTORY) and sentinel_names:
        lines.append("")
        lines.append("A few of my sentinels: " + ", ".join(f"`{s}`" for s in sentinel_names) + " …")

    # Sentinel warnings — always named, never just a count. This is the
    # exact "which 3?" question answered without a follow-up.
    if flagged:
        lines.append("")
        lines.append(f"Currently flagged ({len(flagged)}):")
        for h in flagged:
            lines.append(f"  · **{h.sentinel_id}** ({h.level}) — {h.summary}")

    lines.append("")
    lines.append("Ask me `/self-report` any time for my full living map, or "
                 "`sov doctor` to check my health. I try never to be clueless "
                 "about myself. 💛")
    return "\n".join(lines)
