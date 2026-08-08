"""
╔══════════════════════════════════════════════════════════════════════════╗
║  marketing_brief.py — generate a structured marketing brief              ║
║  v0.2.15.3 · Aria-Sovereign-V1                                            ║
║                                                                            ║
║  Takes a product/release/feature and decomposes the marketing task into  ║
║  five composable sections, each rendered as one ``compose_section`` step ║
║  the agent runs through the orchestrator. Sections aggregate into a      ║
║  single markdown brief at ``output`` — suitable for handoff to a human   ║
║  marketing operator, or for ``sov drafts archive`` to file under the     ║
║  drafts subsystem.                                                       ║
║                                                                            ║
║  Sections (in order):                                                    ║
║    1. positioning         what we are, who we serve, why we win          ║
║    2. audience            three primary segments with pains & jobs       ║
║    3. messaging           hero line + three tone-graded value props      ║
║    4. channel-copy        web, email, twitter, linkedin, readme          ║
║    5. distribution-plan   sequenced launch sequence with owners + dates  ║
║                                                                            ║
║  This planner is intentionally OPINIONATED on structure — every brief    ║
║  has these five sections, in this order, with this naming. That's what   ║
║  makes the output diffable across releases. Don't add fields ad hoc.     ║
║                                                                            ║
║  Authority tier: 1 (writes markdown to a single output path).            ║
║  No external calls; the orchestrator handles all LLM work.               ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..continuation import Step
from .base import PlanResult, Planner, PlannerError


# The fixed section catalog. Order matters: the runner emits sections in
# this sequence, and downstream readers (and humans) come to expect it.
SECTIONS: tuple[tuple[str, str], ...] = (
    (
        "positioning",
        "Compose the POSITIONING section: a 3–5 sentence statement covering "
        "what the product is, the user it serves best, the single biggest "
        "pain it removes, and what makes it materially different from "
        "alternatives. End with a one-line elevator pitch (≤ 18 words).",
    ),
    (
        "audience",
        "Compose the AUDIENCE section: three primary segments. For each, "
        "give a 1-line persona, the job-to-be-done, the current alternative "
        "they reach for, and the moment they'd consider switching. Order the "
        "three by leverage (most-impacted segment first).",
    ),
    (
        "messaging",
        "Compose the MESSAGING section: one hero line (≤ 10 words), then "
        "three value propositions written in three different tones — "
        "(a) sober technical, (b) confident builder, (c) warm operator. "
        "Each value prop is 2–3 sentences.",
    ),
    (
        "channel-copy",
        "Compose the CHANNEL COPY section: short ready-to-ship copy for "
        "each of: web hero (≤ 50 words), launch email (subject + ≤ 120 "
        "word body), one Twitter/X thread (4 posts, ≤ 280 chars each), "
        "one LinkedIn post (≤ 180 words), README intro paragraph (≤ 80 "
        "words). Label each clearly so an operator can paste it without "
        "reformatting.",
    ),
    (
        "distribution-plan",
        "Compose the DISTRIBUTION PLAN section: a numbered sequence of "
        "launch actions across the first 14 days. For each: action, owner "
        "(role, not name), prerequisite, and the metric that tells us it "
        "worked. End with a single rollback line: what to do if the launch "
        "underperforms the metric on day 7.",
    ),
)


class MarketingBriefPlanner(Planner):
    name = "marketing-brief"
    description = (
        "Generate a structured marketing brief (positioning, audience, "
        "messaging, channel copy, distribution plan) into <output>."
    )

    def required_args(self) -> tuple[str, ...]:
        return ("product", "output")

    def plan(self, **kwargs: Any) -> PlanResult:
        product = kwargs.get("product")
        output_arg = kwargs.get("output")

        if not product:
            raise PlannerError("marketing-brief: 'product' is required")
        if not output_arg:
            raise PlannerError("marketing-brief: 'output' is required")

        product = str(product).strip()
        output = Path(str(output_arg)).expanduser().resolve()

        # Optional context the planner threads into every prompt.
        tone = (kwargs.get("tone") or "candid, technically literate").strip()
        audience_hint = (kwargs.get("audience") or "").strip()
        highlights = kwargs.get("highlights") or []
        if isinstance(highlights, str):
            highlights = [highlights]

        # Optional: skip sections by name (e.g., for an internal-only brief
        # the operator may not want a distribution plan).
        skip = set(s.strip().lower() for s in (kwargs.get("skip") or []))
        sections = [(n, p) for (n, p) in SECTIONS if n not in skip]

        if not sections:
            raise PlannerError(
                "marketing-brief: all sections excluded — nothing to plan"
            )

        steps: list[Step] = []
        for i, (section_name, prompt) in enumerate(sections, start=1):
            args = {
                "product": product,
                "section": section_name,
                "prompt": prompt,
                "tone": tone,
                "output": str(output),
            }
            if audience_hint:
                args["audience_hint"] = audience_hint
            if highlights:
                args["highlights"] = list(highlights)

            steps.append(
                Step(
                    id=i,
                    kind="compose_marketing_section",
                    args=args,
                )
            )

        return PlanResult(
            goal=f"Marketing brief for {product} → {output}",
            steps=steps,
            output_path=str(output),
            notes=(
                "Sections (in order): "
                + ", ".join(name for (name, _) in sections)
            ),
        )

    def render_step(self, step: Step, planner_args: dict) -> str:
        a = step.args
        product = a.get("product", "the product")
        section = a.get("section", "section")
        prompt = a.get("prompt", "")
        tone = a.get("tone", "candid, technically literate")
        audience_hint = a.get("audience_hint", "")
        highlights = a.get("highlights") or []

        parts = [
            f"You are writing the **{section}** section of a marketing brief "
            f"for **{product}**.",
            f"Tone: {tone}.",
        ]
        if audience_hint:
            parts.append(f"Audience hint: {audience_hint}.")
        if highlights:
            parts.append(
                "Anchor concrete claims to these highlights when relevant: "
                + "; ".join(str(h) for h in highlights)
                + "."
            )
        parts.append(prompt)
        parts.append(
            "Output: well-formed markdown, no preamble, no postamble. "
            "Start with a level-2 heading naming the section."
        )
        return "\n\n".join(parts)
