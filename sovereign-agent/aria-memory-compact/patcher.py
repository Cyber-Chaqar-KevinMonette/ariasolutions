"""patcher.py — FABLE II M2: register MemoryCompactSentinel, add `sov compact`,
teach ChunkStore.get_chunk the cold-storage fallback.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "memory-compact-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── stewardship/__init__.py — sentinel registration (anchor chain: M1) ───

INIT_ANCHOR = ("from sovereign_agent.consistency import sentinel as "
               "_one_truth  # noqa: F401  # one-truth-d\n")
INIT_NEW = (
    INIT_ANCHOR
    + f"from sovereign_agent.memory_compact import sentinel as _memory_compact  # noqa: F401  # {MARK}\n"
)


def patch_stewardship_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, INIT_ANCHOR, INIT_NEW, label="init anchor"), True


# ── cli.py — `sov compact` sub-app ───────────────────────────────────────

CLI_ANCHOR = 'app.add_typer(vault_app, name="vault")\n'

CLI_BLOCK = f'''

# ─── sov compact — bounded growth with dignity (FABLE II M2) {MARK} ───

compact_app = typer.Typer(
    help="Audit append-only stores; compact old records to verbatim cold "
         "storage with a pointer index. Propose-first; explicit; reversible.")


@compact_app.command("audit")
def compact_audit() -> None:
    """Sizes + growth rates for every append-only store (and the journal)."""
    from sovereign_agent.memory_compact.__main__ import render_audit
    from sovereign_agent.memory_compact.stores import audit_all

    audit = audit_all()
    if STATE.json_out:
        _emit_json(audit)
        raise typer.Exit(ExitCode.OK)
    _print("[bold cyan]memory compact — the append-only stores[/bold cyan]")
    _print(render_audit(audit))
    try:
        from sovereign_agent.memory_compact.sentinel import MemoryCompactSentinel

        sentinel = MemoryCompactSentinel(SETTINGS.paths.data_dir)
        if sentinel.is_enabled():
            sentinel.scan()   # cache the catalog so health reflects this audit
    except Exception:  # noqa: BLE001
        pass


@compact_app.command("preview")
def compact_preview(
    store: str = typer.Argument(..., help="Store id (see `sov compact audit`)."),
    before_days: int = typer.Option(180, "--before-days",
        help="Only records older than this move to cold."),
) -> None:
    """What a run WOULD do — nothing moves."""
    from sovereign_agent.memory_compact import CompactError, preview

    try:
        plan = preview(store, before_days=before_days)
    except CompactError as e:
        _die(ExitCode.USAGE, str(e))
    if STATE.json_out:
        _emit_json(plan.as_dict())
        raise typer.Exit(ExitCode.OK)
    _print(f"would move [bold]{{plan.to_move}}[/bold]/{{plan.total_records}} records "
           f"(older than {{plan.cutoff}}) into {{len(plan.periods)}} cold month(s)")
    for period, n in plan.periods.items():
        _print(f"   {{period}}: {{n}} record(s)")
    _print(f"   ~{{plan.bytes_to_move / 1024:.1f}} KiB · "
           f"{{plan.unparseable_kept_hot}} undatable line(s) stay hot · "
           f"verbatim, reversible, nothing summarized away")


@compact_app.command("run")
def compact_run(
    store: str = typer.Argument(..., help="Store id (see `sov compact audit`)."),
    before_days: int = typer.Option(180, "--before-days",
        help="Only records older than this move to cold."),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation."),
) -> None:
    """Execute a compaction (operator-only; kill-switched; verified; the
    hot-file backup is kept)."""
    from sovereign_agent.memory_compact import CompactError, preview, run

    try:
        plan = preview(store, before_days=before_days)
    except CompactError as e:
        _die(ExitCode.USAGE, str(e))
    if plan.to_move == 0:
        _print("nothing older than the cutoff — store already compact.")
        raise typer.Exit(ExitCode.OK)
    if not yes:
        _print(f"about to move {{plan.to_move}} record(s) to cold storage "
               f"(verbatim; index pointer; .bak kept).")
        if not typer.confirm("proceed?"):
            raise typer.Exit(ExitCode.OK)
    try:
        result = run(store, before_days=before_days)
    except CompactError as e:
        _die(ExitCode.ERROR, str(e))
    if STATE.json_out:
        _emit_json(result.as_dict())
        raise typer.Exit(ExitCode.OK)
    _print(f"[green]moved {{result.moved}}[/green] · kept {{result.kept}} hot · "
           f"periods {{result.periods}}")
    if result.backup:
        _print(f"reversible: hot-file backup at {{result.backup}}")


@compact_app.command("cold")
def compact_cold(
    store: str = typer.Argument(..., help="Store id."),
) -> None:
    """Count what lives in cold storage — proof nothing was lost."""
    from pathlib import Path as _P

    from sovereign_agent.memory_compact import iter_cold_records
    from sovereign_agent.memory_compact.stores import REGISTRY

    spec = REGISTRY.get(store)
    if spec is None:
        _die(ExitCode.USAGE, f"unknown store {{store!r}}")
    store_dir = (_P(SETTINGS.paths.data_dir) / spec.rel_path).parent
    n = sum(1 for _ in iter_cold_records(store, store_dir))
    _print(f"{{n}} record(s) in cold storage for {{store!r}} — verbatim, on disk")


app.add_typer(compact_app, name="compact")

'''

CLI_NEW = CLI_ANCHOR + CLI_BLOCK


def patch_cli(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, CLI_ANCHOR, CLI_NEW, label="cli anchor"), True


# ── checkpoint_chunks/store.py — cold-storage fallback in get_chunk ─────

STORE_ANCHOR = """    def get_chunk(self, chunk_id: str) -> ChunkRecord | None:
        for record in self.all_chunks():
            if record.chunk_id == chunk_id:
                return record
        return None
"""

STORE_NEW = f"""    def get_chunk(self, chunk_id: str) -> ChunkRecord | None:
        for record in self.all_chunks():
            if record.chunk_id == chunk_id:
                return record
        # {MARK} — compacted chunks stay ADDRESSABLE: on a hot miss, search
        # the cold files the compact index names (verbatim, on disk, cold).
        try:
            from sovereign_agent.memory_compact import iter_cold_records

            for raw in iter_cold_records("chunks", self.root):
                try:
                    record = ChunkRecord(**raw)
                except TypeError:
                    continue
                if record.chunk_id == chunk_id:
                    return record
        except Exception:  # noqa: BLE001 — cold read is a gift, never a crash
            pass
        return None
"""


def patch_chunk_store(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, STORE_ANCHOR, STORE_NEW, label="store anchor"), True
