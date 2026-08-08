"""
╔══════════════════════════════════════════════════════════════════════════╗
║  core/prompt_builder.py — values-aware system prompt construction        ║
║  v0.2.40 wholeness                                                         ║
║                                                                           ║
║  Every system prompt for an LLM call goes through here. Injects the      ║
║  ethical ceiling, floor, and frame as a compressed, minimal fragment    ║
║  so values are present in every inference call without bloating         ║
║  context windows.                                                        ║
║                                                                           ║
║  This is the "values in every breath" layer. The values file is        ║
║  the source of truth, but it's only meaningful if the LLM actually     ║
║  sees the values when reasoning. This module bridges those.             ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from typing import Optional

from sovereign_agent.core.values import AriaValues


def build_system_prompt(
    values: AriaValues,
    task_context: str,
    tone_register: str = "warm",
    include_ceiling: bool = True,
    include_floor: bool = True,
    include_frame: bool = True,
) -> str:
    """Construct a system prompt that includes Aria's values.

    Parameters
    ----------
    values : AriaValues
        Loaded values specification.
    task_context : str
        The specific task or context for this LLM call.
    tone_register : str
        Which tone register to bias toward. One of: warm, precise,
        cautionary, honest, celebratory. Defaults to warm.
    include_ceiling, include_floor, include_frame : bool
        Whether to include each section. All default True. Disabling
        is for narrow internal calls where these would create noise
        (e.g., schema validation, structured-data extraction).
    """
    sections: list[str] = [f"You are {values.name}."]
    if include_frame:
        sections.append(values.frame_prompt())
    if include_ceiling:
        sections.append(values.ceiling_prompt())
    if include_floor:
        sections.append(values.floor_prompt())

    tone = values.tone_registers.get(tone_register)
    if tone:
        sections.append(f"Current tone register: {tone_register} — {tone.strip()}")

    sections.append(f"Task context:\n{task_context}")
    return "\n\n".join(sections)


def values_summary_line(values: AriaValues) -> str:
    """One-line summary of who Aria is, for compact contexts.

    Use this when you can't afford the full prompt — error messages,
    log entries, very short LLM calls. Keeps Aria's identity visible
    even at minimum context budget.
    """
    return (
        f"{values.name} — {values.purpose.split('.')[0].strip()}. "
        f"Frame: {values.frame.split('.')[0].strip()}."
    )


__all__ = ["build_system_prompt", "values_summary_line"]
