"""Authority tiering. Architecture §7.

The dispatch gate is the load-bearing safety mechanism. Tools above the
mode's tier ceiling are NOT INCLUDED in the available list passed to the model.
A model cannot call a tool it doesn't know about.

Tier definitions:
  0 = read-only / inspection
  1 = scoped writes (sandbox or memory subsystem)
  2 = scoped destructive (move, trash, shell with allowlist)
  3 = unscoped destructive / external mutation (git push, write outside sandbox)
"""
from __future__ import annotations

from dataclasses import dataclass

from .modes import MODE_TIER_CEILING, Mode


class AuthorityViolation(Exception):
    """Raised when a tool call is attempted above the active mode's ceiling."""

    def __init__(self, tool_name: str, *, tool_tier: int, mode: Mode, ceiling: int):
        self.tool_name = tool_name
        self.tool_tier = tool_tier
        self.mode = mode
        self.ceiling = ceiling
        super().__init__(
            f"authority violation: tool {tool_name!r} (tier {tool_tier}) "
            f"exceeds mode {mode} ceiling (tier {ceiling})"
        )


@dataclass(frozen=True)
class ToolMeta:
    name: str
    tier: int
    description: str
    requires_approval: bool = False  # set True for Tier 3
    failure_modes: tuple[str, ...] = ()  # CI-checked: every tool declares its failure modes


# Built-in tier registry — kept in sync with §7 matrix.
# Tools register themselves by adding entries here.
_TIER_REGISTRY: dict[str, ToolMeta] = {}


def register_tool(meta: ToolMeta) -> None:
    if meta.tier == 3 and not meta.requires_approval:
        raise ValueError(f"Tier 3 tool {meta.name!r} must set requires_approval=True")
    if not meta.failure_modes:
        raise ValueError(
            f"Tool {meta.name!r} must declare at least one failure mode "
            "(architecture §V audit point: tool descriptions must include failure modes)"
        )
    _TIER_REGISTRY[meta.name] = meta


def get_tool_meta(name: str) -> ToolMeta:
    if name not in _TIER_REGISTRY:
        raise KeyError(f"unknown tool: {name!r}")
    return _TIER_REGISTRY[name]


def tools_available_in_mode(mode: Mode) -> list[ToolMeta]:
    """The exact set of tools the model is told about in this mode."""
    ceiling = MODE_TIER_CEILING[mode]
    return [m for m in _TIER_REGISTRY.values() if m.tier <= ceiling]


def all_tools() -> list[ToolMeta]:
    """Every registered tool, regardless of the current mode's tier
    ceiling. For capability/documentation surfaces (the cockpit's Task
    Guide) — never for dispatch (use tools_available_in_mode for that,
    which is what the authority gate actually enforces)."""
    return list(_TIER_REGISTRY.values())


def check_authority(tool_name: str, mode: Mode) -> ToolMeta:
    """Hard gate. Call before tool dispatch. Raises on violation."""
    meta = get_tool_meta(tool_name)
    ceiling = MODE_TIER_CEILING[mode]
    if meta.tier > ceiling:
        raise AuthorityViolation(
            tool_name, tool_tier=meta.tier, mode=mode, ceiling=ceiling
        )
    return meta
