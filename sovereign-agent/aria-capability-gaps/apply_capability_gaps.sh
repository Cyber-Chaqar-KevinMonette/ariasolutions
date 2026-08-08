#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_capability_gaps.sh — Aria logs capability gaps instead of stopping
#  (v0.2.42.0)
#
#  Changes (surgical patches to router.py):
#
#    1. _safe_alternatives() — now does fuzzy matching against the real sov
#       subcommand lists (TIER_0/1/2_SOV_SUBCOMMANDS) to suggest real
#       alternatives rather than generic fallbacks.
#
#    2. _route_work() — when a command fails with "unknown sov subcommand",
#       emits a "capability-gap-d" event to the audit trail (observable,
#       append-only, no new catalog types needed) and includes the gap in
#       the Ambiguous response so Aria sees it.
#
#    3. validate_command() return — when subcommand is unknown, includes
#       a list of available sov subcommands in the reason string so the
#       Ambiguous message Aria receives is actionable.
#
#  Idempotent. Backs up router.py before patching.
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

ROUTER="$ROOT/src/sovereign_agent/router.py"
ts(){ date +%Y%m%d%H%M%S; }
cp "$ROUTER" "$ROUTER.bak.$(ts)"

echo "→ patching router.py"
python3 - "$ROUTER" <<'PYEOF'
import sys, pathlib

f = pathlib.Path(sys.argv[1])
src = f.read_text(encoding="utf-8")

# ── 1. Improve the unknown-subcommand return to include available commands ──

MARKER1 = "# ── _capability_gap_patched ──"
if MARKER1 in src:
    print("  ↷ capability-gap patch already applied — skipping")
    sys.exit(0)

OLD1 = '    return False, f"unknown sov subcommand: {sub}", 3'
NEW1 = '''\
    # ── _capability_gap_patched ──
    known = sorted(
        TIER_0_SOV_SUBCOMMANDS | TIER_1_SOV_SUBCOMMANDS | TIER_2_SOV_SUBCOMMANDS
    )
    known_str = ", ".join(known)
    return False, f"unknown sov subcommand: {sub!r}. known: {known_str}", 3\
'''
if OLD1 not in src:
    print("✗ unknown-subcommand return anchor not found in router.py", file=sys.stderr)
    sys.exit(1)
src = src.replace(OLD1, NEW1, 1)
print("  ✓ unknown-subcommand return now includes available subcommand list")

# ── 2. Improve _safe_alternatives to fuzzy-match real subcommands ───────────

OLD2 = '''\
def _safe_alternatives(intent: Work, blocked_cmd: str) -> list[str]:
    """Suggest up to 3 safer alternatives when a command is rejected."""
    base = []
    if intent.project_hint:
        base.append(f"scan the project '{intent.project_hint}'")
        base.append(f"list what's in '{intent.project_hint}'")
    base.append("just save this as conversation")
    return base[:3]\
'''
NEW2 = '''\
def _safe_alternatives(intent: Work, blocked_cmd: str) -> list[str]:
    """Suggest up to 3 safer alternatives when a command is rejected.

    Tries fuzzy-matching the blocked command against known sov subcommands
    using difflib so Aria gets real suggestions, not generic fallbacks.
    """
    import difflib, shlex as _shlex
    base: list[str] = []

    # Extract the attempted sov subcommand (if any) for fuzzy matching
    attempted_sub: str | None = None
    try:
        argv = _shlex.split(blocked_cmd)
        if len(argv) >= 2 and argv[0] in ("sov", "sovereign"):
            attempted_sub = argv[1]
    except ValueError:
        pass

    if attempted_sub:
        known = sorted(
            TIER_0_SOV_SUBCOMMANDS | TIER_1_SOV_SUBCOMMANDS | TIER_2_SOV_SUBCOMMANDS
        )
        close = difflib.get_close_matches(attempted_sub, known, n=3, cutoff=0.4)
        for match in close:
            base.append(f"sov {match}")

    if intent.project_hint:
        base.append(f"sov projects list (to see '{intent.project_hint}')")

    if not base:
        base = ["sov status", "sov projects list", "sov channels show context"]

    base.append(
        "build it: create aria-<name>/ staging folder with apply_<name>.sh"
    )
    return base[:4]\
'''
if OLD2 not in src:
    print("✗ _safe_alternatives anchor not found in router.py", file=sys.stderr)
    sys.exit(1)
src = src.replace(OLD2, NEW2, 1)
print("  ✓ _safe_alternatives now fuzzy-matches real sov subcommands")

# ── 3. Emit capability-gap event in _route_work when command is unknown ─────

OLD3 = '''\
            ok, reason, tier = validate_command(cmd)
            if not ok:
                return self._route_ambiguous(Ambiguous(
                    text=intent.summary,
                    question=(
                        f"I can't run `{cmd}` ({reason}). "
                        "Did you mean one of these instead?"
                    ),
                    options=_safe_alternatives(intent, cmd),
                    rationale=f"command-validation: {reason}",
                ))\
'''
NEW3 = '''\
            ok, reason, tier = validate_command(cmd)
            if not ok:
                # Emit a capability-gap event when an unknown sov subcommand
                # is encountered so the operator can audit what Aria tried.
                if "unknown sov subcommand" in reason:
                    self.event_sink({
                        "kind": "capability-gap-d",
                        "proposed_command": cmd,
                        "reason": reason,
                        "summary": intent.summary,
                        "note": (
                            "Aria proposed a sov command that doesn't exist. "
                            "Consider building it in aria-<name>/ staging folder."
                        ),
                    })
                return self._route_ambiguous(Ambiguous(
                    text=intent.summary,
                    question=(
                        f"I can't run `{cmd}` ({reason}). "
                        "Did you mean one of these instead? "
                        "(I've logged this as a capability gap in the event trail.)"
                    ),
                    options=_safe_alternatives(intent, cmd),
                    rationale=f"command-validation: {reason}",
                ))\
'''
if OLD3 not in src:
    print("✗ _route_work validation anchor not found in router.py", file=sys.stderr)
    sys.exit(1)
src = src.replace(OLD3, NEW3, 1)
print("  ✓ capability-gap-d event emitted for unknown sov subcommands")

f.write_text(src, encoding="utf-8")
print("  ✓ router.py written")
PYEOF

echo "→ compile check"
python3 -m py_compile "$ROUTER"
echo "  ✓ compiles"

cp "$HERE/tests/test_capability_gaps.py" "$ROOT/tests/test_capability_gaps.py"
echo "  ✓ tests/test_capability_gaps.py installed (first test_router.py!)"
python3 -m py_compile "$ROOT/tests/test_capability_gaps.py"
echo "  ✓ test file compiles"

echo
echo "✓ done. next:"
echo "    pytest tests/test_capability_gaps.py -v"
echo "    # then try: tell Aria to run 'sov synthesize-report'"
echo "    # she should propose it → router logs capability-gap-d event"
echo "    # + returns fuzzy-matched alternatives"
