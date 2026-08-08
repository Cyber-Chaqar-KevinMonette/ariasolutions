"""game_design_doctrine — expert Godot game-design knowledge, as data.

Kevin (2026-08-02): "I want to do none of the game design at all, 0% of
it — I want it all to be her," then "make her a world class expert game
designer optimized for Godot engine." The existing game-dev toolset
(define_game_project, scaffold_godot_project, godot_check/export/open,
place_game_sprite) is mechanically sound but carries no design judgment —
nothing here shapes what genre fits a concept, what a core loop should
be, or how to structure a Godot scene tree well. This module is that
judgment, as data: `game_design_brief.py` (the planner) threads it into
every section it asks the model to write, so the brief — and everything
built from it — is grounded in real Godot idiom instead of a generic
guess.

A field, not hardcoded logic — same discipline `game_projects.py` already
follows for GENRES/DIMENSIONS. No LLM calls happen here.
"""
from __future__ import annotations

from .game_projects import GameProject

# One expert paragraph per game_projects.GENRES key — what makes the genre
# work, the common way it fails, and the pacing/session-length norm that
# keeps a solo-scoped project (this repo's own stated constraint —
# GENRES' own "even a little money, not AAA scope" framing) shippable.
GENRE_DESIGN_NOTES: dict[str, str] = {
    "idle-incremental": (
        "Idle/incremental lives or dies on the curve, not the content: one "
        "core resource, a small number of upgrade tiers with visibly "
        "escalating cost/return, and a prestige/reset loop that makes "
        "starting over feel like progress, not punishment. The common "
        "failure is shipping too MANY currencies before the first one is "
        "fun in isolation — tune one loop until it's satisfying at 30 "
        "seconds, 5 minutes, and 1 hour before adding a second system."
    ),
    "puzzle": (
        "One-screen or short-level puzzle design lives or dies on the "
        "teaching curve: each new mechanic gets one level that can ONLY be "
        "solved by understanding it, immediately followed by a level that "
        "combines it with something already taught. The common failure is "
        "a difficulty spike from under-teaching, not from the puzzle being "
        "hard — if a level needs more than one new idea, split it."
    ),
    "roguelike-arena": (
        "Short-run roguelike arenas need a run to be legible in under a "
        "minute of play: what kills the player, what they can pick up, "
        "and what a 'good' vs 'bad' run choice looks like, all readable "
        "from the screen without a tutorial. Run length should target "
        "5-15 minutes so failure costs little and 'one more run' stays "
        "true. The common failure is randomness that removes agency "
        "instead of creating interesting decisions — bias drops/upgrades "
        "toward choices, not pure luck."
    ),
    "arcade-score-attack": (
        "Score-attack lives entirely in the moment-to-moment feel: input "
        "response has to be near-instant, the scoring system needs one "
        "clear risk/reward lever (combo, multiplier, near-miss), and a run "
        "should target 60-90 seconds so a leaderboard chase stays "
        "low-commitment. The common failure is scope creep into multiple "
        "modes before the core 90-second loop is actually fun on repeat."
    ),
    "narrative-short": (
        "A narrative short needs a single, clear dramatic question stated "
        "or implied in the first two minutes of play, and every "
        "interaction should either reveal character or move that question "
        "forward — nothing decorative. Keep branching shallow (2-3 real "
        "choice points, not a sprawling tree) so the piece can actually "
        "be finished and polished rather than left as an outline."
    ),
    "platformer": (
        "Platformer feel is 90% of the genre: jump height/gravity/coyote-"
        "time/input buffering matter more than level count. Prototype and "
        "tune movement on a flat test room BEFORE building real levels — "
        "levels built against unfinished movement all need rework when "
        "the feel changes later. The common failure is treating level "
        "design as the hard part when it's actually the movement tuning."
    ),
    "other": (
        "No catalogued genre pattern applies directly — fall back on the "
        "core-loop discipline every genre here shares: define the single "
        "thing the player does over and over, make that one thing feel "
        "good in isolation before adding systems around it, and keep "
        "scope small enough that this concept can actually ship."
    ),
}

