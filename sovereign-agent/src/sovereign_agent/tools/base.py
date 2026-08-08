"""Tool base class. Architecture §7.

Every tool:
  - has a Pydantic input model (auto-converted to JSON schema for Ollama)
  - declares its tier
  - declares its failure modes (CI-checked, see authority.register_tool)
  - returns a typed Result

The dispatcher gates by tier (architecture §7) and by path scope where
applicable (architecture §6 invariant 6).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel

from ..authority import ToolMeta, register_tool


@dataclass
class ToolResult:
    """All tools return this. ok=False means the action failed; not raising is
    the rule so the agent loop can pass the failure back to the model."""

    ok: bool
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


_ArgsT = TypeVar("_ArgsT", bound=BaseModel)


class Tool(Generic[_ArgsT], abc.ABC):
    """Abstract base for every tool the agent can invoke.

    Subclasses must set:
        name: stable identifier the model uses
        tier: 0..3
        description: shown to the model
        failure_modes: tuple of strings — what can go wrong
        Args: Pydantic class with the typed inputs
    """

    name: ClassVar[str]
    tier: ClassVar[int]
    description: ClassVar[str]
    failure_modes: ClassVar[tuple[str, ...]]
    requires_approval: ClassVar[bool] = False
    Args: ClassVar[type[BaseModel]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Register on class definition. This is what makes
        # `tools_available_in_mode` work without manual registration calls.
        if hasattr(cls, "name") and not getattr(cls, "_abstract", False):
            register_tool(
                ToolMeta(
                    name=cls.name,
                    tier=cls.tier,
                    description=cls.description,
                    requires_approval=cls.requires_approval,
                    failure_modes=cls.failure_modes,
                )
            )

    @classmethod
    def schema(cls) -> dict[str, Any]:
        """JSON schema in the shape Ollama expects for tool calling."""
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": cls.description,
                "parameters": cls.Args.model_json_schema(),
            },
        }

    @abc.abstractmethod
    async def execute(self, args: _ArgsT, *, trace_id: str) -> ToolResult: ...
