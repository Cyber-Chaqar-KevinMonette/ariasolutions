---
name: aria-status
description: Fast session-start orientation for the Aria repo — staged vs applied modules, tests, tools, safety-kernel status, git cleanliness, and the god-tier floor. Use at the start of a session or any time you need to re-orient quickly instead of re-grepping the codebase.
---

# aria-status — orient fast, don't re-derive

Run the orientation + floor scripts and summarize for the user:

```bash
./scripts/aria_session_status.sh
./scripts/floor_check.sh
```

Then, if helpful, point the user/yourself at:
- `CLAUDE.md` — the binding rules (auto-loaded)
- `.claude/PLAYBOOK.md` — the operational how-to (patterns, reuse map, sealed set)
- `GOD_TIER_STANDARD.md` — the floor we hold

Report the safety-kernel status, staged/applied counts, and any floor attention items plainly. If the floor
is VIOLATED, stop and surface it before doing other work.
