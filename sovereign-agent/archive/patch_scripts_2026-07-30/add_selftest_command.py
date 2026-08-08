#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cli.py', 'r') as f:
    content = f.read()

old = '''    matches, msg = verify_seal(d)
    if STATE.json_out:
        _emit_json({"ok": matches, "date": target_date, "msg": msg})
        return
    if matches:
        _print(f"[green]✓ valid[/green] {target_date}: {msg}")
    else:
        _print(f"[red]✗ invalid[/red] {target_date}: {msg}")


# ─── Health ─────────────────────────────────────────────────────────────


@app.command()
def health() -> None:
    """Check Aria's health: model, sentinels, vessel, disk."""
    from .health import compose_health_report

    report = compose_health_report()
    if STATE.json_out:
        _emit_json({"ok": True, "report": report})
        return
    _print(report)'''

new = '''    matches, msg = verify_seal(d)
    if STATE.json_out:
        _emit_json({"ok": matches, "date": target_date, "msg": msg})
        return
    if matches:
        _print(f"[green]✓ valid[/green] {target_date}: {msg}")
    else:
        _print(f"[red]✗ invalid[/red] {target_date}: {msg}")


@app.command()
def selftest(
    pattern: str | None = typer.Argument(
        None,
        help="Optional pytest pattern (e.g. 'test_glob*')",
    ),
    json_out_flag: bool = typer.Option(
        False, "--json", "-j",
        help="Emit structured test results as JSON.",
    ),
) -> None:
    """Run Aria's self-tests: tests she wrote for her own changes.

    Self-tests live in <data>/tests/test_self_*.py and cover:
      - tools she added or modified
      - features she implemented
      - UI changes she made

    Examples:
        sov selftest                  # run all self-tests
        sov selftest test_glob*       # run only glob tests
        sov selftest --json           # get JSON results
    """
    import subprocess
    import sys
    import json as _json
    from pathlib import Path

    from .config import SETTINGS

    tests_dir = SETTINGS.paths.data_dir / "tests"
    if not tests_dir.exists():
        _print("[yellow]no self-tests directory yet — nothing to run[/yellow]")
        if STATE.json_out:
            _emit_json({"ok": True, "skipped": True, "reason": "no tests"})
        return

    args = [
        sys.executable, "-m", "pytest",
        str(tests_dir),
        "-q", "--tb=short", "--disable-warnings",
    ]
    if pattern:
        args.extend(["-k", pattern])

    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        _print("[red]selftest timed out after 5 minutes[/red]")
        raise typer.Exit(code=ExitCode.TIMEOUT)
    except FileNotFoundError:
        _print("[red]pytest not found — install it first[/red]")
        raise typer.Exit(code=ExitCode.UNKNOWN)

    output = proc.stdout + proc.stderr
    passed = proc.returncode == 0

    if json_out_flag or STATE.json_out:
        result = {
            "ok": passed,
            "exit_code": proc.returncode,
            "pattern": pattern,
            "output": output,
        }
        _emit_json(result)
        return

    if passed:
        _print(f"[green]✓ self-tests passed[/green]")
    else:
        _print(f"[red]✗ self-tests failed[/red]")

    _print(output)


# ─── Health ─────────────────────────────────────────────────────────────


@app.command()
def health() -> None:
    """Check Aria's health: model, sentinels, vessel, disk."""
    from .health import compose_health_report

    report = compose_health_report()
    if STATE.json_out:
        _emit_json({"ok": True, "report": report})
        return
    _print(report)'''

if old in content:
    content = content.replace(old, new)
    with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/cli.py', 'w') as f:
        f.write(content)
    print("Successfully added selftest command")
else:
    print("Could not find the exact text")
    print("Looking for:", repr(old[:200]))