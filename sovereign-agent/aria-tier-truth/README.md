# aria-tier-truth

This reviewable patch fixes false Tier-1 reporting without changing authority policy.

It makes the two independent systems explicit:

- **Authority-tool ceiling:** the highest-risk tool available in the active run mode. BUSY correctly remains Tier 1.
- **Autonomy-duration trust tier:** the operator-approved maximum duration for a timed auto session. It may be Tier 1–4 and does not change tool authority.

It also corrects two stale prompt claims: Tier 4 is 12 hours, and BUSY does not have a Tier 3 ceiling.

Review the payload and run `./aria-tier-truth/apply_tier_truth.sh` only with the cockpit stopped. The patch is idempotent; reverting is `git diff`/`git restore` of the two live source files plus removal of `tests/test_tier_truth.py`.

**Applied 2026-08-02.** Two things needed fixing before this could go in, both real, not cosmetic:
1. `mode_tools.py` had drifted live (an unrelated `get_auto_crown_store` import had been dropped at
   some point) — confirmed the payload was a pure superset (nothing live had that payload didn't) before
   applying, since a whole-file `cp` on a diverged file is otherwise a real risk of deleting live work.
2. `test_system_prompt_distinguishes_authority_from_autonomy_trust` asserted the AUTO CROWN section
   (where "Autonomy-duration trust tier" text lives) against `Mode.BUSY` — but `prompt_diet.py`
   (`DROP_FOR_SHORT_HORIZON`, staged after this module) deliberately strips AUTO CROWN for BUSY/oneshot
   as a token-budget decision. Not a bug — the test now checks the authority-ceiling assertion against
   BUSY (ceiling really is 1) and the autonomy-trust-tier text against `Mode.TIMED` (the long-horizon
   mode AUTO CROWN is actually for). 13/13 tests pass; `test_mode_master.py` and
   `test_prompt_diet_live.py` regression-checked clean.
