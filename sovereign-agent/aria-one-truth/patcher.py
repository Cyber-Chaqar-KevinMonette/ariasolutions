"""patcher.py — FABLE II M1: register the ConsistencySentinel + `sov truth`.

Anchored transforms only; MARK-idempotent; _replace_once refuses a moved
anchor loudly (never silent corruption)."""
from __future__ import annotations

MARK = "one-truth-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── stewardship/__init__.py — sentinel side-effect import ────────────────

INIT_ANCHOR = ("from sovereign_agent.loose_threads import sentinel as "
               "_loose_threads  # noqa: F401  # loose-threads-d\n")
INIT_NEW = (
    INIT_ANCHOR
    + f"from sovereign_agent.consistency import sentinel as _one_truth  # noqa: F401  # {MARK}\n"
)


def patch_stewardship_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, INIT_ANCHOR, INIT_NEW, label="init anchor"), True


# ── cli.py — `sov truth` ─────────────────────────────────────────────────

CLI_ANCHOR = 'app.add_typer(vault_app, name="vault")\n'

CLI_COMMAND = f'''

@app.command(name="truth")  # {MARK}
def truth_cmd(
    as_json: bool = typer.Option(False, "--json",
        help="Machine-readable check results."),
) -> None:
    """Cross-store consistency: check the joins between her memory organs.

    Each join is one named check with a mechanical verdict. Findings carry
    repair PROPOSALS — nothing is ever auto-repaired (one life, one truth).
    """
    from sovereign_agent.consistency.__main__ import render_results
    from sovereign_agent.consistency.checks import run_all
    from sovereign_agent.consistency.sentinel import ConsistencySentinel

    results = run_all()
    try:
        sentinel = ConsistencySentinel(SETTINGS.paths.data_dir)
        if sentinel.is_enabled():
            sentinel.scan()   # persist the catalog so health reflects this sweep
    except Exception:  # noqa: BLE001 — the report matters more than the cache
        pass
    if as_json:
        _emit_json({{"checks": [r.as_dict() for r in results]}})
        raise typer.Exit(ExitCode.OK)
    _print("[bold cyan]one truth — the joins, checked[/bold cyan]")
    _print(render_results(results))


'''

CLI_NEW = CLI_ANCHOR + CLI_COMMAND


def patch_cli(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, CLI_ANCHOR, CLI_NEW, label="cli anchor"), True
