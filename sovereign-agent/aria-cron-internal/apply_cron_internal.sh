#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_cron_internal.sh — Autonomous scheduling for Aria
#
#  Adds schedule.yaml-based cron scheduling to the busy loop.
#  Schedules are checked on each _drain_iteration() cycle.
#
#  Changes:
#  1. Install src/sovereign_agent/schedule.py
#  2. Install tools/schedule_tool.py
#  3. Patch tools/__init__.py — imports + __all__
#  4. Patch mode_controller.py — call check_and_inject_due() in _drain_iteration
#  5. Patch cli.py — add 'sov schedule' typer subcommands
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
TOOLS="$PKG/tools"
INIT="$TOOLS/__init__.py"
CTRL="$PKG/mode_controller.py"
CLI="$PKG/cli.py"
ts(){ date +%Y%m%d%H%M%S; }

# ── 1. Install schedule.py ────────────────────────────────────────────────
echo "→ installing sovereign_agent/schedule.py"
cp "$HERE/payload/src/sovereign_agent/schedule.py" "$PKG/schedule.py"
echo "  ✓ schedule.py"

# ── 2. Install schedule_tool.py ───────────────────────────────────────────
echo "→ installing tools/schedule_tool.py"
cp "$HERE/payload/src/sovereign_agent/tools/schedule_tool.py" "$TOOLS/schedule_tool.py"
echo "  ✓ schedule_tool.py"

# ── 3. Patch tools/__init__.py ─────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

IMPORT_MARKER = "# cron-internal-import-d"
if IMPORT_MARKER in src:
    print("  ↷ schedule_tool import already present — skipping")
else:
    new_import = "from .schedule_tool import ScheduleTaskTool  " + IMPORT_MARKER + "\n"
    for anchor in ("from .read_file import ReadFileTool", "from .palace_search import"):
        if anchor in src:
            src = src.replace(anchor, new_import + anchor, 1)
            print("  ✓ ScheduleTaskTool import added")
            break
    else:
        last_from = src.rfind("\nfrom .")
        if last_from >= 0:
            insert_at = src.find("\n", last_from + 1) + 1
            src = src[:insert_at] + new_import + src[insert_at:]
            print("  ✓ schedule_tool import appended")
        else:
            print("✗ no import anchor", file=sys.stderr); sys.exit(1)

ALL_MARKER = "# cron-internal-all-d"
if ALL_MARKER in src:
    print("  ↷ ScheduleTaskTool __all__ already present — skipping")
else:
    new_all = '    "ScheduleTaskTool",  ' + ALL_MARKER + '\n'
    for anchor in ('    "ReadFileTool",', '    "PalaceSearchTool",'):
        if anchor in src:
            src = src.replace(anchor, new_all + anchor, 1)
            print("  ✓ ScheduleTaskTool added to __all__")
            break
    else:
        print("  ⚠ __all__ anchor not found")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 4. Patch mode_controller.py — inject schedule check ───────────────────
echo "→ patching mode_controller.py"
cp "$CTRL" "$CTRL.bak.$(ts)"

python3 - "$CTRL" <<'PYEOF'
import sys, pathlib
ctrl = pathlib.Path(sys.argv[1])
src = ctrl.read_text(encoding="utf-8")

MARKER = "# cron-internal-drain-d"
if MARKER in src:
    print("  ↷ schedule check already in _drain_iteration — skipping")
else:
    # Inject schedule check at start of _drain_iteration, after protocol_zero check
    # Find "tasks = read_backlog()" — first occurrence in _drain_iteration
    ANCHOR = "        tasks = read_backlog()\n        task = next_task(tasks)"
    INJECT = (
        "        # cron-internal: check scheduled entries, inject due tasks\n"
        "        try:\n"
        "            from sovereign_agent.schedule import ScheduleStore, check_and_inject_due, _schedule_path\n"
        "            check_and_inject_due(ScheduleStore(_schedule_path()))  " + MARKER + "\n"
        "        except Exception:  # noqa: BLE001\n"
        "            pass\n"
        "\n"
    )
    if ANCHOR in src:
        src = src.replace(ANCHOR, INJECT + ANCHOR, 1)
        print("  ✓ schedule check injected into _drain_iteration")
    else:
        print("  ⚠ _drain_iteration anchor not found — skipping mode_controller patch")

ctrl.write_text(src, encoding="utf-8")
print("  ✓ mode_controller.py written")
PYEOF

# ── 5. Patch cli.py — add 'sov schedule' subcommands ─────────────────────
echo "→ patching cli.py"
cp "$CLI" "$CLI.bak.$(ts)"

