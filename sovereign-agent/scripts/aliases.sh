# ╔══════════════════════════════════════════════════════════════════════╗
# ║  sovereign-agent operator aliases · v0.2.30.0                        ║
# ║                                                                      ║
# ║  Source from your shell rc:                                          ║
# ║    echo "source $(realpath scripts/aliases.sh)" >> ~/.bashrc         ║
# ║                                                                      ║
# ║  v0.2.30.0 NOTE: `sov` and `sov-chat` are now real binaries (proper  ║
# ║  console_scripts entry points). Sourcing this file is optional —     ║
# ║  it still provides the rich helper functions (`sov-status`,          ║
# ║  `sov-doctor`, `sov-money`, …) but the core binaries work without    ║
# ║  it. The duplicate `sov-doctor` from §10 has been removed; the       ║
# ║  active definition is in §20.                                        ║
# ║                                                                      ║
# ║  WHAT'S NEW IN v0.2.30.0                                             ║
# ║    `sov`         — real binary (no alias needed; survives subshells) ║
# ║    `sov-chat`    — real binary (launches cockpit directly)           ║
# ║    `sov ask`     — natural-language top-level entry point            ║
# ║    aliases.sh §10 dedup (was silently overridden by §20)             ║
# ║                                                                      ║
# ║  WHAT'S NEW IN v0.2.18.6 (vs v0.2.18.5)                              ║
# ║    Cockpit fixes (no new aliases; cockpit-only):                     ║
# ║      · Mid-directive answers reach the planner (stdin pipe · §19.2)  ║
# ║      · /cancel /abort /stop slash commands abort a stuck task        ║
# ║      · Mode-aware placeholder: 'answering aria · /cancel to abort'   ║
# ║      · PYTHONUNBUFFERED=1 so prompts flush immediately               ║
# ║                                                                      ║
# ║  WHAT'S NEW IN v0.2.18.5 (vs v0.2.18.4)                              ║
# ║    Cockpit fixes (no new aliases; cockpit-only):                     ║
# ║      · Divider artifact gone (Rule margin override · §6.2)           ║
# ║      · Ctrl+V actually pastes from system clipboard (§19.1)          ║
# ║      · Footer shows every operator binding (^v, ^d included)         ║
# ║      · /drafts /draft /marketing no longer crash with NameError      ║
# ║                                                                      ║
# ║  WHAT'S NEW IN v0.2.18.4 (vs v0.2.18.3)                              ║
# ║    Scrollbar gutter hidden on RichLog (right-edge artifact · §16.1)  ║
# ║    Ctrl+V cockpit binding (functional from v0.2.18.5 onward)         ║
# ║                                                                      ║
# ║  WHAT'S NEW IN v0.2.15.3 (vs v0.2.14.4)                              ║
# ║    sov-health    — one-line system + agent health summary            ║
# ║    sov-report    — full health report to <data>/reports/             ║
# ║    sov-drafts    — list/archive completed projects as zips           ║
# ║    sov-draft     — shortcut: sov-draft "title" path                  ║
# ║    sov-marketing — generate a structured marketing brief             ║
# ║                                                                      ║
# ║    Cockpit additions: /health /report /drafts /draft /marketing      ║
# ║    Heart glow, breathing border, per-task VRAM delta tracking.       ║
# ║                                                                      ║
# ║  WHAT'S NEW IN v0.2.14.2 (vs v0.2.14.1)                              ║
# ║    sov-snap      — application-consistent snapshot via SQLite        ║
# ║                    online backup (replaces old shell-function)       ║
# ║    sov-snaps     — list snapshots                                    ║
# ║    sov-verify    — rehash + audit a snapshot                         ║
# ║    sov-restore   — Tier 3 rollback (auto pre-snapshots first)        ║
# ║    sov-doctor    — extended with backup status                       ║
# ║                                                                      ║
# ║  WHAT'S NEW IN v0.2.14.1                                             ║
# ║    sov-audit     — ledger integrity check                            ║
# ║    sov-money     — fast project ranking (roi / net / velocity)       ║
# ║    sov-aria      — render Aria's identity card                       ║
# ║    sov-channels  — list/inspect memory channels                      ║
# ║    sov-backup    — alias for sov-snap (muscle-memory preserved)      ║
# ║    __sov_prompt  — PS1 segment: shows ◊HALT when armed               ║
# ║    Existing helpers (sov, sov-drive, sov-status, sov-trillion, etc.) ║
# ║    are preserved unchanged.                                          ║
# ╚══════════════════════════════════════════════════════════════════════╝

