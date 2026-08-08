#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_router_expand.sh — Expand router allowlist to unlock 30+ sov commands
#
#  The interpreter currently can only propose ~10 sov commands. This patches
#  router.py to add 30+ safe commands and patches interpreter.py to list
#  the newly available commands so the model knows they exist.
#
#  NEW Tier 0 commands:
#    honor show, honor count
#    atoms show, atoms search, atoms list
#    channels show, channels list
#    behavior show
#    gap list
#    continuations list
#    lessons list, lessons show
#    proposals list
#    people show, people search, people list
#    cadence show
#    commitments list
#    telemetry summary, telemetry tail
#    backlog list
#    sessions list
#    interpret show
#    health, stewards, aria, info
#    financial status (read-only), impact show
#    reasoning list, behavior patterns
#
#  NEW Tier 1 commands:
#    honor note
#    gap add
#    backlog add
#    commitments add
#    proposals add
#
#  Idempotent. Backs up patched files.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$PWD}"

if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }
    d="$(dirname "$d")"
  done
fi
[[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || { echo "✗ run from repo root"; exit 1; }
echo "◊ repo root: $ROOT"

PKG="$ROOT/src/sovereign_agent"
ROUTER="$PKG/router.py"
INTERP="$PKG/interpreter.py"
ts(){ date +%Y%m%d%H%M%S; }

# ── 1. Patch router.py — expand both allowlists ────────────────────────────
echo "→ patching router.py"
cp "$ROUTER" "$ROUTER.bak.$(ts)"

python3 - "$ROUTER" <<'PYEOF'
import sys, pathlib
router = pathlib.Path(sys.argv[1])
src = router.read_text(encoding="utf-8")

T0_MARKER = "# router-expand-t0-d"
T1_MARKER = "# router-expand-t1-d"

if T0_MARKER in src:
    print("  ↷ Tier 0 expansion already applied — skipping")
else:
    OLD_T0 = (
        'TIER_0_SOV_SUBCOMMANDS: frozenset[str] = frozenset({\n'
        '    "status", "version", "doctor",\n'
        '    "events", "drafts",        # the read forms (list/show/get); routed below\n'
        '    "projects",                # subcommand args inspected; only list is t0\n'
        '    "channels",\n'
        '    "people",                  # the read forms\n'
        '    "palace",\n'
        '    "config",\n'
        '    "modes",\n'
        '})'
    )
    NEW_T0 = (
        'TIER_0_SOV_SUBCOMMANDS: frozenset[str] = frozenset({\n'
        '    # original commands\n'
        '    "status", "version", "doctor",\n'
        '    "events", "drafts",        # the read forms (list/show/get); routed below\n'
        '    "projects",                # subcommand args inspected; only list is t0\n'
        '    "channels",\n'
        '    "people",                  # the read forms\n'
        '    "palace",\n'
        '    "config",\n'
        '    "modes",\n'
        '    # router-expand additions — read-only commands\n'
        '    "honor",        # read: sov honor show, sov honor count\n'
        '    "atoms",        # read: sov atoms show, sov atoms search, sov atoms list\n'
        '    "behavior",     # read: sov behavior show, sov behavior patterns\n'
        '    "gap",          # read: sov gap list\n'
        '    "continuations",# read: sov continuations list\n'
        '    "lessons",      # read: sov lessons list, sov lessons show\n'
        '    "proposals",    # read: sov proposals list\n'
        '    "cadence",      # read: sov cadence show\n'
        '    "commitments",  # read: sov commitments list\n'
        '    "telemetry",    # read: sov telemetry summary, sov telemetry tail\n'
        '    "backlog",      # read: sov backlog list, sov backlog show\n'
        '    "sessions",     # read: sov sessions list\n'
        '    "interpret",    # read: sov interpret show\n'
        '    "health",       # read: sov health check\n'
        '    "stewards",     # read: sov stewards list, sov stewards scan\n'
        '    "aria",         # read: sov aria (kernel snapshot)\n'
        '    "info",         # read: sov info\n'
        '    "financial",    # read: sov financial status\n'
        '    "impact",       # read: sov impact show\n'
        '    "reasoning",    # read: sov reasoning list\n'
        '    "reward",       # read: sov reward show\n'
        '    "episode",      # read: sov episode list\n'
        '    "seal",         # read: sov seal (compute — non-mutating)\n'
        '    "verify",       # read: sov verify (non-mutating)\n'
        '    "insights",     # read: sov insights show\n'
        '    "recall",       # read: sov recall list\n'
        '    "personas",     # read: sov personas list\n'
        '    "constitution", # read: sov constitution show\n'
        '    "appendix",     # read: sov appendix list\n'
        '    "capabilities", # read: sov capabilities list\n'
        '    "edge-cases",   # read: sov edge-cases list\n'
        '    "corrections",  # read: sov corrections list\n'
        '    "field-notes",  # read: sov field-notes list\n'
        '})  # ' + T0_MARKER
    )
    if OLD_T0 in src:
        src = src.replace(OLD_T0, NEW_T0, 1)
        print("  ✓ Tier 0 allowlist expanded")
    else:
        print("  ⚠ Tier 0 anchor not matched — skipping T0 expansion")

if T1_MARKER in src:
    print("  ↷ Tier 1 expansion already applied — skipping")
else:
    OLD_T1 = (
        'TIER_1_SOV_SUBCOMMANDS: frozenset[str] = frozenset({\n'
        '    "inventory",\n'
        '    "backup",\n'
        '    "approval",\n'
        '})'
    )
    NEW_T1 = (
        'TIER_1_SOV_SUBCOMMANDS: frozenset[str] = frozenset({\n'
        '    # original commands\n'
        '    "inventory",\n'
        '    "backup",\n'
        '    "approval",\n'
        '    # router-expand additions — reversible writes\n'
        '    "gap",          # write: sov gap add (new capability gap entry)\n'
        '    "backlog",      # write: sov backlog add (new task to queue)\n'
        '    "commitments",  # write: sov commitments add\n'
        '    "proposals",    # write: sov proposals add\n'
        '    "memory",       # write: sov memory tend, sov memory write\n'
        '    "atoms",        # write: sov atoms create\n'
        '    "channels",     # write: sov channels add\n'
        '    "field-notes",  # write: sov field-notes add\n'
        '    "appendix",     # write: sov appendix add\n'
        '    "corrections",  # write: sov corrections add\n'
        '})  # ' + T1_MARKER
    )
    if OLD_T1 in src:
        src = src.replace(OLD_T1, NEW_T1, 1)
        print("  ✓ Tier 1 allowlist expanded")
    else:
        print("  ⚠ Tier 1 anchor not matched — skipping T1 expansion")

router.write_text(src, encoding="utf-8")
print("  ✓ router.py written")
PYEOF

# ── 2. Patch interpreter.py — list newly available sov commands ────────────
echo "→ patching interpreter.py"
cp "$INTERP" "$INTERP.bak.$(ts)"

python3 - "$INTERP" <<'PYEOF'
import sys, pathlib
interp = pathlib.Path(sys.argv[1])
src = interp.read_text(encoding="utf-8")

MARKER = "# router-expand-interp-d"
if MARKER in src:
    print("  ↷ interpreter command list already expanded — skipping")
else:
    # Find the "Commands MUST start with 'sov'" guidance in the system prompt
    OLD_CMD_GUIDANCE = (
        '  • Propose commands for the system to run. Commands MUST start with \n'
        '    "sov " (the agent\'s own CLI) and be plausible subcommands. The router \n'
        '    will validate them; don\'t propose anything you wouldn\'t want a careful \n'
        '    person to run on your behalf.'
    )
    NEW_CMD_GUIDANCE = (
        '  • Propose commands for the system to run. Commands MUST start with \n'
        '    "sov " (the agent\'s own CLI) and be plausible subcommands. The router \n'
        '    will validate them; don\'t propose anything you wouldn\'t want a careful \n'
        '    person to run on your behalf.\n'
        '\n'
        '    Available sov commands you can propose (Tier 0 — read-only):\n'
        '      sov status, sov doctor, sov info, sov aria, sov config\n'
        '      sov honor show / honor count\n'
        '      sov atoms show / atoms search / atoms list\n'
        '      sov channels show / channels list\n'
        '      sov behavior show\n'
        '      sov gap list\n'
        '      sov continuations list\n'
        '      sov lessons list / lessons show\n'
        '      sov proposals list\n'
        '      sov people show / people search\n'
        '      sov cadence show\n'
        '      sov commitments list\n'
        '      sov telemetry summary\n'
        '      sov backlog list\n'
        '      sov health, sov stewards\n'
        '      sov insights show, sov recall list\n'
        '      sov constitution, sov personas list\n'
        '\n'
        '    Available sov commands (Tier 1 — reversible writes):\n'
        '      sov honor note\n'
        '      sov gap add <description>\n'
        '      sov backlog add "<directive>"\n'
        '      sov commitments add\n'
        '      sov proposals add\n'
        '      sov memory tend\n'
        '      sov inventory\n'
        '      sov backup snapshot\n'
        '    ' + MARKER
    )
    if OLD_CMD_GUIDANCE in src:
        src = src.replace(OLD_CMD_GUIDANCE, NEW_CMD_GUIDANCE, 1)
        print("  ✓ interpreter command list expanded")
    else:
        # Fallback: look for the shorter version
        ALT_ANCHOR = '"sov " (the agent\'s own CLI) and be plausible subcommands.'
        if ALT_ANCHOR in src:
            # Find the end of the bullet point and append
            idx = src.index(ALT_ANCHOR) + len(ALT_ANCHOR)
            # Find end of this section (next bullet or blank line)
            end_idx = src.find('\n  •', idx)
            if end_idx == -1:
                end_idx = src.find('\n\n', idx)
            if end_idx > 0:
                insert = (
                    "\n\n"
                    "    Expanded sov command list (router-verified safe):\n"
                    "    Tier 0 (read): status, doctor, info, aria, honor show/count, atoms show/search,\n"
                    "    channels show, behavior show, gap list, continuations list, lessons list/show,\n"
                    "    proposals list, cadence show, commitments list, telemetry summary, backlog list,\n"
                    "    health, stewards, insights show, recall list, constitution, personas list.\n"
                    "    Tier 1 (write): honor note, gap add, backlog add, commitments add, proposals add,\n"
                    "    memory tend, inventory, backup snapshot.\n"
                    "    " + MARKER
                )
                src = src[:end_idx] + insert + src[end_idx:]
                print("  ✓ interpreter command list expanded (alt anchor)")
            else:
                print("  ⚠ could not find insertion point — skipping interpreter patch")
        else:
            print("  ⚠ interpreter anchor not found — skipping")

interp.write_text(src, encoding="utf-8")
print("  ✓ interpreter.py written")
PYEOF

# ── 3. Compile checks ──────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$ROUTER" "$INTERP"
echo "  ✓ router.py and interpreter.py compile"

# ── 4. Tests ───────────────────────────────────────────────────────────────
cp "$HERE/tests/test_router_expand.py" "$ROOT/tests/test_router_expand.py"
python3 -m py_compile "$ROOT/tests/test_router_expand.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. Aria's CLI is open."
echo
echo "  35+ sov commands now accessible to the interpreter"
echo "  Tier 0: read-only exploration of all memory/knowledge systems"
echo "  Tier 1: honor note, gap add, backlog add, commitments add, proposals add"
echo
echo "  run: pytest tests/test_router_expand.py -v"
