"""Base planner protocol. All planners implement this contract."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..continuation import Step


class PlannerError(Exception):
    """Base for planner failures (bad args, IO error during plan, etc.)."""


class PlannerNotFound(PlannerError):
    """Requested a planner name that isn't registered."""

    def __init__(self, name: str, *, available: list[str]):
        self.name = name
        self.available = available
        super().__init__(
            f"unknown planner {name!r}. available: {', '.join(available) or '(none)'}"
        )


@dataclass(frozen=True)
class PlanResult:
    """Returned by ``Planner.plan()``.

    ``steps`` is the list of atomic units the runner will execute. ``goal``
    is the human-readable summary stored in the continuation file's top-level
    ``goal`` field. ``output_path`` is optional — if the planner aggregates
    results into a single file, name it here so the runner / CLI can show it.
    """

    goal: str
    steps: list[Step]
    output_path: str | None = None
    notes: str = ""


class Planner(ABC):
    """Abstract base for planners.

    A planner is stateless. Calling ``.plan(**args)`` twice with the same
    args produces equivalent step lists (modulo timestamps embedded in step
    args, which planners should avoid). This is what makes the re-trigger
    architecture deterministic.
    """

    #: Stable identifier used in the registry and in continuation YAML files.
    #: Renaming this breaks every continuation that references the old name.
    name: str = ""

    #: One-line description shown in ``sovereign planners list``.
    description: str = ""

    @abstractmethod
    def plan(self, **kwargs: Any) -> PlanResult:
        """Decompose the task into atomic steps. Pure function of kwargs.

        Should raise PlannerError on bad inputs (missing required arg,
        nonexistent path, empty result set, etc.) — never silently produce
        an empty plan.
        """

    @abstractmethod
    def render_step(self, step: Step, planner_args: dict) -> str:
        """Convert one ``Step`` into a goal string for the agent loop.

        This is what the model actually sees on each ``sovereign continue``
        invocation. Keep it short and concrete — no preamble, no reminders
        about the larger task. The system prompt already covers framing.
        """

    def required_args(self) -> tuple[str, ...]:
        """Return the names of required kwargs. Default: empty.

        Used by the CLI to show better error messages when the operator
        omits a required argument.
        """
        return ()