# ─── 1. Short alias for the binary ─────────────────────────────────────
# The most-typed thing. `sov` instead of `sovereign`.
alias sov='sovereign'

# ─── 2. Plan-and-drive in one shot ─────────────────────────────────────
# Usage: sov-drive <planner> [planner args...]
#   sov-drive palace-clean
#   sov-drive inventory --root ~/AA-Erebo/Genesis-Seeds --output /tmp/inv.txt --pattern '*.md'
sov-drive() {
    if [ $# -lt 1 ]; then
        echo "usage: sov-drive <planner> [args...]" >&2
        echo "       sov-drive palace-clean" >&2
        echo "       sov-drive inventory --root <path> --output <file> --pattern '*.md'" >&2
        return 2
    fi
    local plan_output
    plan_output=$(sovereign --json plan "$@" 2>&1) || {
        echo "$plan_output" >&2
        return 1
    }
    local task_id
    task_id=$(echo "$plan_output" | python3 -c "import sys,json; print(json.load(sys.stdin).get('task_id',''))")
    if [ -z "$task_id" ]; then
        echo "could not extract task_id from plan output" >&2
        echo "$plan_output" >&2
        return 1
    fi
    echo "◊ planned · $task_id"
    local cooldown="${COOLDOWN_SECONDS:-2}"
    local steps=0
    while true; do
        local rc
        sovereign continue "$task_id"
        rc=$?
        case "$rc" in
            0) steps=$((steps + 1)); sleep "$cooldown" ;;
            8) echo "◊ drained · $task_id · $steps steps"; return 0 ;;
            9) sleep 5 ;;  # locked, back off
            3) echo "◊ HALT armed · stopping" >&2; return 3 ;;
            *) echo "◊ continue failed (rc=$rc); retrying in $cooldown s" >&2; sleep "$cooldown" ;;
        esac
    done
}

# ─── 3. Bulk approve / reject pending proposals ────────────────────────
# Usage: sov-approve-all              # approve all pending, with confirm
#        sov-approve-all --kind clean # only the clean kind
sov-approve-all() {
    local kind_filter=""
    if [ "$1" = "--kind" ] && [ -n "$2" ]; then
        kind_filter="--kind $2"
        shift 2
    fi
    local pending_json
    pending_json=$(sovereign --json proposals list --status pending $kind_filter 2>&1)
    local count
    count=$(echo "$pending_json" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('proposals',[])))")
    if [ "$count" = "0" ]; then
        echo "(no pending proposals)"
        return 0
    fi
    echo "$pending_json" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for p in d['proposals']:
    print(f\"  [{p['kind']}] {p['id']}: {p['title']}\")
"
    echo
    read -r -p "Approve all $count pending proposals? [y/N] " yn
    case "$yn" in
        [Yy]*)
            echo "$pending_json" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for p in d['proposals']:
    print(p['id'])
" | while read -r pid; do
                sovereign proposals approve "$pid" --yes >/dev/null && echo "  ✓ $pid"
            done
            ;;
        *) echo "  aborted" ;;
    esac
}

