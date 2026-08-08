---
name: aria-new-module
description: Scaffold a new staged aria-<name>/ module (payload package, shared-helper conftest, test stub, apply script from the canonical template, README stub). Use whenever you start building a new Aria feature/module so you follow the staging doctrine without reinventing boilerplate.
---

# aria-new-module — scaffold a staged module the right way

Given a kebab-case slug (and optional payload package name), scaffold the folder:

```bash
./scripts/new_module.sh <slug> [pkg]
```

This creates `aria-<slug>/` with: payload package `src/sovereign_agent/<pkg>/`, a `tests/conftest.py` that
uses the shared `scripts/lib/aria_conftest.py` helper, a test stub, a README stub, and `apply_<pkg>.sh`
instantiated from `scripts/lib/apply_template.sh`.

Then:
1. Build the real payload in `aria-<slug>/payload/src/sovereign_agent/<pkg>/` — reuse the **reuse map** in
   `.claude/PLAYBOOK.md` (safety_kernel, three_rings, diagnosis, tribunal, foresight, …) before writing new code.
2. Write **real behavior tests** (prove it WORKS, not just imports).
3. If it ships tools, uncomment + fill the tool-registration block in the apply script (anchor on the latest
   `-import-d` / `-all-d` in the chain — see PLAYBOOK).
4. Verify with `/aria-verify aria-<slug>` and scrutinize with `/aria-scrutinize`.

Never mutate live `src/`. The module stays staged until the human runs its apply script.
