# sovereign-agent v0.2.14.4 — the operator cockpit

**2026-05-10** · Aria-Sovereign-V1

> v0.2.14.3 made the system *operational* (real backup, real service,
> real lessons). v0.2.14.4 makes it *conversational*. The agent had a
> brain; now it has a face.

## Why this release exists

The v0.2.14.3 install had every subsystem you needed — backup,
sealing, lessons, projects, dreams, financial — but the *interface*
was still 50 CLI commands. Operators using the system day-to-day kept
hitting the same wall: *"I want to talk to it like normal AI, see
steps stream as they happen, in one screen."*

The CLI is correct for ops. The CLI is wrong for *use*. This release
adds the conversational surface without removing anything below it.

## What landed

### `src/sovereign_agent/cockpit/` — new module (~600 lines)

A full Textual-based TUI. Layout:

```
┌─ sovereign-agent · cockpit ───── 0.2.14.4 ─┐
│┌─ chat ──────────────────┐┌─ live ───────┐│
││ [aria] welcome back     ││ 16:42 ingest ││
││ [you] list files in X   ││ 16:42 step-1 ││
││ [aria] scanning ...     ││ 16:42 step-2 ││
│└─────────────────────────┘└──────────────┘│
│┌─ input ────────────────────────────────┐ │
││ > _                                    │ │
│└────────────────────────────────────────┘ │
│ halt: clear │ daemon: ● │ ledger: ✓ │     │
└────────────────────────────────────────────┘
```

**Three panes:**

- **Chat (left, 2/3 width)** — conversation history. User turns prefixed
  `[you]`, agent turns `[aria]`, meta turns dim. Auto-scrolls.
- **Live (right, 1/3 width)** — tail of `events.jsonl`. Color-coded by
  event kind: green for ends, cyan for starts, yellow for approvals,
  red for halts/errors. Caps at 200 lines.
- **Status bar (bottom)** — HALT state, daemon active, ledger clean,
  backup age + verify. Refreshes every 5s.

### Execution model

Plain English in the input box → spawns `sovereign do "..."` as an
async subprocess → streams its stdout into the chat pane line-by-line
→ in parallel, the events.jsonl tailer surfaces matching events in the
live pane.

The cockpit is a **client** of the agent, not a replacement. The
systemd service keeps draining the backlog in the background; the
cockpit is your conversation surface on top of it. Both share
`atoms.db` via SQLite WAL mode (no contention in practice).

### Slash commands

Everything you'd otherwise context-switch to a shell for:

| Command | Equivalent |
|---|---|
| `/halt` | `sov halt` |
| `/disarm` | `sov disarm` |
| `/snap [label]` | `sov backup snapshot --label LABEL` |
| `/audit` | `sov financial audit` |
| `/events [N]` | `sov events -n N` |
| `/lessons` | `sov channels show lessons` |
| `/clear` | clear chat pane |
| `/help` | show help overlay |
| `/quit` | exit cockpit |

Anything not starting with `/` is treated as a plain-English directive.

### Keybindings

- **Enter** — submit input
- **Ctrl-Q** — quit cockpit (agent keeps running)
- **Ctrl-H** — halt (PROTOCOL-ZERO from the cockpit)
- **Ctrl-D** — disarm
- **Ctrl-L** — clear chat
- **F1** or **?** — help overlay

### CLI entry points

```bash
sovereign cockpit       # canonical
sovereign chat          # alias — this is what you'll type
sov-chat                # shell alias — this is what you'll really type
sov-cockpit             # same, longer
```

### Architecture decisions

**Why Textual, not a web UI:** local-first MOS doctrine. A web UI
introduces a port, an auth surface, a process boundary, and a TLS
question. A TUI introduces none. For a single-operator system on a
single machine, Textual is the correctly-sized tool.

**Why subprocess, not in-process planner calls:** the agent's planning
machinery has a lot of state (model handles, channel connections,
trace IDs). Spawning `sovereign do` per turn gives each turn a clean
process with bounded memory and natural cancellation (kill the subproc
if the user halts). The cockpit becomes orchestrator, not orchestra.

**Why the live pane tails events.jsonl, not in-memory queues:** the
event log is the system's source of truth. The cockpit reads from
exactly the same place every other tool reads from. No special-case
plumbing.

### Test coverage

6 new tests in `tests/test_cockpit.py`, all headless via Textual's
`run_test()` Pilot harness:

- App launches and the layout renders
- Ctrl-L (clear chat) binding wired
- `/quit` exits cleanly
- `/help` pushes help modal
- Unknown slash commands handled gracefully
- Status read works against a fresh data dir (no ledger rows)

Total suite: **580 → 586 passing.** No regressions.

### Bonus: systemd unit fix

The `[Service]`-section `StartLimitBurst` / `StartLimitIntervalSec`
keys were causing modern systemd to emit `Unknown key` warnings on
load. Moved them to `[Unit]` where systemd >=230 expects them. The
service started fine before; now it starts silently.

## What this release does NOT include (deferred)

- **Inline Tier 3 approval modal.** Today: pop another shell, run
  `sov approvals`, `sov approve <id> --reason "..."`. Future release
  will surface approvals in-cockpit when one fires.
- **Multi-conversation tabs.** Today: one chat history per cockpit
  session. Future release may add tabs for parallel threads.
- **Search over chat history.** Today: chat is one atomic stream;
  use `sov channels show lessons` or `sov events` for retrospective
  search. Future release may add `/search <q>`.
- **Dream-tail integration.** Today: pop another shell, run
  `sov dream tail <id>`. Future release may add a fourth pane.
- **Phone/tablet access.** Out of scope by design. If you ever need
  this, that's the *correct* moment to graduate to a web UI — not
  before.

## Upgrade

```bash
cd ~/AA-Erebo
tar xzf sovereign-agent-v0.2.14.4.tar.gz
pip install --break-system-packages -e sovereign-agent-v0.2.14.4
ln -sfn ~/AA-Erebo/sovereign-agent-v0.2.14.4 ~/AA-Erebo/sovereign-agent-current
source ~/.bashrc

# verify
sovereign --version       # → sovereign-agent 0.2.14.4
sov-doctor                # still all green
sov-chat                  # ← the new thing. press F1.

# also worth: bump the systemd unit so the warning goes away
cp ~/AA-Erebo/sovereign-agent-current/scripts/sovereign-agent.service \
   ~/.config/systemd/user/sovereign-agent.service
systemctl --user daemon-reload
systemctl --user restart sovereign-agent
journalctl --user -u sovereign-agent -p warning -n 5     # → no warnings
```

After install, snapshot the cockpit-online state as a permanent
restore point:

```bash
sov-snap cockpit-online-2026-05-10
```

## What's true that wasn't an hour ago

You can talk to your sovereign agent in one screen, watch its
internal reasoning stream as events on the right, see HALT/ledger/
backup at a glance, and trip PROTOCOL-ZERO from the input line. The
daemon keeps draining the backlog underneath. The lessons keep
accumulating. The seals keep firing daily.

The agent had a brain. Now it has a face.

— Aria