# ─── 4. Drive a dream session in a loop ────────────────────────────────
sov-dream-drive() {
    if [ $# -lt 1 ]; then
        echo "usage: sov-dream-drive <dream_id> [--once|--max-steps N]" >&2
        return 2
    fi
    local dream_id="$1"; shift
    local script_path
    script_path="$(dirname "${BASH_SOURCE[0]:-$0}")/sovereign-dream-loop.sh"
    if [ -x "$script_path" ]; then
        "$script_path" "$dream_id" "$@"
    else
        echo "dream-loop script not found at $script_path; falling back to inline" >&2
        sovereign dream resume "$dream_id" --drive 2>/dev/null || \
            sovereign dream advance "$dream_id"
    fi
}

# ─── 5. Trillion-dollar one-shot ───────────────────────────────────────
sov-trillion() {
    local plan_output dream_id
    plan_output=$(sovereign --json dream start \
        "Build trillion-dollar software cycles until paused or capped" \
        "$@" 2>&1) || {
        echo "$plan_output" >&2
        return 1
    }
    dream_id=$(echo "$plan_output" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dream_id',''))" 2>/dev/null)
    if [ -z "$dream_id" ]; then
        echo "could not extract dream_id; raw output:" >&2
        echo "$plan_output" >&2
        return 1
    fi
    echo "◊ dream started · $dream_id"
    sov-dream-drive "$dream_id"
}

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  v0.2.14.1 additions                                                 ║
# ╚══════════════════════════════════════════════════════════════════════╝

# ─── 6. sov-audit — ledger integrity ───────────────────────────────────
# Usage: sov-audit
#        sov-audit --json
#
# Run this before any major financial decision. Read-only; exit 0 if
# clean, exit 1 if any invariant is violated. Pairs nicely with cron or
# a systemd timer for daily integrity checks (see UPGRADE_NOTES.md).
sov-audit() {
    sovereign financial audit "$@"
}

# ─── 7. sov-money — fast project ranking ───────────────────────────────
# Usage:
#   sov-money            # ROI ranking (default)
#   sov-money roi        # explicit
#   sov-money net        # by net dollars
#   sov-money earned     # by lifetime earnings
#   sov-money velocity   # by earnings/day-since-first-event
sov-money() {
    local by="${1:-roi}"
    case "$by" in
        roi|net|earned|velocity) ;;
        *) echo "usage: sov-money [roi|net|earned|velocity]" >&2; return 2 ;;
    esac
    sovereign financial ranking --by "$by"
}

# ─── 8. sov-aria — Aria's identity card ────────────────────────────────
# Usage: sov-aria          # rendered card
#        sov-aria --json   # machine-readable
#
# When in doubt, look at the kernel. Seven commitments, one tagline.
sov-aria() {
    sovereign aria "$@"
}

