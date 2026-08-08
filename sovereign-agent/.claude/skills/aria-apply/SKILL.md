---
name: aria-apply
description: Guided apply of a staged aria-<name>/ module — runs the pre-apply Tribunal+foresight gate, checks the cockpit is stopped, and walks through running the module's apply script and tests. Use when the human is ready to promote a verified module into live src/. Apply itself is a human-run, reversible action.
---

# aria-apply — promote a staged module (human-gated, reversible)

Applying mutates live `src/` and is the human's call. Walk it through safely:

1. **Scrutinize first** (the quality/scrutiny floor):
   ```bash
   ./scripts/pre_apply_gate.sh aria-<slug>
   ```
   If the Tribunal says `reject`/`hold` or foresight says `reject-for-the-future`, STOP and surface it.

2. **Verify** it's green and staged-only:
   ```bash
   ./scripts/verify_module.sh aria-<slug>
   ```

3. **Confirm the cockpit is stopped** (apply scripts refuse to run otherwise) and that this is what Kevin
   wants — applying is outward-facing and reversible-by-backup, but still his decision.

4. **Run the apply script** (the human runs this; offer the exact command):
   ```bash
   ./aria-<slug>/apply_<pkg>.sh
   ```

5. After apply: run the module's tests + `./scripts/floor_check.sh`, and note the backup location for
   rollback. Reversible by construction — backups live under `aria-<slug>/backups/`.
