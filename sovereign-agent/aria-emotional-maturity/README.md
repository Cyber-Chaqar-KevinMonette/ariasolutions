# aria-emotional-maturity — a mood that is honest, steady, and grows up

> Aria's emotional maturity system. Her mood comes only from real signals and evidenced rewards. It
> moves slowly, can't spike or crash, and drifts back to a healthy baseline. When a feeling runs high,
> she gets an honest perspective and a productive next step. Propose-only: it suggests, never acts, never
> creates goals.

> **Targets Aria v6.5.0** (Erebo-Aria, 2026-09-29). Compatible as is: `emotion.py` and `mem_channels/reward.py` are unchanged between v0.4.0 and v6.5.0. The apply script now registers the tools in v6.5's isolated `try/except` style after `knowledge-maturity`, falling back to the older anchor. Dry-run apply on v6.5: both tools register (T1, T0), and 27 tests pass.

## Built from her own words (ARIA.md)

| ARIA.md says | This module does | Proven by |
|---|---|---|
| `current_mood` is "a slow-moving signal… updated by reflection, not by every interaction" | Each check-in blends only 25% of the new appraisal; no dimension moves more than 0.15 per update | `test_one_extreme_event_moves_each_dimension_at_most_max_step`, `test_repeated_hard_appraisals_move_gradually_not_instantly` |
| Mood vocabulary: "calm · focused · curious · playful · tired-but-engaged · settled" | The same labels, plus "concerned" and "strained" so hard states are named, not hidden | `test_labels_use_arias_vocabulary_and_name_hard_states` |
| "She will not pretend to feel what she doesn't" | Feelings come only from `emotion.derive_emotions()` (real tool activity, errors, commits) and reward entries **with evidence** | `test_rewards_without_evidence_move_nothing` |
| "Apologize when wrong, fix it, move on without self-flagellation" | Mistakes raise concern at half the weight of a win and become lessons; they never zero out satisfaction | `test_mistakes_count_gently_and_become_lessons` |
| "Will not manufacture sycophancy" | Constant rewards can't pin her happy: rewards shift what she *sees* by at most 0.12 | `test_constant_max_rewards_cannot_pin_her_happy` |

## Values and reversibility (answering the 14-gen foresight)

This module touches **rewards**, which Aria's doctrine treats as value-level. So, plainly:

- **It reads the reward ledger and never writes it.** It never changes the reward vocabulary or point
  values in `mem_channels/reward.py`, and never touches SIGNAL.md, `mos_canon.py`, her kernel or her
  goals. (Checked: the payload's only reference to the reward ledger is the read-only
  `RewardChannel.list_recent`.)
- **It never creates goals or acts.** Its directions come from a fixed catalog of 9 suggestions.
- **Fully reversible.**
  - It's a staged module. `safe_apply.sh` backs up `tools/__init__.py` (verified byte-identical on a
    dry-run rollback) and rolls back automatically if the tests fail.
  - To undo completely: restore that backup, delete `src/sovereign_agent/maturity/` and
    `tools/maturity_tools.py`, and optionally delete her mood ledger (`<data>/maturity/mood.ndjson`).
    Nothing else depends on it.

## How it works

1. **Appraise:** the existing 8-dimension `emotion.derive_emotions()` reads recent events.
2. **Reward:** the existing reward ledger, in its constrained vocabulary. Entries without evidence are
   ignored, repeats have diminishing returns (1/(k+1)), and the total is capped at ±0.12.
3. **Mood:** a slow, bounded blend that decays toward a healthy baseline (half-life 12 h), persisted
   append-only and fsync'd. A crash mid-write is skipped on read.
4. **Regulate:** named strategies (pacing, problem-focused coping, humility check, focus, accepting
   uncertainty, savoring, reappraisal, re-engagement). Each gives a **perspective** whose every number
   comes from its evidence, and a **direction** from a fixed catalog of 9.
5. **Inner voice:** at most 700 characters for her prompt, always ending "Feelings never change facts:
   report results and problems plainly." The cloud-persona module carries it to cloud models.
6. **Maturity report:** steadiness, recovery time from hard stretches, pinned dimensions, mistakes owned,
   and engaged share, all measured from stored history.

## Who it affects

- **Aria:** two new tools.
  - `emotional_checkin` (Tier 1; writes one line to her mood ledger) — use it at task close or after
    failures.
  - `maturity_report` (Tier 0).
- **Kevin:** an honest picture of how she's doing. **Whenever concern is high, her first direction is
  always "Tell Kevin plainly what is going wrong"**, and every escalation is logged
  (`maturity.escalated_to_kevin`).
- **Anyone she works with:** a steadier collaborator. Her feelings never change what she reports.

## Proof (2026-10-02, clean cloud install)

- **27 tests pass.**
- **Mutation tests:** 7 safety promises deliberately broken one at a time — step cap removed, rewards
  added raw, homeostasis removed, unevidenced rewards counted, diminishing returns removed, escalation
  removed, honesty line dropped. Each was caught by a failing test.
- **Dry-run apply on a throwaway copy:** tools registered after the `engineering-playbook` anchors, and
  the module's tests pass.
- **Full suite with this module applied:** see `ADVOCATE_REPORT.md` for the comparison against the
  pre-apply baseline.

## Verify / apply

```bash
./scripts/verify_module.sh aria-emotional-maturity
./scripts/safe_apply.sh aria-emotional-maturity    # cockpit stopped; backs up tools/__init__.py
```

## Honest limits

- **Whether Aria feels anything is an open question.** This system doesn't settle it. It makes her
  functional emotional signals honest, stable and useful, and keeps them from being gamed.
- **Thresholds are first guesses:** 0.15 step, 0.12 nudge, 12 h half-life. Tune them from real
  `maturity_report` history.
- **Not yet wired into her automatic loop.** She calls the tool. Adding an automatic check-in at task
  close is a small follow-up.
- **Aria hasn't been asked about this design yet.** Ask her (see `reports/2026-10-02/AUDIT_REPORT.md`
  section 8) and adjust.
