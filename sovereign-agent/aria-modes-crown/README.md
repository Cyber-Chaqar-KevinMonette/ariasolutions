# aria-modes-crown — the mode picker, her inner stances, the observatory
(FABLE II · M6)

> *"a popup menu for all the modes… a bunch of new and invaluable modes.
> Also the Auto mode. 1 hour. Maybe a 3 hour auto mode for the highest
> workflows."* Plus, mid-round: her own safe inner stances while in auto,
> watched through an observability window — modes, emotion, stress,
> thinking, a cool-down. Propose-first / reversible / staged.

## Seven declarative mode profiles (F2 / `/modes`)
`chat` (default) · `work` · `auto-1h` (1h lease) · `auto-3h` (3h lease,
**typed confirmation required**: "I approve 3 hours of autonomy") ·
`focus` (garden required) · `companion` (presence, no work) · `guardian`
(read-only, tier ceiling 0). Each is `{base mode, tier ceiling, lease
seconds, wondering, work allowed, garden required, description}` —
composed from what already existed: `cockpit_modes` (the base pair),
`work_interval` + `auto_crown` (leases), and M5's `session_bridge`
lease wire (`record_action`, observable, never self-extends).

## Her inner stances (Tier 0, never touch authority)
`planning · thinking · auditing · scoping · horizon · verifying ·
cool-down`. `set_stance` is a T0 tool — a posture, not a mode. Only
`cool-down` has a tooth: it pauses NEW goal dispatches (the running one
finishes untouched); stepping out is as free as stepping in.

## The observatory (F3 / `/observatory`)
One watching window: mode + lease countdown, stance + trail, her emotion
surface (`emotion.derive_emotions`, already hers), and a mechanical
load/stress read (queue depth, blocked ratio, lease pressure, corrupt-line
reads) — honestly labeled as proxies, never as feelings. Watching, never
steering.

## The gate, enforced (not just UI)
`session_bridge._crown_gate`: non-`work_allowed` modes refuse new
sessions; `focus` requires a declared garden; `cool-down` refuses new
dispatches. PROTOCOL-ZERO / `/halt` / `/rest` are untouched — no profile
ever references them.

## A real bug this round's own suite caught
`request_tools`' grant response could be served from the T0 response
cache on a repeated call within the TTL — silently SKIPPING the mid-loop
attach it exists to perform (cache and session state disagreeing: the
one-truth failure class, in miniature). Tools that cause loop/session
side effects now opt out via `cacheable = False` (`request_tools`,
`set_stance`, `observatory`); `loop.py`'s cache get/put both honor it.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-modes-crown
./scripts/safe_apply.sh aria-modes-crown
```
