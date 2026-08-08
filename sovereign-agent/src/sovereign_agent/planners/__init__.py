"""
╔══════════════════════════════════════════════════════════════════════════╗
║  planners — pure-Python task decomposition                               ║
║  Architecture §13 (new in v0.2.5, expanded v0.2.6)                       ║
╚══════════════════════════════════════════════════════════════════════════╝

A planner takes operator-provided arguments and produces a list of atomic
``Step`` objects. No model is invoked. The plan is deterministic given the
inputs, which is the property that makes the re-trigger architecture
auditable: you can read the continuation file and know exactly what will
happen, without speculating about model behavior.

Planners are registered by name. ``sovereign plan <name> --arg=…`` looks up
the planner, runs ``.plan(**args)``, and creates a continuation with the
returned steps.

Adding a planner:

  1. Create ``planners/<name>.py`` with a class that inherits from
     ``Planner`` and implements ``.plan()`` and ``.render_step()``.
  2. Register it in this file's ``REGISTRY``.
  3. Add a test in ``tests/test_planners.py``.

Each planner sets ``Step.required_model`` on the steps it generates. This
drives model-affinity batching in ``drain-by-model``: all steps tagged
'orchestrator' run with that model loaded, then all 'vision' steps, etc.
Loading each model exactly once instead of per-step.
"""
from __future__ import annotations

from .base import Planner, PlannerError, PlannerNotFound
from .code_inventory import CodeInventoryPlanner
from .game_design_brief import GameDesignBriefPlanner
from .image_inventory import ImageInventoryPlanner
from .impact_score import ImpactScorePlanner
from .inventory import InventoryPlanner
from .marketing_brief import MarketingBriefPlanner
from .metadata_inventory import MetadataInventoryPlanner
from .mos_canon_ingest import MOSCanonIngestPlanner
from .movie_pitch import MoviePitchPlanner
from .palace_apply import PalaceApplyPlanner
from .palace_clean import PalaceCleanPlanner
from .palace_mine import PalaceMinePlanner
from .palace_reflect import PalaceReflectPlanner
from .pdf_inventory import PdfInventoryPlanner
from .read_files import ReadFilesPlanner
from .summaries_to_atoms import SummariesToAtomsPlanner
from .trillion_dollar import TrillionDollarPlanner

REGISTRY: dict[str, Planner] = {
    "inventory": InventoryPlanner(),
    "read-files": ReadFilesPlanner(),
    "code-inventory": CodeInventoryPlanner(),
    "pdf-inventory": PdfInventoryPlanner(),
    "image-inventory": ImageInventoryPlanner(),
    "metadata-inventory": MetadataInventoryPlanner(),
    "palace-mine": PalaceMinePlanner(),
    "palace-reflect": PalaceReflectPlanner(),
    "palace-apply": PalaceApplyPlanner(),
    "palace-clean": PalaceCleanPlanner(),
    "mos-canon-ingest": MOSCanonIngestPlanner(),
    "impact-score": ImpactScorePlanner(),
    "summaries-to-atoms": SummariesToAtomsPlanner(),  # v0.2.11
    "trillion-dollar": TrillionDollarPlanner(),       # v0.2.12 — single cycle
    "marketing-brief": MarketingBriefPlanner(),       # v0.2.15 — PMM surface
    "movie-pitch": MoviePitchPlanner(),               # movie-studio-d — Dream Pitch Generator
    "game-design-brief": GameDesignBriefPlanner(),    # sprite-pipeline-d — expert Godot design brief
}


def get_planner(name: str) -> Planner:
    """Look up a planner by registered name.

    Raises PlannerNotFound with the list of valid names if missing.
    """
    if name not in REGISTRY:
        raise PlannerNotFound(name, available=sorted(REGISTRY.keys()))
    return REGISTRY[name]


def planner_names() -> list[str]:
    """Sorted list of registered planner names."""
    return sorted(REGISTRY.keys())


__all__ = [
    "Planner",
    "PlannerError",
    "PlannerNotFound",
    "REGISTRY",
    "get_planner",
    "planner_names",
]