# Per game_projects.DIMENSIONS key — concrete Godot 4 idioms, not generic
# game-design advice. This is the section the planner's scene-architecture
# step leans on hardest.
DIMENSION_ENGINE_NOTES: dict[str, str] = {
    "2d": (
        "Root the scene at Node2D (scaffold_godot_project.py's own "
        "convention). Player/enemy movement uses CharacterBody2D + "
        "move_and_slide(), not raw position math. Collision via "
        "CollisionShape2D children, never manual AABB checks. A single "
        "Camera2D with limits set to the level bounds beats manual camera "
        "clamping code. Use Node2D groups + signals for "
        "cross-scene communication (e.g. 'enemy_died') instead of a "
        "parent polling children every frame."
    ),
    "2.5d": (
        "Still a Node2D root — 2.5D here means 2D gameplay with "
        "depth/perspective tricks on the same 2D node tree, not a "
        "separate 3D pipeline (scaffold_godot_project.py's own "
        "documented convention). Fake depth with y-sort (`y_sort_enabled "
        "= true` on the parent Node2D) for draw order, and parallax via "
        "ParallaxBackground/ParallaxLayer rather than hand-rolled camera "
        "math. Keep gameplay logic (collision, movement) purely 2D — the "
        "'2.5D' should live entirely in art/visual layering, not in the "
        "physics."
    ),
    "3d": (
        "Root the scene at Node3D. Player/enemy movement uses "
        "CharacterBody3D + move_and_slide(). Light the scene with one "
        "DirectionalLight3D + a WorldEnvironment before adding point "
        "lights — this hardware ceiling (an 8GB GTX 1070, the same VRAM "
        "budget vram_lock() already serializes GPU work against "
        "elsewhere in this repo) means real-time shadows and multiple "
        "dynamic lights should be the exception, not the default. Prefer "
        "baked lighting (LightmapGI) for static geometry once a scene "
        "stabilizes."
    ),
}

# Engine-idiom fundamentals that apply regardless of genre or dimension.
GODOT_CORE_PRINCIPLES: tuple[str, ...] = (
    "Compose scenes, don't inherit code hierarchies — build behavior by "
    "combining small, reusable scenes/nodes rather than deep script "
    "inheritance chains.",
    "Signals over polling — a node that needs to react to another node's "
    "state change should connect a signal, not check that state every "
    "_process()/_physics_process() frame.",
    "Autoload singletons (Project Settings > Autoload) for genuinely "
    "global state — score, save data, scene-transition manager — never "
    "reach up the tree with get_node('../../..') to find them.",
    "Resource-based, data-driven design — define enemy stats, item data, "
    "level parameters as custom Resource (.tres) files editable in the "
    "inspector, not hardcoded arrays/dicts buried in a script.",
    "Consistent node naming (PascalCase, descriptive: 'PlayerHurtbox' not "
    "'Area2D2') — it's the only thing keeping a scene tree readable once "
    "it has more than a handful of nodes.",
    "Respect this machine's real hardware ceiling: an 8GB GTX 1070. "
    "Prototype and profile on modest asset counts before scaling up "
    "texture sizes, particle counts, or dynamic light counts.",
)


def notes_for(project: GameProject) -> str:
    """Assemble the genre + dimension + core-principles guidance relevant
    to one project — what the design-brief planner (and, in time, other
    game-dev tools) thread into their prompts."""
    genre_note = GENRE_DESIGN_NOTES.get(project.genre, GENRE_DESIGN_NOTES["other"])
    dimension_note = DIMENSION_ENGINE_NOTES.get(project.dimension, DIMENSION_ENGINE_NOTES["2d"])
    principles = "\n".join(f"- {p}" for p in GODOT_CORE_PRINCIPLES)

    return (
        f"GENRE GUIDANCE ({project.genre_label}): {genre_note}\n\n"
        f"ENGINE GUIDANCE ({project.dimension}): {dimension_note}\n\n"
        f"GODOT CORE PRINCIPLES (always apply):\n{principles}"
    )


__all__ = [
    "GENRE_DESIGN_NOTES",
    "DIMENSION_ENGINE_NOTES",
    "GODOT_CORE_PRINCIPLES",
    "notes_for",
]
