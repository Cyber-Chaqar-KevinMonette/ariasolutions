# aria-reaction-roles — react to an emoji, get (or lose) a role

> Part of the income plan's gateway-bot track: the first standing,
> invite-able Discord bot capability, chosen because it needs zero
> privileged Discord intents (`guild_reactions` is already in
> `discord.Intents.default()`) — no verification bottleneck between building
> it and eventually listing the bot publicly. v1 proves it on Kevin's own
> server (BigKevs-Bot-Shop); storage is genuinely per-guild-scoped from day
> one so a later multi-server phase is a distribution problem, not a
> rewrite. Propose-only / reversible / staged.

## Payload
- `src/sovereign_agent/reaction_roles/` — pure logic, no discord.py:
  per-guild bindings store (`<data>/reaction_roles/<guild_id>/bindings.json`,
  atomic write, corrupt/missing → safe defaults, same convention as
  `welcome.py`/`members.py`), `emoji_key()`, `decide_reaction_role_action()`
  (dry-run by default), `build_audit_entry()`.
- Patches `discord_admin/bot.py` (anchor-based, never whole-file): 3 new
  `COMMANDS` catalog entries, 3 new `/reaction-role-*` slash commands
  (team-gated via `_is_staff`), and `on_raw_reaction_add`/
  `on_raw_reaction_remove` gateway handlers beside `on_member_join`.

## Tools / tier
Not a `Tool` — this is gateway-bot infrastructure (like `on_member_join`),
not something Aria's reasoning loop calls. Lives in the standalone
`sov discord-admin run` process, same as the rest of `discord_admin/bot.py`.

## Live gate
`DISCORD_ENABLE_REACTION_ROLE_GRANTS=1` — default unset means dry-run: every
reaction is decided and audit-logged, but `add_roles`/`remove_roles` are
never actually called until this is armed.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-reaction-roles     # before apply
./scripts/pre_apply_gate.sh aria-reaction-roles    # Tribunal + quality gates
./aria-reaction-roles/apply_reaction_roles.sh       # cockpit stopped, Kevin's call
```

## Explicitly deferred (not silently dropped)
No cockpit UI (`bot_studio_screen.py` has no concept of an always-on gateway
bot). No public bot-directory listing, multi-server onboarding, abuse
handling at stranger-scale, or ToS/privacy-policy — all phase 2, once v1 is
proven here. `bot_projects.py`'s `"role-reaction"` `BOT_KINDS` entry stays an
unwired picklist label.
