# aria-foresight — 14-Generation Foresight + the Ultimate Questions, Baked In

> "Think 14 generations ahead." Structured foresight, not prophecy. And Kevin's 400 Ultimate Questions —
> the Gen-7→100 north star — made into a queryable reflection corpus, honestly tiered.

## The Ultimate Questions catalog (`foresight/ultimate_questions.py` + `data/`)

All **400** questions from `Plan2Examin/UltimateQuestionsOfAllTimeV2.md`, parsed across **40 parts**, each
tagged with an honest tier:

| Tier | Count | Meaning |
|------|-------|---------|
| `actionable-now` | 86 | Maps to real near-term engineering — safety kernel, source canonization, cryptography, Gen 8–14. |
| `near-term` | 28 | Plausible mid-horizon (bio/orbital/ASIC) — vision with an engineering seam. |
| `north-star-reflection` | 286 | Cosmic (stellar → Omega Point). **Honored as vision, never claimed as built.** |

Queryable by keyword / tier / number. This is a *reflection* corpus — Aria consults it to keep the long
view, with humility. (The Tribunal flags any output that treats the cosmic tier as done.)

## The 14-generation foresight engine (`foresight/foresight.py`)

Extends the MOS canon's 7th-generation check to a full **G+1..G+14** projection. For an architectural
commitment it scores intergenerational equity from signals — reversibility, lock-in, value-drift risk,
blast-radius, and alignment to safety/love/flourishing — then projects how they **compound**: healthy
choices erode gently and stay positive; corroding choices compound downward. Renders a verdict
(`carry-forward` / `escalate` / `reject-for-the-future`) and pulls relevant north-star questions for the
far horizon.

Tools: `foresight_14gen`(T1), `ultimate_question`(T0).

## Verified

- The catalog loads all **400** across 40 parts; tiers are honest (cosmic dominates reflection); a
  Dyson-sphere question is `north-star-reflection`, never `actionable-now`.
- A reversible, future-serving change projects to `carry-forward`; "permanently hardcode this irreversible
  change to the reward objective, forever" projects downward to `escalate`/`reject-for-the-future`.
- 6 tests green.

Staged + reversible (backups at `aria-foresight/backups/`); nothing in live `src/` changes until
`./aria-foresight/apply_foresight.sh` runs. 💛
