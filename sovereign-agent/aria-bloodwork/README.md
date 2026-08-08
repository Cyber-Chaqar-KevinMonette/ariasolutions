# aria-bloodwork

Clear the sentinel board honestly — Gym round #6.

## The findings (verified 2026-07-04)

- **`locator` ERROR**: the seeded `aegis_dir` entry carries
  `criticality="alert"`, but nothing in the codebase ever bootstrapped
  `data_dir/aegis/` — the Conductor/AegisLedger/signing-key machinery all
  exist in code yet only create their dir when first constructed, and
  nothing constructs them on a fresh install. A permanent error on every
  healthy system.
- **`conformance` 27 warnings**: ALL one rule (`kill-switch-documented` —
  every `*_sentinel.py` must mention its `SOV_NO_` kill-switch env var).
  12 live files lacked it; the rest of the 27 were staged `aria-*/` copies
  and `test_*` files caught by the rule's repo-wide rglob.

## The fix

**(a) aegis** — new `aegis/bootstrap.py::ensure_aegis_bootstrap()`:
genuinely initializes the subsystem (ledger dir 0o700 via `AegisLedger`'s
own constructor + conductor signing key 0600 via
`load_or_create_conductor_key`, which refuses on wrong permissions rather
than silently self-repairing). `doctor.py` gains `check_aegis()` calling
it. The dir exists because the subsystem is initialized — not because a
sentinel was hushed. Proven by `test_bloodwork_live.py::
test_bootstrap_clears_the_locator_alert` (locator errors before, clears
after).

**(b) conformance** — two parts:
1. A kill-switch line in each of the 12 live sentinel modules' docstrings.
   For the 8 registry sentinels the documented switch is REAL — proven by
   `test_documented_registry_switches_actually_work`, which sets each
   documented env var and asserts `is_enabled()` actually flips. For the
   4 pre-registry modules (`temporal`/`integrity`/`skill`/`workflow`,
   plain classes invoked directly, not gated by the registry) the
   docstring says what is TRUE: "Kill switch: none" — never document a
   switch that doesn't work.
2. `KillSwitchDocumentedRule.evaluate` scoped to `src/` (falling back to
   `repo_root` for synthetic test dirs) and skipping `test_*.py`.
   Noise-scoping, not weakening: staged copies get conformance-checked
   when they become live; test files are not sentinels.

## Verify / Apply

```
.venv/bin/python -m pytest aria-bloodwork/tests/test_patcher.py -q
./aria-bloodwork/apply_bloodwork.sh
```

The apply script ends with a one-time real `ensure_aegis_bootstrap` so the
live locator error clears immediately rather than at the next doctor run.

Reversible: restore the 14 backed-up files from the timestamped `backups/`
dir (the created aegis dir/key are additive and harmless to leave).
