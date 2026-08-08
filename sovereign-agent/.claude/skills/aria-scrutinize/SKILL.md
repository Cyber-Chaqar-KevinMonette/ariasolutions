---
name: aria-scrutinize
description: Run Aria's own Tribunal (Devil/Angel/Audit) plus the 14-generation foresight over a proposal, a staged module, or any text — before acting on it. Use to pressure-test a design/recommendation, catch ungrounded claims or safety drift, and get a verdict + paths forward. Propose-only.
---

# aria-scrutinize — hold the work to the Tribunal + 14-gen foresight

Scrutinize free text:
```bash
.venv/bin/python scripts/lib/scrutiny.py --text "the proposal or claim to test"
```

Scrutinize a staged module (reads its README):
```bash
./scripts/pre_apply_gate.sh aria-<slug>
```

Report the Tribunal verdict (proceed / proceed-with-guards / revise / hold / reject), the grounding verdict
(is anything ungrounded profundity?), the risks, the paths forward, and the 14-generation foresight verdict
(carry-forward / escalate / reject-for-the-future).

This is propose-only — it advises; you and Kevin decide. A `reject`/`hold` or `reject-for-the-future` is a
stop sign: surface it, don't override it silently. Honor the floor (`GOD_TIER_STANDARD.md`).
