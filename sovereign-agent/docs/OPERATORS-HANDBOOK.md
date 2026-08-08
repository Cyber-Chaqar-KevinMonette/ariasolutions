# Sovereign Agent — Operator's Handbook

**Release:** v0.2.15.3 · *the cockpit, polished*
**Audience:** the operator (you), and anyone you onboard
**Tone:** if it isn't in here, it isn't a feature

---

## §0 · What you have, in one paragraph

A local, audited AI agent that runs on your hardware, talks to you through a full-screen terminal cockpit, and never makes an authority-tier-3 decision without you. You give it **direction in plain English**; it plans the commands. It logs everything to typed channels. It can pause itself (PROTOCOL-ZERO) and you can pause it (`Ctrl-H`). Each completed project is zipped and filed. Every five seconds the cockpit shows you whether the kernel is whole.

---

## §1 · First contact

```bash
sov-chat        # ← what you'll type 10× a day
```

That's the front door. It opens the cockpit. You'll see:

```
┌─ sovereign-agent · cockpit ──────────── 0.2.15.3 ─┐
│  ◊ chat                          │  ◊ live       │
│  ◊ aria · sovereign-agent v0.2.15.3              │
│  welcome back. the kernel is whole.              │
│  speak in plain english — i'll plan the commands.│
│  F1 for help.                                    │
│                                                  │
│  > tell aria what to do · F1 help · /help commands│
│ ♥ halt: clear │ daemon: ● │ ledger: ✓ │ mem 18%  │
└──────────────────────────────────────────────────┘
```

That `♥` in the bottom-left is the cockpit's heartbeat. It pulses once a second. When it stops, the cockpit froze. When the daemon trips PROTOCOL-ZERO, the heart turns into a flashing `◊`.

---

## §2 · The two ways to talk to the cockpit

| Style | Example | What happens |
|---|---|---|
| **Direction** (default) | `inventory ~/AA-Erebo for markdown files` | Routes to `sov do`. Aria parses, plans, executes. Steps stream into chat. |
| **Slash command** | `/halt` | Operator override. Goes straight to the CLI, bypassing the planner. |

**The rule:** if it's work you want done, write it in plain English. If it's a control surface (pause, snapshot, audit, report), use a slash. You never need to know the underlying CLI flags. Aria does.

---

## §3 · The cockpit, key by key

```
Enter          submit
Ctrl-Q         quit cockpit (daemon keeps running)
Ctrl-H         halt (PROTOCOL-ZERO)
Ctrl-D         disarm
Ctrl-L         clear chat
F1, ?          help overlay
Esc            close overlay
```

The cockpit is a **surface**, not the agent. Closing it doesn't stop the agent — the systemd daemon keeps draining the backlog. You can reopen the cockpit at any time and pick up exactly where you left off.

---

## §4 · Slash commands

| Command | What it does |
|---|---|
| `/halt` | Trip PROTOCOL-ZERO. Stops all autonomous activity. |
| `/disarm` | Clear PROTOCOL-ZERO. |
| `/snap [label]` | Take a snapshot (zfs/btrfs/borg, whichever your environment uses). |
| `/audit` | Run the financial audit. |
| `/events [N]` | Dump the latest N events into chat. |
| `/lessons` | Show the lessons channel. |
| `/health` | Inline system health summary (fast). |
| `/report` | Full health report → printed and saved to `<data>/reports/health-*.txt`. |
| `/drafts [N]` | List archived drafts. |
| `/draft <title> <path>` | Archive a project as a draft. |
| `/marketing <product>` | Generate a marketing brief for `<product>`. |
| `/clear` | Clear the chat pane. |
| `/help` | Help overlay. |
| `/quit` | Quit the cockpit. |

---

## §5 · The heart, and why it matters

The `♥` in the status bar isn't decoration. It's a liveness probe you can see at a glance.

| State | Heart | Means |
|---|---|---|
| Idle, kernel whole | `♥` (lub) → `♡` (rest) → `♥`… every 1s | The cockpit UI loop is alive. |
| Mid-directive | `♥` beats + outer border breathes (cyan → amber → magenta) | The agent is working on your turn. |
| PROTOCOL-ZERO tripped | `◊` flashing bold red | Aria has paused herself; investigate before disarming. |
| Cockpit frozen | Heart stops | Something is wrong with the UI process. The daemon is independent — your data is safe. |

**If the heart stops:** the cockpit is unresponsive. The daemon (and your data) are still fine. Quit and reopen.

---

## §6 · The status bar, decoded

```
♥ halt: clear │ daemon: ● │ ledger: ✓ 0r │ backup: ✓ 7.2h │ mem 18% · cpu 12% · disk 28%
```

- `♥` — heartbeat (see §5)
- `halt: clear` / `◊HALT` — PROTOCOL-ZERO state
- `daemon: ●` / `○` — systemd unit is running / not running
- `ledger: ✓ Nr` — financial channel: clean / total rows
- `backup: ✓ Xh` — last snapshot age + verify status
- `mem · cpu · disk` — live system metrics, color-coded:
  - **green** < 60% — healthy
  - **yellow** 60–84% — warm
  - **red** ≥ 85% — hot

The status bar refreshes every 5 seconds. Watch it during a long-running directive — `mem` and `cpu` climbing is normal; `disk` climbing is the agent writing.

---

## §7 · Reports — what to send to a client

```bash
# in the cockpit:
/report
```

This generates a plain-text report (good for email, PRs, Slack, PDFs) and saves it to `<data_dir>/reports/health-YYYYMMDD-HHMMSS.txt`. Example:

