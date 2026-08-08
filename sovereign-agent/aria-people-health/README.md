# aria-people-health — offline health tracking, consent-gated (PH1+PH2)

> Extends the existing People channel with structured health records —
> conditions, medications, allergies, appointments, vitals, notes —
> fully offline (this whole system is already local-SQLite-first), with
> optional document/image references via the existing content-addressed
> archive. Scoped to the principal + explicitly-consented others.
> Propose-only / reversible / staged.

## Why

Kevin: a doctor's-office internet outage blocked things that should have
just worked locally. A full per-person data model already exists
(`sql/003_people.sql`, `mem_channels/people.py`'s `PeopleChannel`) — this
is an extension of it, not a new subsystem.

## The consent gate (structural, not just documented)

`people.health_tracking_consented` defaults `FALSE` for every person
except the principal (`TRUE` at profile creation). `PeopleHealthChannel.
record_health_fact()` **raises** `ConsentRequiredError` — never silently
drops — before any row is written, if the target person is neither the
principal nor explicitly consented. Verified by a dedicated test
(`test_recording_for_a_non_consented_other_never_writes_a_row`) that the
rejected attempt leaves zero rows behind.

## Payload

- `sql/015_people_health.sql` — `people_health_records` table (FK to
  `people.person_id`, bitemporal, redactable, `document_hash` FK into the
  existing `archive` table) + the `health_tracking_consented` column.
- `mem_channels/people_health.py` — `PeopleHealthChannel`: `record_health_
  fact` (consent-gated), `confirm_health_fact`, `retract_health_fact`,
  `redact_health_fact`, `list_health_facts`, `export_person_health` (data
  sovereignty, parity with `PeopleChannel.export_person`).
- `tools/health_record_tool.py` — `RecordHealthFactTool`: Tier 3,
  `requires_approval=True` (third-party health data is irreversible-in-
  consequence even though technically redactable). Resolves the person by
  name via the existing `PeopleChannel.resolve()`.

## What PH3 still needs (not in this module)

- `retrieval/filter.py`'s `_PRIVATE_CHANNELS` — add `"people_health"`.
- `doctor.py`'s channel count — add `"people_health"` to the expected set.
- A third-party-data-consent addendum to `mos_canon.py` — **sealed file,
  STOP AND ASK** before touching it; the exact clause text is proposed for
  Kevin's sign-off, not silently assumed to already be covered.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-people-health     # before apply
./aria-people-health/apply_people_health.sh              # cockpit stopped
```