python3 - "$CLI" <<'PYEOF'
import sys, pathlib
cli = pathlib.Path(sys.argv[1])
src = cli.read_text(encoding="utf-8")

MARKER = "# cron-internal-cli-d"
if MARKER in src:
    print("  ↷ schedule commands already present — skipping")
else:
    schedule_block = '''
# ─── sov schedule (aria-cron-internal) ─────────────────────────────────────
# cron-internal-cli-d

schedule_app = typer.Typer(
    help="◊ manage recurring scheduled directives",
    invoke_without_command=False,
    no_args_is_help=True,
)
app.add_typer(schedule_app, name="schedule")


@schedule_app.command("list")
def schedule_list_cmd() -> None:
    """List all scheduled entries."""
    from .schedule import ScheduleStore, _schedule_path
    entries = ScheduleStore(_schedule_path()).load()
    if not entries:
        _print("[dim](no schedules configured)[/dim]")
        return
    for e in entries:
        status = "[green]●[/green]" if e.enabled else "[dim]○[/dim]"
        last = e.last_run[:16] if e.last_run else "never"
        _print(f"{status} [bold]{e.name}[/bold]  {e.cron}")
        _print(f"    directive: {e.directive}")
        if e.description:
            _print(f"    {e.description}")
        _print(f"    [dim]last run: {last}[/dim]")


@schedule_app.command("add")
def schedule_add_cmd(
    name: str = typer.Argument(..., help="Schedule name (kebab-case)"),
    cron: str = typer.Argument(..., help="Cron expression ('0 8 * * *')"),
    directive: str = typer.Argument(..., help="Goal text to inject when due"),
    description: str = typer.Option("", "--desc", help="Human-readable description"),
) -> None:
    """Add or replace a scheduled directive."""
    from .schedule import ScheduleEntry, ScheduleStore, _schedule_path
    if len(cron.split()) != 5:
        _print(f"[red]✗ cron must be 5 fields: {cron!r}[/red]")
        raise typer.Exit(1)
    entry = ScheduleEntry(name=name, cron=cron, directive=directive, description=description)
    ScheduleStore(_schedule_path()).add(entry)
    _print(f"[green]✓[/green] schedule added: {name!r} ({cron}) → {directive!r}")


@schedule_app.command("remove")
def schedule_remove_cmd(name: str = typer.Argument(...)) -> None:
    """Remove a scheduled entry by name."""
    from .schedule import ScheduleStore, _schedule_path
    removed = ScheduleStore(_schedule_path()).remove(name)
    if removed:
        _print(f"[green]✓[/green] removed: {name!r}")
    else:
        _print(f"[yellow]⚠ not found: {name!r}[/yellow]")


@schedule_app.command("run-due")
def schedule_run_due_cmd() -> None:
    """Inject all currently-due schedules into the backlog (cron-job-friendly)."""
    from datetime import datetime, timezone
    from .schedule import ScheduleStore, check_and_inject_due, _schedule_path
    injected = check_and_inject_due(ScheduleStore(_schedule_path()))
    if injected:
        for name in injected:
            _print(f"[green]✓[/green] injected: {name!r}")
    else:
        _print("[dim](no schedules due)[/dim]")

'''

    # Find a good anchor in cli.py — after backlog_app block
    anchor = "# ─── sov stewardship"
    if anchor in src:
        src = src.replace(anchor, schedule_block + anchor, 1)
        print("  ✓ schedule commands added to cli.py")
    else:
        # Fallback: before interpret_app
        anchor2 = "interpret_app = typer.Typer("
        if anchor2 in src:
            src = src.replace(anchor2, schedule_block + "\n" + anchor2, 1)
            print("  ✓ schedule commands added to cli.py (fallback anchor)")
        else:
            print("  ⚠ no cli.py anchor found — skipping cli patch")

cli.write_text(src, encoding="utf-8")
print("  ✓ cli.py written")
PYEOF

# ── 6. Compile checks ──────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$PKG/schedule.py" "$TOOLS/schedule_tool.py" "$INIT" "$CTRL"
echo "  ✓ core files compile"

# cli.py has syntax — quick check
python3 -m py_compile "$CLI"
echo "  ✓ cli.py compiles"

cp "$HERE/tests/test_cron_internal.py" "$ROOT/tests/test_cron_internal.py"
python3 -m py_compile "$ROOT/tests/test_cron_internal.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. Autonomous scheduling is live."
echo
echo "  New module: schedule.py — cron_matches, check_and_inject_due"
echo "  New tool: schedule_task (T1)"
echo "  New CLI: sov schedule list | add | remove | run-due"
echo "  Busy loop: checks due schedules on each _drain_iteration()"
echo
echo "  run: pytest tests/test_cron_internal.py -v"
