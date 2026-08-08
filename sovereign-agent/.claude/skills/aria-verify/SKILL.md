---
name: aria-verify
description: Verify a staged aria-<name>/ module end-to-end before applying it — py_compile, run its tests, confirm live src/ is untouched, and confirm tool/sentinel registration anchors are present. Use after building or editing a staged module and before proposing it for apply.
---

# aria-verify — one command for the full pre-apply verification

```bash
./scripts/verify_module.sh aria-<slug>
```

It runs, in order: `py_compile` of the payload → the module's pytest suite → a check that none of the
payload files already exist in live `src/` (staged-only) → a check that the apply script patches tool
registration if the module ships tools.

Report PASS/FAIL plainly. On FAIL, show the failing check's output and fix it before proceeding. A module
that doesn't pass verify is not ready to apply — that's the quality floor.
