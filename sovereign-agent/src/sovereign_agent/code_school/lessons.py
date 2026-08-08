"""lessons — the curriculum, as verifiable data.

Every lesson cites a real file in this repo and a real commit. That is the
whole point: Kevin owns a ~100k-line production system he can't yet fully
read, and generic tutorials teach syntax while the thing that makes someone
reliable is reading real code and debugging real failures.

Lessons are DATA, never LLM-generated at runtime. A model confidently
inventing a detail about his own codebase would teach him something false
about the system he depends on — the same "never hallucinates a number"
discipline `game_dev_xp.py` already holds. `test_code_school.py` asserts
every cited file still exists, so a lesson can't quietly rot into fiction.

The seed corpus is the six bugs found on 2026-08-03/04. Every one of them
looked healthy from the outside, which is exactly what makes them worth
teaching — and Kevin watched all six happen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Lesson", "LESSONS", "for_track", "by_id", "ordered_for_track"]


@dataclass(frozen=True)
class Lesson:
    id: str
    track: str
    title: str
    file: str                      # repo-relative, asserted to exist
    symptom: str                   # what it looked like from outside
    reality: str                   # what was actually happening
    principle: str                 # the transferable rule
    commit: str = ""
    drill: str = ""                # drill id, if this lesson has one
    order: int = 100
    tags: list[str] = field(default_factory=list)


LESSONS: list[Lesson] = [
    Lesson(
        id="swallowed-exception",
        track="python", order=10,
        title="`except: pass` turned a total failure into apparent health",
        file="src/sovereign_agent/discord_admin/bot.py",
        commit="0cb31c8",
        symptom="Bot connected to Discord. 51 commands answered normally. "
                "Zero errors in the log. Everything looked fine.",
        reality="Every command-tree sync had been failing. One command had a "
                "108-character description (Discord's limit is 100), so the "
                "API rejected the ENTIRE payload with error 50035. No new "
                "command had registered for as long as that description "
                "existed. The failure was caught and discarded.",
        principle="Catching an exception without recording it converts a "
                  "loud failure into a silent one. If you must swallow, log "
                  "first. A system that cannot fail visibly cannot be "
                  "trusted when it says it's healthy.",
        drill="fix-the-swallow",
        tags=["error-handling", "observability"],
    ),
    Lesson(
        id="health-check-ignored-the-output",
        track="python", order=20,
        title="A health check that never checked whether output was possible",
        file="src/sovereign_agent/bot_health.py",
        commit="0cb31c8",
        symptom="`sov bots health` reported 79 of 89 bots healthy, "
                "'delivering normally'.",
        reality="23 of them had no webhook configured at all — no delivery "
                "target, so they physically could not post. The check looked "
                "at sources, queue depth, dead-letters and last-delivery "
                "age. It never asked whether there was anywhere to send. "
                "#condos and #apartments had been empty since creation.",
        principle="A health check must verify the OUTPUT path, not just the "
                  "inputs and the internals. Ask the question the user "
                  "actually cares about — 'did it reach anyone?' — not the "
                  "questions that are easy to measure.",
        drill="check-the-output",
        tags=["health-checks", "design"],
    ),
    Lesson(
        id="duplicate-registration",
        track="python", order=30,
        title="One duplicate name un-registered every command in the bot",
        file="tests/test_command_names_unique.py",
        commit="0cb31c8",
        symptom="New slash commands simply didn't appear in Discord. The "
                "process was up and older commands worked.",
        reality="`/buy` and `/leaderboard` were each declared twice. "
                "discord.py raises CommandAlreadyRegistered during startup, "
                "which aborts the whole registration pass — so everything "
                "after the duplicate silently never registered.",
        principle="When a registry raises on conflict, one bad entry can "
                  "take out the entire set, not just itself. Prefer a check "
                  "that runs in tests over discovering it from a live log.",
        drill="find-the-duplicate",
        tags=["registries", "testing"],
    ),
    Lesson(
        id="phantom-role",
        track="python", order=40,
        title="A permission naming a role that never existed",
        file="src/sovereign_agent/discord_admin/blueprint.py",
        commit="6add74f",
        symptom="Nothing. No error, no warning, no log line.",
        reality="The ADMIN category granted `allow_roles=['Aria', 'Staff']` "
                "and hid sensitive channels with `hide_from=['Staff']`. No "
                "role named Staff ever existed — the real one is Support. "
                "Discord ignores an overwrite for a role it can't find, so "
                "Camden could never open ADMIN (its entire purpose) AND the "
                "owner-only channels were never actually restricted.",
        principle="A reference to a name that doesn't exist usually fails "
                  "SILENTLY, and can fail open and closed at the same time. "
                  "Validate that identifiers resolve to something real — "
                  "especially in security config.",
        drill="validate-the-reference",
        tags=["security", "config"],
    ),
    Lesson(
        id="slice-assumed-position",
        track="python", order=50,
        title="A `[1:]` slice ate a whole category when index 0 changed",
        file="src/sovereign_agent/verticals.py",
        commit="0cb31c8",
        symptom="Warframe vanished from /my-panel. Nothing errored.",
        reality="`subscribable_categories()` hardcoded that index 0 was "
                "TRACKERS and iterated `SUBSCRIBABLE_CATEGORIES[1:]` to skip "
                "it. When TRACKERS was removed from that tuple, the slice "
                "silently skipped WARFRAME instead, making it "
                "unsubscribable.",
        principle="Never encode a position when you mean an identity. "
                  "`[1:]` says 'whatever happens to be first' — if you mean "
                  "'except TRACKERS', say that by name.",
        drill="name-not-position",
        tags=["correctness", "refactoring"],
    ),
    Lesson(
        id="curve-not-monotone",
        track="python", order=60,
        title="A level curve that made level 2 easier than level 1",
        file="src/sovereign_agent/member_levels.py",
        commit="0cb31c8",
        symptom="The XP formula looked reasonable: `A*n² + B*n + C`.",
        reality="With a constant term, reaching level 1 cost 100 xp but "
                "level 2 only cost 60 more. The curve dipped instead of "
                "rising. Caught by a test asserting the per-level cost was "
                "sorted — not by reading the formula.",
        principle="Test the PROPERTY you actually care about ('each level "
                  "costs more than the last'), not a handful of example "
                  "values. Properties catch the cases you didn't imagine.",
        drill="monotone-curve",
        tags=["testing", "math"],
    ),
    Lesson(
        id="logs-are-not-truth",
        track="aisys", order=10,
        title="'sent via webhook' did not mean anyone received it",
        file="scripts/scan_listings.py",
        commit="0cb31c8",
        symptom="Run records showed `sent: true, detail: 'sent via webhook'`. "
                "The pipeline reported success.",
        reality="That only proves Discord returned 2xx to an HTTP POST. It "
                "says nothing about whether a usable message rendered in a "
                "channel a human reads. The only way to know was to read the "
                "channels back — which found several that had been empty "
                "since the day they were created.",
        principle="An agent's own logs describe what it TRIED, not what "
                  "happened. For anything that matters, verify at the "
                  "destination — read back the state you claim you changed.",
        drill="verify-at-destination",
        tags=["agents", "verification"],
    ),
    Lesson(
        id="fail-safe-toward-not-acting",
        track="aisys", order=20,
        title="Why the reconciler reports instead of guessing",
        file="src/sovereign_agent/stripe_reconcile.py",
        symptom="A paid Stripe subscription that can't be matched to a "
                "Discord member does nothing automatically.",
        reality="That's deliberate. The reconciler is read-only against "
                "Stripe, only revokes with positive evidence, and never "
                "attributes an unmatched payment to a member. It would "
                "rather leave money unfulfilled than grant a stranger's "
                "purchase to the wrong person.",
        principle="When an autonomous loop is uncertain, the safe default is "
                  "to REPORT, not to act. Design the failure mode before the "
                  "happy path: ask 'what does this do when it's wrong?'",
        drill="",
        tags=["agents", "safety"],
    ),
    Lesson(
        id="tools-declare-their-danger",
        track="aisys", order=30,
        title="How a tool earns the right to act",
        file="src/sovereign_agent/authority.py",
        symptom="Every tool in the system declares `failure_modes`, and "
                "Tier 3 requires human approval.",
        reality="Capability and permission are separate concerns. A tool "
                "that CAN delete a file doesn't get to decide whether it "
                "SHOULD. The authority gate sits between them, and the tier "
                "is declared by the tool rather than inferred at the call "
                "site.",
        principle="In an agent system, separate 'what this can do' from "
                  "'what this is allowed to do right now'. Encode the "
                  "danger next to the capability so the gate can't be "
                  "forgotten by a new caller.",
        drill="",
        tags=["agents", "safety", "architecture"],
    ),
]

LESSONS_BY_ID = {ls.id: ls for ls in LESSONS}


def for_track(track: str) -> list[Lesson]:
    return [ls for ls in LESSONS if ls.track == (track or "").lower()]


def ordered_for_track(track: str) -> list[Lesson]:
    """Teaching order — `order` first, then id so ties are deterministic."""
    return sorted(for_track(track), key=lambda ls: (ls.order, ls.id))


def by_id(lesson_id: str) -> Lesson | None:
    return LESSONS_BY_ID.get((lesson_id or "").strip().lower())
