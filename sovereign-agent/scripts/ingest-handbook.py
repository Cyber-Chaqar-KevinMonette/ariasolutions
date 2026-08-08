#!/usr/bin/env python3
"""
ingest-handbook.py — seed the agent's LessonsChannel with curated
patterns from the operator handbook.

Idempotent: each lesson has a stable idempotency_id ('hb-N-slug'), so
running this twice writes exactly the same set the first time wrote.

Run as:
    python3 scripts/ingest-handbook.py

What it does:
    1. Opens atoms.db via the agent's standard helper.
    2. For each curated lesson, calls LessonsChannel.write_lesson with
       a fixed idempotency_id. The channel's _find_by_idempotency
       returns the existing atom if one was already written — so
       re-runs are no-ops on a populated DB.
    3. Reports: ingested / already-present / total.

Why lessons (and not palace triples or another channel):
    LessonsChannel.spec.voice says: "Earned. Each one bought with at
    least one mistake." The handbook patterns ARE earned — the safe
    bulk-edit pattern, the pre-dream snapshot, the label-generously
    rule were all built around real failures in this conversation. So
    'lessons' is the right home.

What this script does NOT do:
    - It doesn't ingest the entire handbook prose. That would be
      noise. We curate.
    - It doesn't dedupe by content similarity. It dedupes by ID. If
      you want to change a lesson's content, change its rule text AND
      its idempotency_id.
    - It doesn't write to palace, channels other than lessons, or any
      Tier 3 store. Lessons is Tier 2.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Lesson:
    """One curated handbook lesson destined for the lessons channel."""
    slug: str           # short id-tail; full id is f"hb-{slug}"
    rule: str           # the rule itself, ≤120 chars
    evidence: str       # why this is true — anchored in a real event
    trigger: str = ""   # when to recall this — "before <X>", "when <Y>"
    confidence: float = 0.9   # earned ones are higher

    @property
    def idempotency_id(self) -> str:
        return f"hb-{self.slug}"


# ─── The curated set ────────────────────────────────────────────────────────
# Each entry is something an operator working this system should
# internalize. Drawn directly from patterns documented in the handbook
# AND from incidents in this conversation that produced the rules.

LESSONS: tuple[Lesson, ...] = (
    Lesson(
        slug="snap-before-tier3",
        rule="Take a labeled snapshot before any Tier 3 or destructive operation.",
        evidence=(
            "v0.2.14.1 upgrade and v0.2.14.2 backup-system build both "
            "produced moments where rollback was needed; pre-labeled "
            "snapshots made it a one-command recovery. The pre-restore "
            "auto-snapshot proved its value when default backup root "
            "was inside data_dir."
        ),
        trigger="before sov-restore, before ./install.sh / uv sync, before bulk edits",
    ),
    Lesson(
        slug="label-generously",
        rule="Label snapshots, continuations, and projects generously. Retention never penalizes verbose labels.",
        evidence=(
            "v0.2.14.2 retention policy keeps labeled snapshots forever. "
            "Unlabeled snapshots compete in time buckets; labels exempt them. "
            "Future-you doesn't know what past-you was thinking unless past-you "
            "wrote it down."
        ),
        trigger="every sov-snap, every sov continuations alias, every sov projects scan",
    ),
    Lesson(
        slug="backup-root-outside-data",
        rule="The backup root MUST live outside the data dir. A nested root is destroyed by restore.",
        evidence=(
            "v0.2.14.2 mid-build bug: original default fallback put backup_root "
            "inside data_dir. Restore atomically renames data_dir, obliterating "
            "snapshots stored inside it. _validate_backup_root() now refuses "
            "nested configurations at runtime. See TestCircularDependency."
        ),
        trigger="when configuring a custom --root, when troubleshooting missing snapshots",
    ),
    Lesson(
        slug="sqlite-online-backup-not-cp",
        rule="Never `cp -r` an active SQLite database. Use Connection.backup() for crash-consistency.",
        evidence=(
            "v0.2.14.1 sov-backup shell function used cp -r and could "
            "produce torn snapshots under concurrent writes. v0.2.14.2 "
            "replaced this with the SQLite online backup API. The "
            "crash-consistency probe in test_backup.py asserts the new "
            "path passes PRAGMA integrity_check even under thread-based "
            "writer pressure."
        ),
        trigger="when designing any backup, mirror, or replication path",
    ),
    Lesson(
        slug="sandbox-is-ephemeral",
        rule="The sandbox/ directory is ephemeral. Never include it in backups or restores.",
        evidence=(
            "v0.2.14.2 first-run snapshot crashed on a broken symlink at "
            "sandbox/escape (a sandbox-escape test artifact). v0.2.14.3 "
            "excluded sandbox from EXCLUDED_PATTERNS and hardened the "
            "walker against non-regular files. Real persistent state lives "
            "in atoms.db, events.db, and blobs/."
        ),
        trigger="when adding new excluded patterns, when reviewing snapshot contents",
    ),
    Lesson(
        slug="audit-before-trust",
        rule="Run audit() invariants before trusting a database, especially a staged or restored one.",
        evidence=(
            "v0.2.14.2 restore() opens the staged atoms.db read-only and "
            "runs financial.audit() BEFORE swapping it for live data. "
            "Refuses the restore if violations found. The whole agent "
            "rests on the ledger being honest; file hashes alone cannot "
            "prove that."
        ),
        trigger="before sov-restore, after suspected corruption, weekly hygiene",
    ),
    Lesson(
        slug="protocol-zero-is-cheap",
        rule="`sov halt` is cheap. Use it the moment something feels off. Investigate, then disarm.",
        evidence=(
            "PROTOCOL-ZERO halts at the next iteration boundary. Nothing "
            "important is lost. The cost of an unnecessary halt is "
            "negligible; the cost of letting a confused agent continue is "
            "unbounded. The seven commitments include 'halt cheaply'."
        ),
        trigger="when agent behavior surprises you, when planning a destructive change",
    ),
    Lesson(
        slug="impact-score-estimates-matter",
        rule="Score impact even when uncertain. The delta between estimate and actual teaches more than either alone.",
        evidence=(
            "Impact atoms feed the Reflector's pattern-learning. A guess "
            "today corrected in three months > a perfect score with no "
            "comparison point. The Reflector learns from the delta."
        ),
        trigger="after any significant action, especially decisions you'd rate ≥3 on social or time scales",
    ),
    Lesson(
        slug="reject-over-delete",
        rule="Reject proposals; don't delete them. Reject preserves audit; delete erases history.",
        evidence=(
            "sov proposals reject creates a permanent rejection record. "
            "sov proposals delete hard-removes the proposal. The Reflector "
            "can learn from rejected ideas; it cannot learn from absences."
        ),
        trigger="when reviewing pending proposals",
    ),
    Lesson(
        slug="alias-continuations-immediately",
        rule="Alias every continuation immediately. IDs are forgettable; names are not.",
        evidence=(
            "sov continuations alias <id> <name> attaches a human-readable "
            "handle that survives across days. ULIDs do not survive the "
            "human attention span. Recovery from a stuck continuation is "
            "much harder when you can't remember which one it is."
        ),
        trigger="immediately after starting any continuation that may live more than one session",
    ),
    Lesson(
        slug="halt-is-not-stop",
        rule="`sov halt` preserves state. `agent-stop` terminates the service. Default to halt for ops; stop only for service changes.",
        evidence=(
            "halt trips PROTOCOL-ZERO at the iteration boundary — clean. "
            "agent-stop kills the systemd unit — agent tries to land "
            "cleanly but no guarantee on mid-step state. They are not "
            "interchangeable. Use the right tool for the situation."
        ),
        trigger="when pausing the agent for any reason",
    ),
    Lesson(
        slug="approval-reason-always",
        rule="Always pass --reason to sov approve/deny. Future-you needs the why, not the yes.",
        evidence=(
            "Approval atoms include the rationale field. 'approved by "
            "kmon' three months later is useless context. 'approved by "
            "kmon: needed to roll back the experiment after output "
            "corrupted lessons channel' tells the full story."
        ),
        trigger="every time you approve or deny a Tier 3 request",
    ),
    Lesson(
        slug="dream-with-snapshot",
        rule="Always snapshot before `sov dream resume --drive`. Dreams are autonomous; rollbacks are cheap.",
        evidence=(
            "Dreams produce files in their work_dir, may modify channel "
            "state, and run for hours. A labeled pre-dream snapshot turns "
            "an unhappy outcome into a single restore command. The dream's "
            "work_dir artifacts survive restore (by design) so nothing "
            "interesting is lost."
        ),
        trigger="before sov dream start --drive or sov dream resume --drive",
    ),
    Lesson(
        slug="doctor-first-then-deeper",
        rule="sov-doctor before any deeper diagnosis. The first red section is the first thing to investigate.",
        evidence=(
            "The doctor has four sections (install, ledger, aria, backup) "
            "with explicit pass/fail. Following the trail it surfaces is "
            "more efficient than guessing where the problem is. Each "
            "section's specific audit command tells you what specifically."
        ),
        trigger="every morning, after any anomaly, before opening any incident",
    ),
    Lesson(
        slug="paths-via-symlink",
        rule="AGENT_SRC should point at a version-current symlink, not a versioned dir. Upgrades become a one-liner.",
        evidence=(
            "Original bashrc had AGENT_SRC=$EREBO_HOME/sovereign-agent-v0.2.10, "
            "stale through three upgrades. Pattern adopted: ln -sfn "
            "<v.X.Y.Z> sovereign-agent-current, then sed AGENT_SRC to the "
            "stable name. Future upgrades only retarget the symlink; "
            "bashrc never changes again."
        ),
        trigger="when scripting an upgrade workflow, when documenting onboarding",
    ),
    Lesson(
        slug="event-seal-is-honesty",
        rule="A failed `sov verify` of a sealed event log is a four-alarm fire. The agent's honesty rests on inviolate seals.",
        evidence=(
            "Merkle-sealing the daily event log makes after-the-fact "
            "insertion or deletion detectable. If a seal fails to verify, "
            "either the log was tampered with or seals are being computed "
            "wrong. Either way: stop, restore to last known good, "
            "investigate before resuming."
        ),
        trigger="if sov verify <date> ever returns ✗",
    ),
    Lesson(
        slug="restore-the-restore",
        rule="Every restore auto-creates a pre-restore snapshot. Restoring a restore is one command.",
        evidence=(
            "v0.2.14.2 backup_mod.restore() snapshots current state with "
            "label 'pre-restore-<timestamp>' BEFORE swapping. If the "
            "restore was a mistake, sov backup list shows the pre-restore "
            "snapshot; sov-restore <that-label> reverses it cleanly."
        ),
        trigger="when a restore turns out to be wrong; teach this in onboarding",
    ),
    Lesson(
        slug="health-cant-fix-data",
        rule="`sov health repair` clears zombies and ghosts. It cannot reconstruct lost data. Use sov-restore for that.",
        evidence=(
            "Health checks for process/state mismatches: continuations "
            "marked running with no live runner, ghosts whose status "
            "contradicts progress. Repair is safe (it ends false-positive "
            "states). For data-level corruption: sov-verify + sov-restore."
        ),
        trigger="after a reboot/crash, when a continuation 'won't budge'",
    ),
    Lesson(
        slug="snapshot-mutate-snapshot",
        rule="The snapshot–mutate–snapshot pattern is the safest bulk-edit. Both ends recorded; rollback trivial.",
        evidence=(
            "Composition pattern D in the handbook: sov-snap pre-edit; "
            "sov projects scan; sov do <bulk edit>; sov projects update "
            "(see the diff); if good → sov impact score, if bad → "
            "sov-restore. Three primitives composed for full reversibility "
            "with full visibility."
        ),
        trigger="before any large-scale edit, refactor, or rename across files",
    ),
    Lesson(
        slug="palace-is-for-beliefs",
        rule="Palace = durable beliefs. Channels = typed streams. Events = activity log. Don't confuse the three.",
        evidence=(
            "Palace stores subject-predicate-object triples (\"what the "
            "agent thinks about X\"). Channels store typed atoms (lessons, "
            "financial entries, identity). Events store the action log "
            "(\"what the agent did\"). Use sov palace subject <X> for "
            "beliefs; sov channels for streams; sov events for actions."
        ),
        trigger="when deciding which read command will answer your question",
    ),
)


# ─── Main ───────────────────────────────────────────────────────────────────


def main() -> int:
    """Ingest the curated lesson set; report counts."""
    try:
        from sovereign_agent.db import open_atoms_db
        from sovereign_agent.mem_channels.lessons import LessonsChannel
        from sovereign_agent.channels import _find_by_idempotency
    except ImportError as exc:
        print(f"✗ sovereign-agent not importable: {exc}", file=sys.stderr)
        print("  Is the venv activated? Try: source ~/.bashrc", file=sys.stderr)
        return 2

    conn = open_atoms_db()
    try:
        ch = LessonsChannel(conn)

        already_present: list[str] = []
        ingested: list[str] = []

        for lesson in LESSONS:
            # write_atom is naturally idempotent when given an
            # idempotency_id (it returns the existing atom_id without
            # re-writing). We pre-check so we can REPORT which lessons
            # were new vs already present — write_atom alone returns
            # the same atom_id either way.
            existing = _find_by_idempotency(
                conn, ch.spec.name, lesson.idempotency_id,
            )
            if existing is not None:
                already_present.append(lesson.slug)
                continue

            ch.write_atom(
                summary=f"LESSON: {lesson.rule}",
                content={
                    "rule": lesson.rule,
                    "evidence": lesson.evidence,
                    "trigger": lesson.trigger,
                },
                confidence=lesson.confidence,
                actor="handbook-ingest",
                idempotency_id=lesson.idempotency_id,
            )
            ingested.append(lesson.slug)

    finally:
        conn.close()

    print(f"◊ handbook ingest complete")
    print(f"  ingested:        {len(ingested)} new lessons")
    print(f"  already present: {len(already_present)} lessons (idempotency hits)")
    print(f"  total in set:    {len(LESSONS)}")
    if ingested:
        print()
        print("  new lessons:")
        for slug in ingested:
            print(f"    + hb-{slug}")
    if already_present and len(already_present) < len(LESSONS):
        print()
        print("  re-running is a no-op; lessons are matched by idempotency_id.")
    print()
    print("  read them back with:  sovereign channels show lessons")
    print("  (note: 'sov lessons' shows Reflector-distilled output,")
    print("   not channel atoms; use 'channels show' to see ingested ones.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
