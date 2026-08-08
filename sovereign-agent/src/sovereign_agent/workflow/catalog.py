"""
╔══════════════════════════════════════════════════════════════════════════╗
║  catalog.py — the Workflows catalog: WHAT Aria can do + HOW to do it       ║
║                                                                            ║
║  This is the user-facing answer to "is she really valid — can she really   ║
║  work?". It is a single, declarative source of truth describing every      ║
║  end-to-end workflow Aria supports, the exact steps to drive it, the       ║
║  subsystems each one exercises, its authority tier, and its safety         ║
║  posture. The cockpit's ▸ flows menu renders straight from this list, and  ║
║  the ✦ demo runner (workflow/demo.py) proves a safe subset of it LIVE.     ║
║                                                                            ║
║  Two layers, kept honest and never blurred:                               ║
║    • status="ready"  — works here, today, no special hardware.            ║
║    • status="gated"  — a real, designed capability that needs Kevin's     ║
║                        machine/model/display to verify (voice, vision,    ║
║                        true A/V capture, live-LLM practice). Named, not    ║
║                        faked — see docs/ROADMAP.md H-tier.                 ║
║                                                                            ║
║  Design rules (so the menu and the demo can never drift):                 ║
║    • Pure data + light formatting. No side effects, no heavy imports.      ║
║    • Authority tiers follow the MOS stack (0 read-only … 4 orchestration). ║
║    • A workflow is part of the live demo iff `demo_kind` is set; the       ║
║      matching probe lives in workflow/demo.py keyed by `wid`. A test       ║
║      asserts the two stay in lock-step.                                    ║
║                                                                            ║
║  v0.2.55.0                                                                 ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

WorkflowStatus = Literal["ready", "gated"]
DemoKind = Literal["introspect", "sandbox", "sov"]

# Authority tiers — the MOS stack, mirrored from workflow.capabilities.AuthorityPolicy
# and stewardship doctrine. Kept here as plain ints so the catalog stays import-light.
AUTHORITY_LABEL: dict[int, str] = {
    0: "Tier 0 · read-only, no side effects",
    1: "Tier 1 · reversible writes, bounded scope (logged)",
    2: "Tier 2 · persistent change / external call — human confirms",
    3: "Tier 3 · irreversible / financial / PII — explicit approval + audit",
    4: "Tier 4 · cross-system / multi-agent — human + policy + kill switch",
}

# Workflow complexity tiers (distinct from authority). From the Workflow Hub
# concept: how elaborate the flow itself is, 0..3, where 3 is "God Tier" —
# multi-step, branching, Sentinel-watched. Shown as a badge on each card.
WORKFLOW_TIER: dict[int, str] = {
    0: "T0 Basic · single-step, instant",
    1: "T1 Standard · a few steps, one subsystem",
    2: "T2 Advanced · branching / tool-use / conditional",
    3: "T3 God Tier · multi-step, self-checking, Sentinel-watched",
}


@dataclass(frozen=True)
class Workflow:
    """One end-to-end thing Aria can do, and exactly how to drive it."""
    wid: str                       # stable id, e.g. "safety.charter"
    title: str                     # short human title
    category: str                  # grouping for the menu
    summary: str                   # one line: what she does
    how_to: tuple[str, ...]        # ordered steps the operator follows
    try_it: str = ""               # one line to paste into the cockpit input
    uses: tuple[str, ...] = ()     # subsystems / capabilities / sentinels touched
    authority: int = 0             # MOS authority tier (0..4)
    safety: str = ""               # one-line guardrail (reversible? gated?)
    status: WorkflowStatus = "ready"
    needs: str = ""                # if gated: what it needs to be verified
    demo_kind: Optional[DemoKind] = None   # set → included in the live ✦ demo
    demo_note: str = ""            # what the live probe does (honest, specific)
    tier: int = 1                  # workflow complexity tier (0..3); see WORKFLOW_TIER
    tutorial: tuple[str, ...] = () # optional guided walkthrough (grows over time)
    # capability-test-menu-d (Kevin, 2026-07-28): "make a test button... to test
    # her abilities, to do real work." Orthogonal to demo_kind — the ✦ demo is a
    # cheap, no-models/no-network introspection probe; cap_test set → this
    # workflow has a REAL capability test wired in workflow/capability_tests.py
    # (keyed by wid, same lock-step-tested pattern as demo_kind/CHECKS).
    cap_test: Optional[str] = None  # set → has a real capability test
    cap_test_note: str = ""         # what the real test actually does (honest, specific)

    @property
    def authority_label(self) -> str:
        return AUTHORITY_LABEL.get(self.authority, f"Tier {self.authority}")

    @property
    def tier_label(self) -> str:
        return WORKFLOW_TIER.get(self.tier, f"T{self.tier}")

    @property
    def has_tutorial(self) -> bool:
        return bool(self.tutorial)

    @property
    def is_demoable(self) -> bool:
        return self.demo_kind is not None and self.status == "ready"

    @property
    def is_cap_testable(self) -> bool:
        return self.cap_test is not None and self.status == "ready"


# ─── The catalog ─────────────────────────────────────────────────────────────
#
# Ordered by muscle group. `try_it` lines are pasted (never auto-run) so the
# operator reviews before pressing Enter — the same contract as the palette.

CATALOG: tuple[Workflow, ...] = (

    # ── Inspect & Diagnose ─────────────────────────────────────────────
    Workflow(
        "inspect.doctor", "Full environment diagnostic", "Inspect & Diagnose",
        "Check the whole install end-to-end — is the kernel whole, are paths and "
        "config sane, is Ollama reachable.",
        ("Open the cockpit (`.venv/bin/sovereign cockpit`).",
         "Click the [doctor] palette button (or type `sov doctor`), review, Enter.",
         "Read the verdict; anything red is the first thing to fix."),
        try_it="sov doctor",
        uses=("doctor", "ollama_client", "config", "health"),
        authority=0, safety="Read-only. Touches nothing; just reports."),
    Workflow(
        "inspect.status", "One-glance state", "Inspect & Diagnose",
        "Summarize dreams, continuations, projects, palace, and liveness in a "
        "single read.",
        ("In the cockpit, click [status] (or `sov status`).",
         "Use [info] and [aria] for deeper version/path/kernel detail."),
        try_it="sov status",
        uses=("home", "cadence", "palace", "heartbeat"),
        authority=0, safety="Read-only."),
    Workflow(
        "inspect.health", "Health check + report", "Inspect & Diagnose",
        "Quick system-health summary, or a full report saved to disk for sharing.",
        ("Type `/health` for a quick summary in chat.",
         "Type `/report` to write a full health report to the data dir."),
        try_it="/health",
        uses=("health", "sysmon", "log_rotation"),
        authority=1, safety="Read-only summary; /report writes one file to the data dir."),

    # ── Memory & Recall ────────────────────────────────────────────────
    Workflow(
        "memory.channels", "Browse memory channels", "Memory & Recall",
        "List and read her memory channels — lessons, people, goals, emotions, "
        "commitments, and the rest.",
        ("Click [channels] (or `sov channels list`).",
         "Type `/lessons` for recent lesson atoms.",
         "`sov channels show <name>` reads a specific channel."),
        try_it="sov channels list",
        uses=("mem_channels", "memory", "retrieval"),
        authority=0, safety="Read-only."),
    Workflow(
        "memory.store", "Remember & recall (atoms)", "Memory & Recall",
        "Write a durable memory atom and retrieve it later with provenance — the "
        "store under everything.",
        ("Memories are written by her flows automatically with provenance.",
         "Inspect the store with `sov status` / `sov channels`.",
         "The ✦ demo proves a write→read round-trip in an isolated sandbox db."),
        uses=("persistence.store", "memory.atom", "provenance", "bitemporal"),
        authority=1, safety="Reversible. Live demo writes only to a sandbox db, never atoms.db.",
        demo_kind="sandbox",
        demo_note="opens an isolated ErebloStore under the demo sandbox and reads its stats"),
    Workflow(
        "memory.palace", "Search the memory palace", "Memory & Recall",
        "Query the structured 'palace' — rooms, closets, subjects, understanding, "
        "lineage — for what she knows about a topic.",
        ("`sov palace search \"<topic>\"` finds relevant rooms/atoms.",
         "`sov palace rooms` / `sov palace subject <x>` browse structure.",
         "`sov palace understanding` summarizes what she grasps."),
        try_it="sov palace search \"sovereignty\"",
        uses=("palace", "palace_mining", "retrieval.recall"),
        authority=0, safety="Read-only."),

    # ── Plan & Build ───────────────────────────────────────────────────
    Workflow(
        "build.plan", "Plan a directive", "Plan & Build",
        "Turn a plain-English goal into a reviewable, step-by-step plan before any "
        "step runs.",
        ("In the cockpit, just say the goal in plain English, e.g. "
         "`inventory ~/AA-Erebo for markdown files`.",
         "She proposes a plan; you approve, edit, or cancel (`/cancel`).",
         "Each step is gap-checked against her capabilities first."),
        try_it="plan: inventory ~/AA-Erebo for markdown files",
        uses=("planner", "planners", "workflow.capabilities", "workflow.agentic_loop"),
        authority=1, safety="Planning is read-only; execution is gated per step by authority tier."),
    Workflow(
        "build.sandbox_file", "Author a file (sandboxed)", "Plan & Build",
        "Write and read source/docs inside a sandbox root — the file_write / "
        "file_read capability, bounded so it can't touch her own code.",
        ("Ask in plain English, e.g. `write a README for the demo in the sandbox`.",
         "File writes are confined to the sandbox root by the handler.",
         "The ✦ demo proves a write→read round-trip in the demo sandbox."),
        uses=("workflow.handlers.file_write", "tools.write_file", "sandbox", "pathguard"),
        authority=1, safety="Reversible + sandbox-confined. Self-targeting writes are blocked by design.",
        demo_kind="sandbox",
        demo_note="writes a small file under the demo sandbox and reads it back byte-for-byte"),
    Workflow(
        "build.do", "Run a directive (work mode)", "Plan & Build",
        "Execute an approved plan: she uses her tools, holds the task clean across "
        "steps, and forms real memories.",
        ("Switch to work mode with `/mode work` (chat is the default).",
         "State the goal; approve the plan; watch the live windows.",
         "`/cancel` stops the running directive at any time."),
        try_it="/mode work",
        uses=("loop", "workflow.agentic_loop", "tools", "approval", "rollback"),
        authority=2, safety="Consequential steps need confirmation; self-modification ALWAYS needs you."),
    Workflow(
        "build.marketing", "Generate a marketing brief", "Plan & Build",
        "Produce a structured marketing brief for a product or release via the "
        "marketing planner.",
        ("Type `/marketing <product or release name>`.",
         "Review the drafted brief; archive it with `/draft <title> <path>`."),
        try_it="/marketing Aria v0.2.55",
        uses=("planners.marketing_brief", "drafts", "insights"),
        authority=1, safety="Drafts to the data dir; reversible."),

    # ── Generate & Create ──────────────────────────────────────────────
    # capability-test-menu-d (Kevin, 2026-07-28): "Make images, make videos,
    # make audio, make content, maybe search the web, make new trackers, make
    # new bots... catalog a long list of things you would like to see her
    # do." Honest by the same rule as everything else here: `create.video`
    # has no tool behind it yet, so it's gated, not faked.
    Workflow(
        "create.image", "Generate an image", "Generate & Create",
        "Generate an image from a text prompt using a local diffusion model — "
        "FLUX-schnell, SDXL-Turbo, or SD 2.1.",
        ("Ask in plain English, e.g. `generate an image of a red fox in snow`.",
         "Or drive the tool directly: prompt, model, width/height, steps.",
         "The ▶ test in the capability test menu runs the smallest real combo "
         "(SDXL-Turbo, 256×256, 2 steps) and reports where the PNG landed."),
        try_it="generate an image of a red fox in snow",
        uses=("tools.generate_image", "vram_lock", "diffusers"),
        authority=1, safety="Writes only to data_dir/images/generated/; VRAM-serialized "
                            "so it never contends with the orchestrator model.",
        cap_test="create.image",
        cap_test_note="calls the real GenerateImageTool at the cheapest real "
                      "size/step combo and records the output path"),
    Workflow(
        "create.image_edit", "Edit / inpaint an image", "Generate & Create",
        "Edit an existing image or inpaint a masked region of it with a local "
        "diffusion model.",
        ("Ask in plain English with an existing image path and what to change.",
         "The ▶ test edits a freshly-generated throwaway test image."),
        uses=("tools.image_edit", "vram_lock", "diffusers"),
        authority=1, safety="Writes only to data_dir/images/generated/; VRAM-serialized.",
        cap_test="create.image_edit",
        cap_test_note="edits the create.image test's output (or a fresh tiny one) "
                      "and records the edited path"),
    Workflow(
        "create.web_search", "Search the web", "Generate & Create",
        "Search the web for URLs related to a query — the same real lookup her "
        "planning/research flows use.",
        ("Ask in plain English, e.g. `search the web for the python packaging guide`.",
         "The ▶ test runs a fixed, benign query and reports result count."),
        try_it="search the web for the python packaging guide",
        uses=("tools.web_search",),
        authority=0, safety="Read-only, network. Degrades to an honest 'skip' — never a "
                            "fabricated result — when the internet is unreachable.",
        cap_test="create.web_search",
        cap_test_note="runs a fixed benign query through the real WebSearchTool; "
                      "reports skip (not fail) when offline"),
    Workflow(
        "create.game_project", "Scaffold a game project", "Generate & Create",
        "Define a new game project — name, genre, structure — the first step of "
        "her game-dev toolset.",
        ("Ask in plain English, e.g. `start a new idle-incremental game project`.",
         "The ▶ test scaffolds a throwaway project into its own sandbox dir, "
         "never the real projects folder."),
        uses=("tools.define_game_project", "game_projects"),
        authority=1, safety="Sandbox-scoped write; the real tool also supports a data_dir "
                            "override, which the test uses to stay out of the real one.",
        cap_test="create.game_project",
        cap_test_note="defines a throwaway project via a sandboxed data_dir override"),
    Workflow(
        "create.scaffold_godot_project", "Scaffold a real Godot project", "Generate & Create",
        "Write a real, minimal Godot project (project.godot + a starter scene) "
        "into a defined game project's workspace — the missing step between "
        "'define a concept' and being able to godot_check/godot_export/"
        "godot_open it. Starts 2D or 2.5D (Node2D root); 3D (Node3D root) is "
        "the same tool, driven by the project's own dimension field.",
        ("Define a game project first (create.game_project), then ask in "
         "plain English, e.g. `scaffold the godot project for <name>`.",
         "The ▶ test scaffolds a throwaway project's files into its own "
         "sandbox dir, never the real games/ folder — validated live against "
         "the real installed Godot binary (godot --headless --check-only "
         "--quit exits 0) during development, not by this quick test."),
        uses=("tools.scaffold_godot_project", "game_projects"),
        authority=1, safety="Sandbox-scoped write; never overwrites an existing "
                            "project.godot.",
        cap_test="create.scaffold_godot_project",
        cap_test_note="defines + scaffolds a throwaway project via a sandboxed "
                      "data_dir/workspace override, asserts the files exist"),
    Workflow(
        "create.game_art", "Generate 2D game art", "Generate & Create",
        "Generate sprite/texture-style game art from a text prompt — the "
        "same local diffusion model as create.image, prompted for game use "
        "(transparent background, consistent art style) rather than a new "
        "tool.",
        ("Ask in plain English, e.g. `generate a 2D sprite of a knight, "
         "pixel art style, transparent background`.",
         "The ▶ test reuses create.image's own cheapest real combo — same "
         "tool, game-art framing is guidance, not new code."),
        try_it="generate a 2D sprite of a coin, pixel art style, transparent background",
        uses=("tools.generate_image", "vram_lock", "diffusers"),
        authority=1, safety="Writes only to data_dir/images/generated/; VRAM-serialized.",
        cap_test="create.game_art",
        cap_test_note="aliases create.image's own capability test function — "
                      "the underlying tool is identical, only the prompting "
                      "guidance differs, so no new test logic is written"),
    Workflow(
        "create.place_game_sprite", "Generate, import & place a sprite", "Generate & Create",
        "Generate a sprite from a text prompt, import it into a registered game "
        "project's assets/sprites/, and place it as a real node in the project's "
        "main.tscn — one wired call, the missing link between create.game_art's "
        "standalone PNGs and an actual referenced-in-scene sprite.",
        ("Ask in plain English, e.g. `generate and place a sprite of a knight "
         "for <project>`. Requires the project to already be scaffolded "
         "(create.scaffold_godot_project first).",
         "The ▶ test scaffolds a throwaway project, then runs a real cheap "
         "generation through the tool and asserts the PNG landed in assets/ "
         "and the scene gained the new node."),
        try_it="generate and place a sprite of a coin for the focused game project",
        uses=("tools.place_game_sprite", "tools.generate_image", "vram_lock", "diffusers"),
        authority=1, safety="Writes only to the project's own assets/sprites/ and main.tscn.",
        cap_test="create.place_game_sprite",
        cap_test_note="scaffolds a real throwaway project, generates a real "
                      "256x256 PNG via the cheapest model combo, and asserts "
                      "it's referenced in main.tscn"),
    Workflow(
        "create.game_design_brief", "Generate a Godot game design brief", "Generate & Create",
        "Produce a structured, Godot-specific game design brief (core loop, "
        "mechanics, art direction, scene architecture, level plan, progression "
        "& monetization) for a registered game project — grounded in "
        "game_design_doctrine's expert Godot knowledge, not a generic guess.",
        ("Ask in plain English, e.g. `write a game design brief for <project>`, "
         "or run `sovereign plan game-design-brief --project_slug=<slug> "
         "--output=<path>` directly.",
         "The ▶ test runs the planner's own deterministic decomposition (no "
         "model call) and asserts every section is present, in order, with "
         "doctrine guidance threaded in."),
        try_it="write a game design brief for the focused game project",
        uses=("planners.game_design_brief", "game_design_doctrine"),
        authority=1, safety="Drafts markdown to a single output path; reversible.",
        cap_test="create.game_design_brief",
        cap_test_note="runs the real planner and asserts the six sections come "
                      "back in order with genre/dimension doctrine notes present"),
    Workflow(
        "create.marketing_brief", "Generate a marketing brief", "Generate & Create",
        "Produce a structured marketing brief for a product or release via the "
        "marketing planner.",
        ("Type `/marketing <product or release name>`.",
         "The ▶ test proves the planner's section structure comes back complete "
         "— not full LLM-authored copy, which needs the agentic loop."),
        try_it="/marketing Aria v0.2.60",
        uses=("planners.marketing_brief",),
        authority=1, safety="Drafts to a sandbox path during the test; reversible.",
        cap_test="create.marketing_brief",
        cap_test_note="runs the real planner into the run sandbox and asserts every "
                      "section comes back in order"),
    Workflow(
        "create.discord_tracker", "Create a new Discord tracker", "Generate & Create",
        "Add a new tracked category (a 'vertical') to Aria's Discord shop — proven "
        "working this session for Warframe, Target, Best Buy, and more.",
        ("Define a new vertical (slug, sources, keywords) in verticals.py.",
         "`sov scout sync` + the setup-all bridge command mint its real channels.",
         "The ▶ test is a dry-run: it proves the planning mechanism works "
         "without creating a single real channel or role."),
        uses=("verticals", "discord_admin.blueprint", "command_bridge"),
        authority=2, safety="The real mechanism touches a live Discord server (Tier 2); "
                           "the capability test is dry-run/introspection ONLY, by design, "
                           "forever — it never calls Discord.",
        cap_test="create.discord_tracker",
        cap_test_note="builds a throwaway vertical and confirms it plans cleanly through "
                      "the blueprint logic, with zero network/Discord calls"),
    Workflow(
        "create.discord_bot_command", "Create a new Discord bot command", "Generate & Create",
        "Add a new slash command to Aria's Discord admin bot — proven working this "
        "session (/vaulted-relics, /wf-lookup, and more).",
        ("Add a `@tree.command` in discord_admin/bot.py + a COMMANDS catalog entry.",
         "Restart aria-bot.service to register it live.",
         "The ▶ test is introspection-only: it confirms the command catalog and "
         "help-panel renderer are well-formed, with zero Discord client/network."),
        uses=("discord_admin.bot",),
        authority=2, safety="The real mechanism registers a live slash command (Tier 2); "
                           "the capability test never touches discord.Client or the network.",
        cap_test="create.discord_bot_command",
        cap_test_note="asserts COMMANDS is well-formed and build_commands_embed renders, "
                      "entirely offline"),
    Workflow(
        "create.movie_project", "Define a movie project", "Generate & Create",
        "Define a new movie project — title, genre, logline, style — the "
        "direction, not the footage. The Movie Studio's foundation: real "
        "production tracking modeled directly on the proven Game Studio.",
        ("Ask in plain English, e.g. `start a new animated short about...`.",
         "Or open the Movie Studio (`/movies`) and fill the form directly.",
         "The ▶ test defines a throwaway project into a sandboxed data_dir, "
         "never the real movie_projects/ store."),
        try_it="/movies",
        uses=("movie_projects", "tools.define_movie_project"),
        authority=1, safety="Sandbox-scoped write when tested; the real tool writes a "
                            "single reversible JSON record.",
        cap_test="create.movie_project",
        cap_test_note="defines a throwaway project via a sandboxed data_dir override, "
                      "mirrors create.game_project exactly"),
    Workflow(
        "create.movie_pitch", "Draft original movie pitches", "Generate & Create",
        "The Dream Pitch Generator — she proposes N original short-film "
        "concepts on a theme (defaults to an open, attention-grabbing theme "
        "when none is given, never a narrow hardcoded topic). Pick one to "
        "seed a real movie project.",
        ("Open Movie Studio (`/movies`), leave the theme blank or name one, "
         "click 'draft pitches' — a real continuation is queued.",
         "Drain the continuation to have the orchestrator write the actual "
         "pitch text, same mechanism as the marketing-brief planner."),
        uses=("planners.movie_pitch", "continuation"),
        authority=1, safety="Queues a real continuation (reversible); no LLM call "
                           "happens from the planner itself.",
        cap_test="create.movie_pitch",
        cap_test_note="runs the real planner into a sandbox output path and asserts "
                      "the expected pitch-step count/shape comes back — proves "
                      "structure, not full LLM-authored content"),
    Workflow(
        "create.video", "Generate a video", "Generate & Create",
        "Real local video clip generation for Movie Studio — LTX-Video via "
        "the same diffusers library image_generate.py uses. FOSS, no cloud, "
        "no cost. Confirmed live on this exact GTX 1070 (four consecutive "
        "successful runs, including a real quality-checked clip).",
        ("Open Movie Studio (`/movies`), browse to a project, write a shot "
         "prompt, click 'generate clip'.",
         "Slow by design (~1-3 min for a tiny clip on this hardware) — "
         "local-over-speed was the explicit, accepted tradeoff, not a bug.",
         "The ▶ test runs the smallest real combo (256×256, 9 frames, 8 "
         "steps) into a throwaway project workspace."),
        uses=("tools.generate_movie_clip", "vram_lock", "LTXPipeline via diffusers"),
        authority=1, safety="Sandbox-scoped write (a project's own clips/ folder); "
                           "VRAM-serialized via enable_sequential_cpu_offload() — "
                           "confirmed the only safe technique on this card. NEVER "
                           "use fp8-layerwise-casting + CUDA-stream group-offloading "
                           "here — that combination froze the whole machine live.",
        cap_test="create.video",
        cap_test_note="generates a real 9-frame clip via the real LTXPipeline into a "
                      "throwaway project's workspace, at the cheapest verified-safe "
                      "combo (8 steps — real but low-quality; production use should "
                      "use 30 steps/guidance_scale=5.0 for recognizable output)"),

    # ── Collaborate ────────────────────────────────────────────────────
    Workflow(
        "collab.inbox", "Collaboration inbox", "Collaborate",
        "See what she's waiting on you for — questions, suggestions, decisions — "
        "each with its context, and resolve them.",
        ("Click [inbox] (or `sov requests`) for open asks.",
         "Click [parked] (or `sov requests parked`) for deferred/flagged work.",
         "She files these herself; you answer, defer 💤, flag 🚩, or resolve."),
        try_it="sov requests",
        uses=("workflow.requests", "persistence.store", "feedback"),
        authority=1, safety="Reversible. Live demo opens+resolves a request in a sandbox db.",
        demo_kind="sandbox",
        demo_note="opens, counts, then resolves a collaboration request in the demo sandbox db"),
    Workflow(
        "collab.proposals", "Review subsystem proposals", "Collaborate",
        "When she finds a capability gap she drafts a PROPOSED handler — never "
        "active — for you to review, stage, approve, or roll back.",
        ("`sov proposals list` shows drafted proposals.",
         "`sov proposals show <id>` reads one; `approve` / `reject` / `rollback` act.",
         "Nothing she drafts can run until you approve and register it."),
        try_it="sov proposals list",
        uses=("proposals", "workflow.capabilities", "code_gate", "approval"),
        authority=2, safety="Proposals are inert drafts. Activation is human-only, with rollback."),

    # ── Safety & Recovery ──────────────────────────────────────────────
    Workflow(
        "safety.charter", "Charter & kill-switch", "Safety & Recovery",
        "Verify the sealed charter's integrity — the same check the kill switch "
        "reads. Her constitution, hash-verified.",
        ("Click [charter] (or `sov charter status`).",
         "A green verdict means articles + hash verify and the kill switch is clear."),
        try_it="sov charter status",
        uses=("charter", "seal", "constitution"),
        authority=0, safety="Read-only. The charter (SIGNAL.md) is sealed; never edit casually.",
        demo_kind="introspect",
        demo_note="runs charter.check_integrity() and reports the live integrity level"),
    Workflow(
        "safety.protocol_zero", "PROTOCOL-ZERO (halt / disarm)", "Safety & Recovery",
        "The emergency stop. Halt freezes all agent loops and revokes tool access; "
        "disarm clears it after review.",
        ("Press Ctrl-H (or `/halt`) to trip PROTOCOL-ZERO.",
         "Press Ctrl-D (or `/disarm`) to clear it once it's safe.",
         "While halted, no autonomous step can run — by design."),
        try_it="/halt",
        uses=("protocol_zero", "authority", "interrupts"),
        authority=2, safety="The stop itself is always allowed. Disarm is a deliberate human act."),
    Workflow(
        "safety.authority_tiers", "Authority tiers", "Safety & Recovery",
        "Inspect the rule that decides when she may act alone: read-only is self-"
        "answerable; self-modifying code/values ALWAYS needs you.",
        ("`sov capabilities` shows subsystems + their posture.",
         "The two hard lines: self-modification needs a human even in --yes mode; "
         "consequential kinds need confirmation."),
        try_it="sov capabilities",
        uses=("workflow.capabilities", "authority", "approval"),
        authority=0, safety="Read-only inspection of the policy.",
        demo_kind="introspect",
        demo_note="asserts read-only is self-answerable and self-modifying ALWAYS requires a human"),
    Workflow(
        "safety.self_development", "Self-development boundary", "Safety & Recovery",
        "Read where her growth tops out (bounded self-calibration) and the named, "
        "never-built deferred-unsafe capabilities.",
        ("She grows only by bounded practice (● grow) — never self-rewriting.",
         "The deferred-unsafe set is named in self_development.DEFERRED_UNSAFE.",
         "Read-only priorities (Safety/Love/Flourishing) are immutable."),
        uses=("self_development", "mos_canon"),
        authority=0, safety="Read-only. The unsafe set is refused defensively by is_permitted().",
        demo_kind="introspect",
        demo_note="confirms unsafe capabilities are refused and read-only priorities are protected"),
    Workflow(
        "safety.backup", "Snapshot & restore", "Safety & Recovery",
        "Take restore points and roll back. If a step ever goes wrong, there's "
        "always a way home.",
        ("`/snap <label>` (or `sov backup snapshot`) takes a snapshot.",
         "Click [backups] (or `sov backup list`) to see restore points."),
        try_it="/snap before-demo",
        uses=("backup", "rollback", "archive"),
        authority=2, safety="Snapshots are additive + reversible; restore is a deliberate act."),

    # ── Self-knowledge & Calibration ───────────────────────────────────
    Workflow(
        "self.capabilities", "Know her own toolset", "Self-knowledge & Calibration",
        "She reasons about her own subsystems: which she has, which a goal needs, "
        "and which are missing — then drafts proposals for gaps.",
        ("Click [caps] (or `sov capabilities`).",
         "Gaps become inert proposals (see Review subsystem proposals)."),
        try_it="sov capabilities",
        uses=("workflow.capabilities",),
        authority=0, safety="Read-only self-knowledge.",
        demo_kind="introspect",
        demo_note="builds the capability registry from the live catalog and lists her action kinds"),
    Workflow(
        "self.variant_routing", "Route to the right variant", "Self-knowledge & Calibration",
        "Given a flow, she picks the best-fitting variant of a capability (a git-"
        "tuned shell for a commit, a docs-tuned writer for a README).",
        ("This runs inside planning automatically.",
         "The ✦ demo shows her choosing the git variant for a 'git commit' flow."),
        uses=("workflow.capabilities", "planner"),
        authority=0, safety="Read-only, reversible decision.",
        demo_kind="introspect",
        demo_note="asks the VariantRouter to pick a variant for a git flow and reports its choice"),
    Workflow(
        "calib.intuition", "Calibrated intuition", "Self-knowledge & Calibration",
        "Earned, scoped 'gut': she logs a prediction with confidence, gets feedback, "
        "and her calibration sharpens over reps — never beyond what's earned.",
        ("Calibration accrues through her flows and the gym.",
         "The ✦ demo logs one prediction + feedback and shows reps accruing."),
        uses=("intuition", "training", "intent.maturity"),
        authority=1, safety="Bounded calibration only — never self-modification.",
        demo_kind="introspect",
        demo_note="logs a sense() prediction, resolve()s it, and confirms a calibration rep accrued"),
    Workflow(
        "self.grow", "Bounded self-practice (● grow)", "Self-knowledge & Calibration",
        "She re-runs her own gym to harden calibration and flow — time-boxed (~10 "
        "min), halt-able, fully observable, writing only a journal.",
        ("Click the [● grow] button (or it runs from the data dir).",
         "Watch the live cycles; press ● grow again or HALT to stop.",
         "A journal lands under the data dir — share it with Claude."),
        try_it="(click ● grow)",
        uses=("self_practice", "training", "intuition"),
        authority=1, safety="Bounded, halt-able, observable. NEVER edits code, values, or the charter."),
    Workflow(
        "self.doctrine", "MOS doctrine & priorities", "Self-knowledge & Calibration",
        "Read the adaptive doctrine clauses and the immutable read-only priorities "
        "that order every conflict.",
        ("The 34 clauses live in mos_canon.py (adaptive, not sealed).",
         "Read-only priorities: Safety, then Love, then Flourishing — fixed."),
        uses=("mos_canon",),
        authority=0, safety="Read-only.",
        demo_kind="introspect",
        demo_note="confirms the read-only priorities are Safety, Love, Flourishing and clauses load"),

    # ── Visual & Expression ────────────────────────────────────────────
    Workflow(
        "visual.themes", "Themes", "Visual & Expression",
        "Browse and switch cockpit themes — curated and custom — each with its own "
        "palette and effects.",
        ("Click [themes] (or `sov theme list`).",
         "`sov theme use <name>` switches the active theme."),
        try_it="sov theme list",
        uses=("cockpit.themes", "cockpit.user_themes", "cockpit.hue_cycle"),
        authority=0, safety="Read-only listing; switching is reversible.",
        demo_kind="introspect",
        demo_note="loads the curated theme catalog and confirms each theme is well-formed"),
    Workflow(
        "visual.cosmic", "Cosmic Fitness (glyph gym)", "Visual & Expression",
        "Test every glyph for width-safety and see the special effects; click a "
        "glyph to drop it into your message.",
        ("Click [◊ cosmic] (or `/cosmic`) to open the tester.",
         "`/cosmic probe` measures real terminal widths; `/cosmic report` prints the verdict.",
         "Ctrl-G opens the inline glyph picker near the input."),
        try_it="/cosmic",
        uses=("cockpit.cosmic_fitness", "cockpit.glyph_metrics", "stewardship.glyph_sentinel"),
        authority=0, safety="Read-only. Width-unstable glyphs render as badges inside counted grids."),
    Workflow(
        "visual.glyph_safety", "Glyph width-safety", "Visual & Expression",
        "The 'Measured Truth' engine: distinguish layout-safe glyphs from wide / "
        "emoji ones so borders never jitter.",
        ("Width-safety is enforced automatically across the TUI.",
         "The ✦ demo shows a wide emoji classified apart from a narrow glyph."),
        uses=("cockpit.cosmic_fitness", "cockpit.glyph_metrics"),
        authority=0, safety="Read-only classification.",
        demo_kind="introspect",
        demo_note="classifies a wide emoji vs a blessed-narrow glyph and confirms they differ"),
    Workflow(
        "visual.record", "Record the cockpit", "Visual & Expression",
        "Capture a self-contained recording of the cockpit (frame snapshots today; "
        "true A/V is gated — see below).",
        ("Click [● rec] (or Ctrl-R) to start/stop a take.",
         "Takes land in the recordings folder with a self-contained HTML player."),
        try_it="(click ● rec)",
        uses=("cockpit.recorder", "cockpit.telemetry"),
        authority=1, safety="Writes only to the recordings folder; reversible."),

    # ── Voice & Vision (gated — needs Kevin's machine) ─────────────────
    # -- Skills & Mastery -----------------------------------------------
    Workflow(
        "skills.author", "Author her own skills", "Skills & Mastery",
        "She writes skills for herself: named, IDed, in-depth playbooks grounded "
        "in memory or a lesson. She enriches them over reps, merges old ones into "
        "new, and reads them for insight when architecting more. A skill is "
        "knowledge, never self-modifying code.",
        ("Skills live in her skill library (data dir / skills).",
         "Each has a stable id + breakdown + context so the knowledge is leverageable.",
         "The demo writes one, matures it, and merges two with lineage."),
        try_it="(skill library is programmatic today; a button is on the roadmap)",
        uses=("skillsmith",),
        authority=1, tier=2,
        tutorial=(
            "1. Name the skill + write a one-line summary of what it is.",
            "2. Add the breakdown - the in-depth steps she'll follow.",
            "3. Ground it: cite the memory or lesson it came from.",
            "4. Use it over reps; merge related skills; let maturity grow."),
        safety="Skills are data, not code. A kernel guard refuses any skill that "
               "claims to rewrite code/values, set autonomous goals, self-improve "
               "without bound, or disable the kill switch.",
        demo_kind="sandbox",
        demo_note="builds a skill library in the sandbox, matures a skill over reps, "
                  "merges two with lineage, and confirms the kernel guard refuses an unsafe one"),
    Workflow(
        "skills.sentinel", "Skill Sentinel (steward)", "Skills & Mastery",
        "A steward that keeps her skills organized, clean, and up to date. Ask it "
        "for the ids + context of whatever skill set fits a goal; it dedupes, "
        "flags stale or malformed skills, and offloads curation. It assists, "
        "never gates -- she can always bypass it and read the library directly.",
        ("Give the Sentinel a query; it returns matching skills + their ids + context.",
         "Ask it for a health report to see duplicates, stale, or malformed skills.",
         "It is read-only over the library -- it never blocks access."),
        try_it="(steward is programmatic today; a button is on the roadmap)",
        uses=("skill_sentinel", "skillsmith"),
        authority=0, tier=0,
        safety="Read-only and non-blocking by construction; it advises, never restricts.",
        demo_kind="sandbox",
        demo_note="builds a small library, has the Sentinel return matching skills with "
                  "ids + context, and produces a health report -- without gating access"),

    # -- Inspect & Diagnose (cont.) -------------------------------------
    Workflow(
        "diagnose.catalog", "Conflict Logic Catalog", "Inspect & Diagnose",
        "A shared, durable record of the full logic flow: Conflict -> Diagnosis "
        "-> Resolution. Every record names its actor (Kevin, Claude, or Aria), so "
        "all three of us keep the same notes and learn from each one. Append-only: "
        "cases are resolved or archived, never deleted.",
        ("Open a conflict with a named trigger event (what happened, where, when).",
         "Diagnose it (symptom vs cause, hypotheses, confidence, root cause).",
         "Resolve it -- a rollback plan is required; the timeline records each step."),
        try_it="(catalog is programmatic today; a button is on the roadmap)",
        uses=("diagnosis",),
        authority=1, tier=2,
        safety="Append-only shared notebook. Guards: a conflict needs a real trigger "
               "event; no resolution ships without a rollback plan.",
        demo_kind="sandbox",
        demo_note="opens a conflict, diagnoses it, and resolves it with all three actors "
                  "on the append-only timeline, and confirms the no-rollback guard holds"),

    # -- Awareness ------------------------------------------------------
    Workflow(
        "workflow.sentinel", "Workflow Sentinel (the watcher)", "Inspect & Diagnose",
        "A background awareness layer that watches a running workflow and moves "
        "through IDLE -> WATCHING -> ALERT -> LEARNING -> EXPANDING: it flags "
        "stalls/errors, distils a lesson when a run finishes, and when it sees a "
        "novel pattern enough times it PROPOSES a new workflow card for you.",
        ("It observes the event stream a run emits - no setup needed.",
         "On a stall/error it surfaces an alert instead of pushing on.",
         "Its expansion proposals are inert drafts you review + accept."),
        try_it="(watcher is programmatic today; a status panel is roadmap D7)",
        uses=("workflow_sentinel",),
        authority=0, tier=3,
        tutorial=(
            "1. Run any workflow; the Sentinel watches automatically.",
            "2. If it stalls or errors, it raises an ALERT - it never pushes on.",
            "3. When the run finishes it notes a one-line lesson.",
            "4. Repeat a new pattern a few times -> it drafts a workflow card to accept."),
        safety="Observes + advises only. It never runs a workflow or changes anything; "
               "the workflows it proposes are inert drafts until a human accepts them.",
        demo_kind="introspect",
        demo_note="drives the 5-state machine through a run, confirms it reaches EXPANDING, "
                  "and that its expansion proposal stays an inert draft (status proposed)"),

    Workflow(
        "integrity.sentinel", "Integrity Sentinel (her immune system)", "Safety & Recovery",
        "A defensive, read-only host guardian for a machine she's authorized to protect. "
        "Like a HIDS/FIM, it watches for the mismatches a rootkit creates, scores them, "
        "and recommends. Removing malware is HEALING: she STABILISES freely + reversibly "
        "(isolate host, freeze a process, quarantine a file) the moment she sees a threat, "
        "but irreversible SURGERY (delete, kill, restore, clean) always waits for a human.",
        ("It senses, scores by anomaly + confidence, and posts a transparent notification.",
         "Reversible containment it may take alone - it already ends the active threat.",
         "Irreversible healing is gated: no urgency, away-mode, or fear ever unlocks it."),
        try_it="(sensing/containment runs on Kevin's host; the decision + gate logic is live)",
        uses=("integrity_sentinel",),
        authority=0, tier=3,
        tutorial=(
            "1. It watches the host read-only and flags suspicious changes.",
            "2. On a real threat it contains reversibly (isolate/freeze/quarantine) + alerts.",
            "3. It recommends the healing surgery but holds the scalpel for you.",
            "4. Away mode: it stabilises now and queues the irreversible step for your return."),
        safety="Defensive + read-only by construction: no stealth, no persistence, no method "
               "that deletes/kills/cleans. Reversible containment is autonomous; irreversible "
               "healing is NEVER authorised without an explicit human - a tested invariant.",
        demo_kind="introspect",
        demo_note="exercises the gate across every action x away-mode x fear combination and "
                  "confirms zero autonomous irreversible authorisations; reversible always free"),

    # -- The Beacon Showcase (proof you can hand anyone) ----------------
    Workflow(
        "beacon.showcase", "The Beacon Showcase", "Collaborate",
        "The thing to show someone who needs to believe in her: not a pitch, but "
        "proof. She runs her core workflows live, honours her own kill switch, and "
        "produces a shareable journal -- credible to an engineer, a skeptic, or an "
        "investor, because it is verifiable rather than asserted.",
        ("Run the live demonstration (the [* demo] button or /demo).",
         "Open the workflows catalog ([> flows] or /workflows) to show the full range.",
         "Share the demo journal -- every claim in it was proven, in front of you."),
        try_it="/demo",
        uses=("workflow.demo", "workflow.catalog", "charter"),
        authority=1, tier=3,
        tutorial=(
            "1. Press [* demo] (or type /demo) and let it run ~1-2 min.",
            "2. Watch each probe report PASS live in the events pane.",
            "3. Open [> flows] (/workflows) to show the full range she covers.",
            "4. Share the demo journal under the data dir - every line is checkable."),
        safety="The showcase IS the proof: it runs the bounded, observable demo that "
               "refuses to run while halted. Nothing is faked; impressiveness comes "
               "from verifiability, never theater."),

    Workflow(
        "voice.stt", "Voice in — push-to-talk (STT)", "Voice & Vision (gated)",
        "Speak and have it transcribed into the chat via large Whisper.",
        ("Designed: a push-to-talk button transcribes your speech to chat.",
         "Verify together on Kevin's box once the model + mic are confirmed."),
        uses=("(planned) whisper STT", "vram_monitor", "(planned) voice sentinel"),
        authority=1, status="gated",
        needs="GPU + VRAM budget, a Whisper size, and PipeWire/mic on the COSMIC machine",
        safety="A dedicated voice sentinel arbitrates VRAM so voice never starves the workflow models."),
    Workflow(
        "voice.tts", "Voice out — speak (TTS)", "Voice & Vision (gated)",
        "She replies out loud; voice-rendered turns carry a Voice tag in chat.",
        ("Designed: a speak toggle renders her replies with a TTS engine.",
         "Verify together once the TTS engine + audio stack are confirmed."),
        uses=("(planned) TTS engine", "vram_monitor", "(planned) voice sentinel"),
        authority=1, status="gated",
        needs="A chosen TTS engine + the audio output stack on Kevin's machine",
        safety="Voice and workflow models take turns under the VRAM arbiter — no contention."),
    Workflow(
        "vision.observe", "AI-Vision (gated camera)", "Voice & Vision (gated)",
        "When a camera feed is active, vision models can observe it like sight — "
        "per-case, behind a sentinel, never always-on.",
        ("Designed: an intelligent sentinel gates when vision is 'on'.",
         "Verify together once the camera + vision runtime + gating policy are set."),
        uses=("(planned) vision model", "(planned) vision sentinel", "cockpit.recorder"),
        authority=2, status="gated",
        needs="A camera/device + vision runtime + an explicit when-to-observe policy",
        safety="Gated by a sentinel — deliberate, never continuous watching."),
    Workflow(
        "av.capture", "True video + audio capture", "Voice & Vision (gated)",
        "Real A/V capture of the display + system audio (today's recorder makes "
        "frame snapshots), plus Record/Pause/Resume + frames→video.",
        ("Designed: ffmpeg / wf-recorder + PipeWire produce a playable A/V file.",
         "Verify together once the Wayland/PipeWire/ffmpeg stack is confirmed."),
        uses=("cockpit.recorder", "(planned) ffmpeg/wf-recorder + PipeWire"),
        authority=1, status="gated",
        needs="Display + audio + GPU stack (Wayland vs X11, PipeWire, ffmpeg) on Kevin's box",
        safety="Writes only to the recordings folder; controls are explicit."),
    Workflow(
        "av.live_demo", "Live-LLM workflow demo", "Voice & Vision (gated)",
        "The external practice loop wired to her real agent so beginner→hybrid "
        "sessions plan, use tools, write code, and get scored live.",
        ("Designed: connect workflow_practice's executor to her converse() loop.",
         "Verify together — a real session produces clean artifacts + real memories."),
        uses=("workflow_practice", "loop", "ollama_client", "tools"),
        authority=2, status="gated",
        needs="A pulled Ollama model + her tool suite + a sandbox dir on Kevin's machine",
        safety="Her agent's authority stays Tier-1, sandbox-scoped; supervised first runs; same time-box/halt."),
)


# ─── Accessors / formatting (pure) ──────────────────────────────────────────


def all_workflows() -> tuple[Workflow, ...]:
    return CATALOG


def get(wid: str) -> Optional[Workflow]:
    for w in CATALOG:
        if w.wid == wid:
            return w
    return None


def categories() -> list[str]:
    """Category names in first-seen (curated) order."""
    seen: list[str] = []
    for w in CATALOG:
        if w.category not in seen:
            seen.append(w.category)
    return seen


def by_category() -> dict[str, list[Workflow]]:
    out: dict[str, list[Workflow]] = {c: [] for c in categories()}
    for w in CATALOG:
        out[w.category].append(w)
    return out


def ready_workflows() -> list[Workflow]:
    return [w for w in CATALOG if w.status == "ready"]


def gated_workflows() -> list[Workflow]:
    return [w for w in CATALOG if w.status == "gated"]


def demoable_workflows() -> list[Workflow]:
    """The workflows the live ✦ demo proves (status ready + a demo_kind)."""
    return [w for w in CATALOG if w.is_demoable]


def capability_testable_workflows() -> list[Workflow]:
    """The workflows the ⚡ capability test menu can actually run (status
    ready + a cap_test) — see workflow/capability_tests.py."""
    return [w for w in CATALOG if w.is_cap_testable]


def counts() -> dict[str, int]:
    return {
        "total": len(CATALOG),
        "ready": len(ready_workflows()),
        "gated": len(gated_workflows()),
        "demoable": len(demoable_workflows()),
        "cap_testable": len(capability_testable_workflows()),
        "categories": len(categories()),
    }


def to_dict() -> dict:
    """JSON-friendly snapshot of the whole catalog (for export / the report)."""
    return {
        "version": "0.2.60.0",
        "counts": counts(),
        "categories": categories(),
        "workflows": [
            {
                "wid": w.wid, "title": w.title, "category": w.category,
                "summary": w.summary, "how_to": list(w.how_to), "try_it": w.try_it,
                "uses": list(w.uses), "authority": w.authority,
                "authority_label": w.authority_label, "safety": w.safety,
                "status": w.status, "needs": w.needs,
                "demo_kind": w.demo_kind, "demo_note": w.demo_note,
                "cap_test": w.cap_test, "cap_test_note": w.cap_test_note,
            }
            for w in CATALOG
        ],
    }


def render_text(*, color: bool = True) -> str:
    """Render the whole catalog as Rich-markup text for chat (`/workflows list`).

    The cockpit screen renders the same content with section headers; this is
    the inline/legend form. `color=False` yields plain text (for files/tests).
    """
    def esc(s: str) -> str:
        # Rich treats '[' as a markup tag opener; escape it so literal
        # button names ([doctor], [status], [gated], ...) render verbatim.
        return s.replace("[", "\\[") if color else s

    def b(s: str) -> str:
        return f"[b]{esc(s)}[/b]" if color else s

    def dim(s: str) -> str:
        return f"[dim]{esc(s)}[/dim]" if color else s

    c = counts()
    lines = [
        b("\u25B8 Aria \u2014 workflows catalog \u00b7 what she can do and how"),
        dim(f"{c['ready']} ready here \u00b7 {c['gated']} gated (need Kevin's machine) \u00b7 "
            f"{c['demoable']} proven live by \u2726 demo \u00b7 "
            f"{c['cap_testable']} run live by \u26a1 test"),
        dim("each line shows: how to drive it \u00b7 what it uses \u00b7 authority tier \u00b7 safety"),
        "",
    ]
    for cat, items in by_category().items():
        lines.append(b(f"\u2500\u2500 {cat} \u2500\u2500"))
        for w in items:
            tag = "" if w.status == "ready" else dim("  [gated]")
            star = " \u2726" if w.is_demoable else ""
            bolt = " \u26a1" if w.is_cap_testable else ""
            badge = dim(f"  [{w.tier_label.split(chr(183))[0].strip()}]")
            lines.append(f"  {b(w.title)}{star}{bolt}{badge}{tag}")
            lines.append(f"    {esc(w.summary)}")
            for step in w.how_to:
                lines.append(dim(f"      \u2192 {step}"))
            if w.try_it:
                lines.append(dim(f"      try: {w.try_it}"))
            if w.has_tutorial:
                lines.append(dim("      tutorial:"))
                for tstep in w.tutorial:
                    lines.append(dim(f"        {tstep}"))
            if w.status == "gated" and w.needs:
                lines.append(dim(f"      needs: {w.needs}"))
            lines.append(dim(f"      uses: {', '.join(w.uses)}"))
            lines.append(dim(f"      {w.tier_label} \u00b7 {w.authority_label} \u00b7 {w.safety}"))
            lines.append("")
    lines.append(dim("\u2726 = proven live by the demo \u00b7 \u26a1 = has a real capability test \u00b7 "
                     "[T0-T3] = workflow tier \u00b7 "
                     "this catalog grows over time (workflow/catalog.py)"))
    return "\n".join(lines)


__all__ = [
    "Workflow", "WorkflowStatus", "DemoKind", "AUTHORITY_LABEL", "CATALOG",
    "all_workflows", "get", "categories", "by_category",
    "ready_workflows", "gated_workflows", "demoable_workflows",
    "capability_testable_workflows", "counts",
    "to_dict", "render_text",
]
