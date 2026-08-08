"""Provision default hygiene schedule entries idempotently."""
import sys
sys.path.insert(0, "src")

from sovereign_agent.schedule import ScheduleEntry, ScheduleStore, _schedule_path

DEFAULT_ENTRIES = [
    ScheduleEntry(
        name="daily-eval",
        cron="0 7 * * *",
        directive=(
            "call eval_score() to check the 7-day composite score. "
            "If it has dropped by more than 10 points from last week, "
            "call notify(title='Eval Score Drop', body='Score dropped >10 pts — investigate') "
            "and log_experience about what might have caused it."
        ),
        tier=0,
        description="Daily 07:00 UTC — eval score check with notification on drops",
        enabled=True,
    ),
    ScheduleEntry(
        name="weekly-compact-preview",
        cron="0 9 * * 1",
        directive=(
            "call atoms_compact_preview(before_days=90) to check how many atoms are compaction candidates. "
            "If more than 100 candidates are found, call notify(title='Compaction Due', "
            "body='100+ atoms ready for compaction — consider running atoms_compact(before_days=90)')."
        ),
        tier=0,
        description="Monday 09:00 UTC — weekly atoms compaction preview",
        enabled=True,
    ),
    ScheduleEntry(
        name="weekly-reflection",
        cron="5 9 * * 1",
        directive=(
            "call weekly_reflection() to synthesize last week's experiences, eval score, "
            "session briefs, and hypothesis confirmations into a weekly-reflection atom. "
            "This is the crew brief for the next session — do it even if the week was quiet."
        ),
        tier=0,
        description="Monday 09:05 UTC — weekly synthesis reflection atom",
        enabled=True,
    ),
]

path = _schedule_path()
store = ScheduleStore(path)
existing = store.load()
existing_names = {e.name for e in existing}

added = []
for entry in DEFAULT_ENTRIES:
    if entry.name not in existing_names:
        store.add(entry)
        added.append(entry.name)
        print(f"  + added schedule entry: {entry.name}")
    else:
        print(f"  ✓ schedule entry already present: {entry.name}")

if added:
    print(f"  Provisioned {len(added)} new schedule entries.")
else:
    print("  All default entries already present.")
