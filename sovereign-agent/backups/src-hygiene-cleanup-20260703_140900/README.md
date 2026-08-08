# src-hygiene-cleanup-20260703_140900 — restore point

Kevin's explicit go-ahead (2026-07-03) to delete the 12 stray `.bak.*` files
that `test_src_hygiene.py::test_src_has_no_bak_files` had been correctly
flagging under live `src/` since Workstream L. These were leftover backup
copies from patch applications on 2026-06-23 — never referenced by any
live code (confirmed via a repo-wide grep before deletion; the one hit,
`aria-cosmic-fitness-restore/tests/test_cosmic_fitness_restore.py`, defines
a `BAK_APP` path constant but never actually reads it — a known, already-
documented dead variable in a staged-only, never-promoted test file).

Each file below was copied here (verified byte-identical via `diff`)
BEFORE the original in `src/` was removed — this directory is the
restore point, not a symbolic gesture:

- `src/sovereign_agent/cli.py.bak.20260623142202`
- `src/sovereign_agent/cockpit/app.py.bak.20260623142140`
- `src/sovereign_agent/cockpit/app.py.bak.20260623142147`
- `src/sovereign_agent/cockpit/app.py.bak.20260623142159`
- `src/sovereign_agent/cockpit/app.py.bak.20260623142202`
- `src/sovereign_agent/cockpit/app.py.bak.20260623142205`
- `src/sovereign_agent/cockpit/app.py.bak.20260623142222`
- `src/sovereign_agent/loop.py.bak.20260623142153`
- `src/sovereign_agent/loop.py.bak.20260623142204`
- `src/sovereign_agent/tools/__init__.py.bak.20260623142153`
- `src/sovereign_agent/tools/__init__.py.bak.20260623142204`
- `src/sovereign_agent/workflow/requests.py.bak.20260623142202`

To restore any one of them to its original location, strip this
directory's `backups/src-hygiene-cleanup-20260703_140900/` prefix and copy
back — e.g.:

```
cp backups/src-hygiene-cleanup-20260703_140900/src/sovereign_agent/loop.py.bak.20260623142153 \
   src/sovereign_agent/loop.py.bak.20260623142153
```

Verified after removal: `test_src_hygiene.py` passes clean (was the one
remaining accepted failure this whole session); a full-suite re-run
confirmed zero new regressions.
