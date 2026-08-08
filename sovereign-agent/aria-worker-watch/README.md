# aria-worker-watch — Fable F5
Dead cockpit loops (heart/breathe/status/events) were silent: per-pass try/except
self-heal, but a terminal exit froze the pane forever. Now `on_worker_state_changed`
(the Textual hook app.py never used) gives each persistent group a bounded respawn
(max 2/session) and past that a permanent red `⛔ <group>` status-bar latch + chat
alert. SUCCESS counts as death too — these loops are `while True`; finishing IS
failure. Supervision, never a crash loop. Closes GOD_TIER_CRITERIA §3's named gap.
