# aria-game-bridge

Kevin (2026-08-03): a new game concept — a small game where the core mechanic
is Aria and a human player building something together, in real time, inside
the world. Screenshot+ydotool (used for Ember Keep's playtest the same night)
was proven too slow and fragile for that: multi-second round trips, coordinate
calibration issues, window-focus issues. "It can assist just not for fast
paced workflows. That is why we have to engineer a system optimized for her."

This delivers the fast path instead: a direct TCP/NDJSON channel between a
running Godot game (a `game_bridge.gd` autoload) and Aria's agent loop.
Screenshots stay available as a secondary, async channel for aesthetic
judgment — never the thing the real-time loop waits on.

- `game_bridge_client.py` — asyncio TCP/NDJSON client, one persistent
  connection per project slug, req_id-matched replies, an event queue for
  unsolicited pushes (e.g. a human's live placement).
- `game_bridge_connect` (Tier 1) — open the connection to a running game.
- `game_place_piece` (Tier 1) — place a piece at a grid cell, live.
- `game_world_state` (Tier 1) — read current placement state + pending events.

All Tier 1, deliberately: `Mode.BUSY` (the default `/work` session mode) caps
the visible toolset at tier 1 — anything higher would be invisible mid-session,
and a per-placement approval gate would defeat the point of "real-time."

## Apply

```bash
./apply_game_bridge.sh
.venv/bin/python -m pytest tests/test_game_bridge.py -v
```