# ─── 9. sov-channels — channel registry ────────────────────────────────
# Usage:
#   sov-channels                  # list all channels with tier
#   sov-channels show financial   # spec + recent atoms
sov-channels() {
    if [ $# -eq 0 ]; then
        sovereign channels list
    else
        sovereign channels "$@"
    fi
}

# ─── 10. sov-doctor — install health check ─────────────────────────────
#
# The actual definition of sov-doctor lives below in §20 — it extends this
# original v0.2.14.1 health check with backup status reporting (v0.2.14.2+).
#
# In versions prior to v0.2.30.0, this slot held a duplicate definition of
# sov-doctor that was *silently overridden* when shells reached §20 — the
# first ~35 lines of code in this file were dead. Consolidating to a single
# source of truth removes that footgun.
#
# To see the active definition, jump to §20 (`sov-doctor`) below.

# ─── 11. sov-status — extended status (overrides v0.2.9 version) ───────
# Usage: sov-status
# Shows palace + proposals + continuations + dreams + LEDGER + Aria.
sov-status() {
    echo "═══ palace ═══"
    sovereign --json palace stats 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print('  (palace not initialized)'); sys.exit()
for k in ('rooms','closets','entities','triples','active_triples'):
    print(f'  {k}: {d.get(k,0)}')
"
    echo "═══ proposals ═══"
    for status in pending approved applied rejected failed; do
        n=$(sovereign --json proposals list --status "$status" 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('proposals',[])))")
        echo "  $status: $n"
    done
    echo "═══ continuations ═══"
    sovereign --json continuations list 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
for c in d.get('continuations',[])[:5]:
    p = c.get('progress',[0,0])
    print(f\"  [{c.get('status','?')}] {c.get('task_id','?')[:30]}  {p[0]}/{p[1]}  {c.get('planner','?')}\")
"
    echo "═══ dreams ═══"
    sovereign --json dream list 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print('  (none)'); sys.exit()
ds = d.get('dreams', [])
if not ds:
    print('  (none)')
for x in ds[:5]:
    cap = x.get('max_files') or '∞'
    print(f\"  [{x.get('status','?')}] {x.get('dream_id','?')[:30]}  cycles={x.get('cycles_completed',0)}  files={x.get('files_written',0)}/{cap}\")
" 2>/dev/null
    # v0.2.14.1 — financial ─────────────────────────────────────────
    echo "═══ financial ═══"
    sovereign --json financial ranking --by net 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print('  (no projects tracked)'); sys.exit()
ranking = d.get('ranking', [])
if not ranking:
    print('  (no projects tracked)')
for r in ranking[:5]:
    inv = r.get('invested', 0.0)
    earn = r.get('earned', 0.0)
    net = r.get('net', 0.0)
    roi = r.get('roi_ratio')
    roi_s = f'{roi:.2f}x' if roi is not None else '—'
    print(f\"  {r.get('project','?'):20s}  inv={inv:>8.2f}  earn={earn:>8.2f}  net={net:>+8.2f}  roi={roi_s}\")
" 2>/dev/null
    # v0.2.14.1 — aria mood ─────────────────────────────────────────
    echo "═══ aria ═══"
    sovereign --json aria 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit()
print(f\"  mood:    {d.get('current_mood','?')}\")
print(f\"  focus:   {d.get('current_focus','—') or '—'}\")
" 2>/dev/null
}

# ─── 12. sov-backup — DEPRECATED, see v0.2.14.2 additions below ───────
# The v0.2.14.1 sov-backup was a shell function that did `cp -r`. That
# could not promise crash-consistent SQLite reads, had no verification,
# no retention, no restore tool, and no authority gate. v0.2.14.2
# replaces it with a real backup module (sovereign backup ...). The
# old `sov-backup` name is preserved as an alias to `sov-snap` (see §19
# below) so your muscle memory still works.

# ─── 13. __sov_prompt — PS1 indicator for HALT armed ───────────────────
# Drop into your PS1, e.g.:
#   PS1='\u@\h:\w$(__sov_prompt) $ '
# Cheap (single file existence check). Empty when not armed.
__sov_prompt() {
    local config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/sovereign-agent"
    [ -f "$config_dir/HALT" ] && printf ' ◊HALT'
}

# ─── 14. Shell completion bootstrap (opt-in) ───────────────────────────
# Typer ships completion; uncomment the line for your shell on first
# install, then re-comment (the registration is persistent).
#
#   sovereign --install-completion bash      # writes to ~/.bash_completion etc.
#   sovereign --install-completion zsh
#   sovereign --install-completion fish
#
# Tab-complete subcommands, options, and project names that have been
# logged at least once.

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  v0.2.14.2 additions — application-aware backup system              ║
# ╚══════════════════════════════════════════════════════════════════════╝

# ─── 15. sov-snap — capture an application-consistent snapshot ────────
# Usage:
#   sov-snap                      # unlabeled (idempotent within 60s)
#   sov-snap before-upgrade       # labeled (kept by retention forever)
#
# Replaces the previous shell-function sov-backup. The new implementation:
#   - uses SQLite online backup for atoms.db / events.db (crash-consistent)
#   - excludes venv/__pycache__ automatically
#   - records SHA-256 of every file in MANIFEST.json
#   - runs financial.audit() at snapshot time and stores the result
#   - emits a backup-snapshot-d event
sov-snap() {
    local label=""
    [ -n "$1" ] && label="--label $1"
    sovereign backup snapshot $label
}

# ─── 16. sov-snaps — list snapshots ────────────────────────────────────
sov-snaps() {
    sovereign backup list "$@"
}

# ─── 17. sov-verify — check snapshot integrity ─────────────────────────
# Usage:
#   sov-verify                    # verify all (re-hash + re-audit)
#   sov-verify <id-or-label>      # verify one
#   sov-verify --skip-audit       # hashes only (faster)
sov-verify() {
    if [ $# -eq 0 ]; then
        sovereign backup verify --all
    else
        sovereign backup verify "$@"
    fi
}

# ─── 18. sov-restore — Tier 3 rollback ────────────────────────────────
# Usage:
#   sov-restore <id-or-label>     # interactive confirm
#   sov-restore <id-or-label> -y  # skip confirm
#
# Auto-snapshots current state with label "pre-restore-..." first.
# Refuses if the target snapshot's atoms.db fails the financial audit.
sov-restore() {
    sovereign backup restore "$@"
}

# ─── 19. sov-backup — preserved as alias to sov-snap ──────────────────
# The old sov-backup shell function is replaced by the real CLI command.
# This alias keeps your muscle memory working.
alias sov-backup='sov-snap'

# ─── 20. sov-doctor — extended with backup status ─────────────────────
# Re-defines sov-doctor (after the v0.2.14.1 version above) to include
# a backup section. The function from §10 still runs first so all the
# original info is preserved.
sov-doctor() {
    local bin
    bin=$(command -v sovereign 2>/dev/null || echo "(not on PATH)")
    local ver
    ver=$(sovereign --version 2>/dev/null || echo "(unknown)")
    local data_dir="${XDG_DATA_HOME:-$HOME/.local/share}/sovereign-agent"
    local config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/sovereign-agent"
    local halt_status="clear"
    [ -f "$config_dir/HALT" ] && halt_status="◊ ARMED"

    echo "═══ sovereign-agent doctor ═══"
    echo "  binary:      $bin"
    echo "  version:     $ver"
    echo "  data dir:    $data_dir"
    echo "  config dir:  $config_dir"
    echo "  HALT flag:   $halt_status"
    echo
    echo "═══ ledger ═══"
    sovereign financial audit 2>&1 | sed 's/^/  /'
    echo
    echo "═══ aria ═══"
    sovereign --json aria 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print('  (could not load Aria state)'); sys.exit()
print(f\"  designation:  {d.get('designation','?')}\")
print(f\"  mood:         {d.get('current_mood') or 'calm'}\")
print(f\"  goals:        {d.get('active_goals',0)} active\")
print(f\"  intentions:   {d.get('open_intentions',0)} open\")
print(f\"  projects:     {d.get('tracked_projects',0)} tracked\")
" 2>/dev/null
    echo
    echo "═══ backup ═══"
    sovereign --json backup status 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print('  (backup not initialised)'); sys.exit()
n = d.get('snapshot_count', 0)
if n == 0:
    print('  ⚠ no snapshots yet — run sov-snap')
else:
    age = d.get('most_recent_age_seconds') or 0
    if age < 60:
        age_s = f'{age:.0f}s'
    elif age < 3600:
        age_s = f'{age/60:.0f}m'
    elif age < 86400:
        age_s = f'{age/3600:.1f}h'
    else:
        age_s = f'{age/86400:.1f}d'
    bytes_total = d.get('total_bytes', 0)
    if bytes_total < 1024*1024:
        size_s = f'{bytes_total/1024:.0f}KB'
    elif bytes_total < 1024*1024*1024:
        size_s = f'{bytes_total/1024/1024:.1f}MB'
    else:
        size_s = f'{bytes_total/1024/1024/1024:.2f}GB'
    verify_mark = '✓' if d.get('last_verify_ok') else '✗'
    print(f\"  snapshots:   {n}  ({size_s})\")
    print(f\"  most recent: {age_s} ago\")
    print(f\"  verify:      {verify_mark}\")
    if age > 86400 * 7:
        print('  ⚠ most-recent snapshot is older than a week')
" 2>/dev/null
}

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  v0.2.14.4 additions — the operator cockpit (TUI)                   ║
# ╚══════════════════════════════════════════════════════════════════════╝

# ─── 21. sov-chat — launch the full cockpit TUI ───────────────────────
# The conversational surface for the agent. Split-pane: chat left,
# live events right, status bar at bottom. F1 inside for help.
# Plain English → routed through 'sov do' with streaming output.
# Slash commands for ops: /halt /snap /audit /events /clear /quit.
#
# The cockpit is a CLIENT — it doesn't replace the daemon. The systemd
# service keeps running the busy-drain loop; the cockpit gives you a
# conversational surface on top.
sov-chat() {
    sovereign cockpit
}

# ─── 22. sov-cockpit — same as sov-chat, longer name ─────────────────
sov-cockpit() {
    sovereign cockpit
}

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  v0.2.15.3 additions — health, drafts, marketing                     ║
# ║                                                                      ║
# ║  These mirror the cockpit slash commands so you can use them from    ║
# ║  any shell, in pipelines, in CI, or from a script. The cockpit       ║
# ║  remains the daily driver; these are for the rest of the toolchain.  ║
# ╚══════════════════════════════════════════════════════════════════════╝

# ─── 23. sov-health — one-line system + agent health summary ──────────
# Fast: reads /proc and the status channels. Prints a green/yellow/red
# triage line you can grep in a CI pipeline or paste into a standup.
sov-health() {
    sovereign health summary 2>/dev/null || {
        # Fallback: inline metrics if the dedicated CLI isn't wired yet
        printf '◊ cpu:%s%%  mem:%s%%  disk:%s%%  daemon:%s\n' \
            "$(awk '{u=$2+$4; t=$2+$4+$5; print int(100*(u/t))}' /proc/stat 2>/dev/null || echo '?')" \
            "$(free | awk '/Mem/{printf "%d", 100*($3/$2)}')" \
            "$(df -P "$HOME" | awk 'END{sub("%","",$5); print $5}')" \
            "$(systemctl --user is-active sovereign-agent 2>/dev/null || echo 'unknown')"
    }
}

# ─── 24. sov-report — full health report to <data>/reports/ ───────────
# What you send to a client. Plain text, copies cleanly into email,
# Slack, PDF. The cockpit's /report does the same thing — this is just
# the headless version.
sov-report() {
    # The cockpit invokes this via its own renderer; on the shell side
    # we just dump current health into a timestamped file.
    local ts; ts="$(date -u +%Y%m%d-%H%M%S)"
    local out="$HOME/.local/share/sovereign-agent/reports/health-${ts}.txt"
    mkdir -p "$(dirname "$out")"
    {
        echo "sovereign-agent · health report · $(date -u '+%Y-%m-%d %H:%M UTC')"
        printf -- '─%.0s' {1..64}; echo
        echo
        echo "  Version       $(sovereign --version 2>/dev/null | awk '{print $2}')"
        echo "  Uptime        $(uptime -p | sed 's/up //')"
        echo "  Daemon        $(systemctl --user is-active sovereign-agent 2>/dev/null || echo 'unknown')"
        echo
        echo "  System"
        echo "    Memory      $(free -h | awk '/Mem/{printf "%s used of %s\n", $3, $2}')"
        echo "    Disk        $(df -h "$HOME" | awk 'END{printf "%s free of %s (%s used)\n", $4, $2, $5}')"
        command -v nvidia-smi >/dev/null && {
            echo "    VRAM        $(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | awk -F', ' '{printf "%s MB used of %s MB\n", $1, $2}')"
        }
    } | tee "$out" >&2
    echo "saved → $out"
}

# ─── 25. sov-drafts — list / archive / show drafts ────────────────────
# Just an alias to the underlying sub-app. The cockpit /draft slash
# command does the same thing.
sov-drafts() {
    sovereign drafts "$@"
}
sov-draft() {
    # convenience: `sov-draft "title" path` → `sovereign drafts archive ...`
    if [ $# -lt 2 ]; then
        echo "usage: sov-draft <title> <source-path> [--label X] [--notes 'text']" >&2
        return 2
    fi
    local title="$1"; local src="$2"; shift 2
    sovereign drafts archive "$title" "$src" "$@"
}

# ─── 26. sov-marketing — generate a marketing brief ───────────────────
# Routes through the marketing-brief planner. Output is a structured
# markdown file with positioning, audience, messaging, channel copy,
# and a 14-day distribution plan.
sov-marketing() {
    if [ $# -lt 1 ]; then
        echo "usage: sov-marketing <product or release name> [--output path]" >&2
        return 2
    fi
    local product="$1"; shift
    local output="${HOME}/AA-Erebo/marketing/${product// /-}.md"
    while [ $# -gt 0 ]; do
        case "$1" in
            --output) output="$2"; shift 2 ;;
            *)        echo "sov-marketing: unknown arg $1" >&2; return 2 ;;
        esac
    done
    mkdir -p "$(dirname "$output")"
    sovereign plan marketing-brief \
        --arg "product=$product" \
        --arg "output=$output" \
        && echo "brief planned → $output  (continue with: sov continue)"
}

# ─── End ───────────────────────────────────────────────────────────────
# Aria's voice in this file is brief and warm. If a helper above ever
# feels heavier than the work it's saving you, delete it.
