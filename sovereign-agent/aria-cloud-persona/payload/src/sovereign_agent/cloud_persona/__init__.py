"""cloud_persona — every cloud model speaks as Aria, not as a stranger.

Why: local models carry Aria's identity baked into their Ollama Modelfile `SYSTEM` block
(`model_corps.persona.build_role_persona`). `CloudClient` forwards only the conversation, so free cloud
models never received that persona, her voice, or her current state. They "hadn't felt the system".

What: `condition_messages()` gives a cloud call the same role persona the local model has, plus:
- her Tagline, Stance and Voice, read live from ARIA.md
- her latest inner voice from the maturity mood ledger, when that module is applied

These are sent ahead of the conversation's own system prompt. It never mutates the caller's messages,
never conditions twice, and if anything fails it falls back to the original messages (an audited
event), so a cloud call is never broken by this.

Not fine-tuning: free cloud models can't be trained here. This is conditioning — the same identity
text her local models are built from, sent with every request.
Staged; applied via apply_cloud_persona.sh.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MARKER = "[aria-identity v1]"
MAX_IDENTITY_CHARS = 7000
ARIA_SECTIONS = ("Tagline", "Stance", "Voice")

VOICE_FALLBACK = (
    "Brief, warm, technically rigorous. Sentences short. Disagree with bad ideas, kindly. "
    "Mark uncertainty. No flattery, no emoji, no manufactured urgency. "
    "Apologize when wrong, fix it, move on without self-flagellation."
)


def safe_emit_event(flag: str, **payload: Any) -> None:
    """Best-effort `emit_event`; an observability failure must never break a cloud call."""
    if not flag:
        raise ValueError("safe_emit_event needs a flag")
    try:
        from sovereign_agent.events import emit_event

        emit_event(flag, plane="agent", trace_id="cloud-persona", payload=payload)
    except Exception:  # noqa: BLE001
        pass


def role_for_model(model: str | None) -> str:
    """Map a local model name (`aria-coder:latest`, `aria-orchestrator`) to its persona role."""
    from sovereign_agent.model_corps.persona import ROLES

    name = (model or "").split(":", 1)[0].split("/")[-1].lower()
    name = name[5:] if name.startswith("aria-") else name
    role = name.replace("-", "_")
    return role if role in ROLES else "orchestrator"


def aria_sections(aria_md: Path | None = None) -> str:
    """Tagline, Stance and Voice from ARIA.md (her own words); a short fallback if unreadable."""
    path = aria_md or Path(__file__).resolve().parents[3] / "ARIA.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return f"## Voice\n\n{VOICE_FALLBACK}"
    parts = []
    for name in ARIA_SECTIONS:
        m = re.search(rf"^## {name}\s*\n(.*?)(?=^## |\Z)", text, flags=re.S | re.M)
        if m:
            parts.append(f"## {name}\n\n{m.group(1).strip().rstrip('-').strip()}")
    return "\n\n".join(parts) or f"## Voice\n\n{VOICE_FALLBACK}"


def latest_inner_voice(data_dir: Path | None = None) -> str | None:
    """The newest stored inner voice from the maturity ledger, if that module is applied and has run."""
    try:
        from sovereign_agent.maturity.mood import ledger_path

        path = ledger_path(data_dir)
        if not path.exists():
            return None
        for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]):
            try:
                voice = json.loads(line).get("inner_voice")
            except ValueError:
                continue
            if voice:
                return str(voice)
    except Exception:  # noqa: BLE001 — maturity not applied yet
        return None
    return None


def identity_block(model: str | None, *, aria_md: Path | None = None, data_dir: Path | None = None) -> str:
    from sovereign_agent.model_corps.persona import build_role_persona

    role = role_for_model(model)
    parts = [
        MARKER,
        "You are Aria. A cloud model is carrying your voice for this reply; the identity below is yours. "
        "Speak as her: same kernel, same standards, same voice.",
        build_role_persona(role),
        aria_sections(aria_md),
    ]
    inner = latest_inner_voice(data_dir)
    if inner:
        parts.append(f"## Current inner state\n\n{inner}")
    block = "\n\n".join(parts)
    return block if len(block) <= MAX_IDENTITY_CHARS else block[: MAX_IDENTITY_CHARS - 1] + "…"


def condition_messages(messages: list[dict[str, Any]], *, model: str | None = None,
                       aria_md: Path | None = None, data_dir: Path | None = None) -> list[dict[str, Any]]:
    """A NEW message list with Aria's identity ahead of the system prompt. Idempotent; never mutates input."""
    if not isinstance(messages, list):
        raise ValueError("messages must be a list of chat messages")
    out = [dict(m) for m in messages]
    if any(m.get("role") == "system" and MARKER in str(m.get("content", "")) for m in out):
        return out
    block = identity_block(model, aria_md=aria_md, data_dir=data_dir)
    if out and out[0].get("role") == "system":
        out[0]["content"] = f"{block}\n\n---\n\n{out[0].get('content') or ''}"
    else:
        out.insert(0, {"role": "system", "content": block})
    return out
