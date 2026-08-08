# aria-people-health-privacy — real registration + retrieval privacy + doctor sync (People-Health round · PH3)

> Closes a real gap PH2 left open (the channel never actually registered
> at real app startup), gates health data out of default retrieval the
> same way people/relationships already are, and keeps `sov doctor`'s
> channel count accurate. Propose-only / reversible / staged.

## Payload (in-place patches only — no new files this round)

- `mem_channels/__init__.py` — adds `people_health` to the registration
  import list. Without this, `PeopleHealthChannel`'s `@register_channel`
  never fires outside of tests that import the module directly — a real
  gap, not cosmetic.
- `retrieval/filter.py`'s `_PRIVATE_CHANNELS` — adds `"people_health"`
  alongside `"people"`/`"relationships"`.
- `doctor.py`'s expected channel set — adds `"people_health"` so `sov
  doctor`'s channel-count check stays accurate.

## What this module does NOT do

Does not touch `mos_canon.py` (sealed file). The third-party-data-consent
addendum this round's plan calls for is proposed separately, in chat, for
explicit sign-off — not silently added here.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-people-health-privacy     # before apply
./aria-people-health-privacy/apply_people_health_privacy.sh      # cockpit stopped
```
