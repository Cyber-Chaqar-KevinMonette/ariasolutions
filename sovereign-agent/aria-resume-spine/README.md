# aria-resume-spine — Fable F7
The engine's resume half was finished and orphaned: run_session is safely
re-entrant (picks up at the next pending subtask) and NOTHING re-entered it —
paused/budget sessions were unreachable corpses (one sat on disk from the first
K4 E2E). Now: `resume_goal_session(sid)` + `/resume [sid]` (work-mode gated,
chat proposes; endings that aren't complete name the exact /resume command) —
scope contracts reload and pause-window messages deliver at the first boundary,
both for free, both by construction.

And Kevin's safe exit — **/rest**: an exit is a bookmark, never an amputation.
Running session → the interrupts pause flag makes Gate 2 stop at the NEXT SAFE
BOUNDARY (never mid-tool-call), the worker's finally writes
`data_dir/resume_point.json` + clears the flag + exits (the unmount flush seals
chunks/events on the way out). Idle → bookmark + exit now. The next wake
surfaces it exactly once: "we rested mid-work — /resume <sid> to continue 💛".