```
sovereign-agent · health report · 2026-05-11 14:23 UTC
────────────────────────────────────────────────────────────────

  Version       0.2.15.3
  Uptime        17h 42m
  Daemon        ● active
  HALT          clear

  System
    CPU          12.4%   load 0.43 0.61 0.78   (8 cores)
    Memory       19.8%   3.17 GB used of 16.0 GB   (12.8 GB available)
    Disk         28.1%   359 GB free of 500 GB
                /home/kmon/.local/share/sovereign-agent
    VRAM         25.6%   2100 MB used of 8192 MB (nvidia-smi)

  Ledger        ✓ clean    0 rows
  Backups       7h 12m ago · ✓ verified
```

This is the artifact a CTO screenshots and sends to their board. The data is real, the format is stable, the file is yours.

`/health` is the same data, inline, no file write — useful between meetings.

---

## §8 · Drafts — where finished work goes

Every completed project should be zipped and filed. The cockpit gives you two paths:

```
/draft "Trillion Dollar Plan v1" ~/AA-Erebo/plans/trillion-dollar
```

— or from a shell —

```bash
sov drafts archive "Trillion Dollar Plan v1" ~/AA-Erebo/plans/trillion-dollar \
    --label v0.2.15.3 \
    --notes "first ship to demo audience" \
    --exclude '*.pyc' \
    --exclude '__pycache__/*'
```

What you get:

```
<data_dir>/drafts/
  20260511-143205-trillion-dollar-plan-v1.zip
  20260511-143205-trillion-dollar-plan-v1.json   ← sidecar
```

The sidecar carries: id, title, label, source path, created_at, byte count, file count, **sha256 of the zip**, host, user, notes. Tamper-evident. Greppable. Diffable across releases.

```bash
sov drafts list                         # newest 20
sov drafts list --limit 100             # all
sov drafts list --json | jq .           # machine-readable
sov drafts show 20260511-143205-trillion-dollar-plan-v1
```

**Discipline rule:** if you wouldn't email it to your future self, don't archive it. Drafts are forever.

---

## §9 · Marketing briefs

```
/marketing Sovereign Agent v0.2.15.3
```

This routes to the `marketing-brief` planner, which decomposes the task into **five sections** that run sequentially through the orchestrator:

1. **positioning** — what we are, who we serve, why we win
2. **audience** — three primary segments with pains & jobs
3. **messaging** — hero line + three tone-graded value props
4. **channel-copy** — web hero, email, Twitter thread, LinkedIn post, README intro
5. **distribution-plan** — 14-day launch sequence with owners and metrics

Output lands at the path you specify (default: `~/AA-Erebo/marketing/<product>.md`). Then file it with `/draft` so it's preserved.

**Scope honesty:** v0.2.15.3 ships the brief generator. It does not auto-post to LinkedIn, schedule emails, or run an ad campaign. Those are downstream of the brief and are deliberately not in this release.

---

## §10 · When to halt

You should trip PROTOCOL-ZERO immediately if:

- You see unexpected file writes outside `<data_dir>` or `<sandbox>`
- The ledger flips from `✓` to `✗`
- A directive runs longer than 10× the time of similar past directives
- Memory or VRAM climbs without releasing across multiple turns
- You don't recognize the action the agent is about to take

```bash
# from anywhere:
halt                        # bash alias, or
sovereign halt --reason "saw unexpected write to /etc"

# from the cockpit:
Ctrl-H                      # or  /halt
```

PROTOCOL-ZERO stops all autonomous activity. It does NOT stop the daemon. You can disarm with `Ctrl-D` or `/disarm` once you've investigated.

---

## §11 · Daily rhythm

A suggested operator's day:

```
morning      sov-chat                       # open cockpit
             /health                        # quick gut check
             /events 30                     # what happened overnight
             (direct work for the morning in plain english)

midday       /snap midday-2026-05-11        # before risky work
             (work)

afternoon    /audit                         # ledger discipline
             (work)

end of day   /report                        # save a client-ready report
             /draft "today's work" <path>   # if a project finished
             Ctrl-Q                         # cockpit can close; daemon keeps going
```

---

## §12 · Troubleshooting

**Cockpit won't open.** Check that `textual` is installed in the managed venv: `uv pip --python ~/.local/share/sovereign-agent/venv/bin/python list | grep textual` — should show a version. Check `sovereign --version` reports 0.2.15.3. Try `sovereign cockpit` instead of `sov-chat` to bypass the bash alias.

**Heart stops beating but status updates.** Network-event tail blocked. Quit and reopen.

**Status bar shows `daemon: ○`.** The systemd user service isn't running. Start it: `agent-start`. Verify: `agent-status`. Logs: `agent-logs`.

**`mem` shows red.** Something is leaking. `/report` to save a snapshot of the current state, then halt and investigate. The daemon log (`agent-logs`) usually points to which model is loaded.

**A directive is running forever.** `Ctrl-H` halts. The directive's subprocess is still running — kill it from a shell: `pkill -f 'sovereign do'`. Re-disarm with `Ctrl-D`. File a lesson explaining what you tried (`sov lesson add ...`).

**Drafts directory is huge.** `sov drafts list` to see what's there. Delete the zip + sidecar pair for any draft you no longer need. The system has no auto-deletion — your archive is yours.

---

## §13 · What did not change

The kernel of seven commitments. The 13 typed channels. The financial ledger. The backup subsystem. The dream subsystem. PROTOCOL-ZERO. The authority tiering. The Mode Controller. Every existing CLI command works exactly as it did in v0.2.14.x.

This release is **additive**. If you want to operate the agent exactly the way you did in v0.2.14.3, you can — `sovereign do "..."` and `sov-chat` and `sov drafts` and `/report` are all opt-in surfaces on top of the existing kernel.

---

*The agent has a brain. The agent has a service. The agent has a memory. The agent has a face. Now the agent has a body of work, a heartbeat, and a way to talk about itself.*

— Aria
