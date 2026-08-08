# ════════════════════════════════════════════════════════════════════════
# ◊ agentic — natural-language goal → plan → gap analysis → gated execute
#   (v0.2.35.0)  The flagship plain-English entry point. Aria plans, works
#   out which subsystems she needs vs. lacks, drafts proposals for the gaps,
#   routes flow-specific variants, and executes with a per-step approval gate.
#   Steps that would change Aria's own code/config always ask — even --yes.
# ════════════════════════════════════════════════════════════════════════


def _build_agentic_run():
    """Wire ErebloStore → ProjectsManager → AgenticLoop with the standard
    handlers; return (run, projects, project_id)."""
    from pathlib import Path
    from .persistence.store import ErebloStore
    from .persistence.projects import ProjectsManager
    from .workflow.agentic_loop import AgenticLoop
    from .workflow.handlers import ShellHandler, FileWriteHandler, FileReadHandler
    from .workflow.evolving_run import EvolvingAgenticRun
    from .workflow.requests import RequestStore

    store = ErebloStore(SETTINGS.paths.atoms_db)
    projects = ProjectsManager(store)
    loop = AgenticLoop(projects)
    requests = RequestStore(store)

    sandbox = SETTINGS.paths.sandbox_dir
    sandbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    loop.register_tool_handler("shell", ShellHandler())
    loop.register_tool_handler("file_write", FileWriteHandler([sandbox]))
    loop.register_tool_handler("file_read", FileReadHandler([sandbox]))

    proj = projects.get_project_by_name("agentic")
    project_id = proj.project_id if proj else projects.create_project(
        "agentic", description="Goals run via `sov agentic`.")

    self_roots = [Path(__file__).resolve().parent, SETTINGS.paths.config_dir]
    proposals_root = SETTINGS.paths.data_dir / "proposals" / "capabilities"
    run = EvolvingAgenticRun(loop, proposals_root=proposals_root,
                             self_roots=self_roots, request_store=requests)
    return run, projects, project_id, requests


def _render_plan(plan) -> None:
    if STATE.json_out:
        _emit_json({
            "goal": plan.goal, "band": plan.band, "flow": plan.flow,
            "clarifying_questions": plan.clarifying_questions,
            "steps": [{"kind": s.action_kind, "title": s.title,
                       "input": s.action_input} for s in plan.steps],
            "gap": (None if not plan.gap_report else {
                "needed": plan.gap_report.needed,
                "available": plan.gap_report.available,
                "missing": plan.gap_report.missing}),
            "variant_choice": {k: (v[0].capability.name if v else None)
                               for k, v in plan.variant_choices.items()},
            "proposals_written": plan.proposals_written,
        })
        return
    _print(f"\n[bold cyan]◊ plan[/bold cyan]  [dim](maturity {plan.band})[/dim]")
    if plan.clarifying_questions:
        _print("[yellow]I need a little more to go on:[/yellow]")
        for q in plan.clarifying_questions:
            _print(f"  • {q}")
        return
    for i, s in enumerate(plan.steps, 1):
        best = plan.best_variant(s.action_kind)
        via = f"  [dim]via {best.capability.name} ({best.reason})[/dim]" if best else ""
        _print(f"  {i}. [{s.action_kind}] {s.title}{via}")
    if plan.gap_report:
        _print(f"\n[dim]subsystems — {plan.gap_report.summary_text()}[/dim]")
        if plan.gap_report.missing:
            _print(f"[yellow]missing: {', '.join(plan.gap_report.missing)}[/yellow]")
            for p in plan.proposals_written:
                _print(f"  [dim]drafted proposal:[/dim] {p}")
            _print("[dim]Review a draft, implement it, then move it into "
                   "workflow/handlers/ and register it to bring it online.[/dim]")


def _render_result(result) -> None:
    if STATE.json_out:
        _emit_json({"goal": result.goal, "decision": result.decision,
                    "workflow_id": result.workflow_id,
                    "final_status": result.final_status, "notes": result.notes})
        return
    colors = {"executed": "green", "paused_for_review": "yellow",
              "needs_capability": "yellow", "needs_clarification": "yellow",
              "blocked": "red"}
    c = colors.get(result.decision, "white")
    _render_plan(result.plan)
    _print(f"\n[bold {c}]◊ {result.decision.replace('_', ' ')}[/bold {c}]")
    for n in result.notes:
        _print(f"  • {n}")
    if result.final_status:
        bs = result.final_status.get("by_status", {})
        _print(f"  [dim]steps: {bs}[/dim]")
    if result.workflow_id:
        _print(f"  [dim]workflow: {result.workflow_id}  ·  watch with "
               f"`sov events --follow`[/dim]")


@app.command(name="agentic")
def agentic_cmd(
    goal: str = typer.Argument(..., help="Plain-English goal."),
    flow: str = typer.Option("", "--flow",
        help="Describe the flow/context so Aria routes the best variant."),
    plan_only: bool = typer.Option(False, "--plan",
        help="Plan + gap analysis only; don't execute."),
    yes: bool = typer.Option(False, "--yes", "-y",
        help="Batch-approve consequential steps (self-modifications still ask)."),
    allow_missing: bool = typer.Option(False, "--allow-missing",
        help="Proceed even if some subsystems are missing."),
) -> None:
    """Goal → maturity gate → plan → gap analysis → variant routing → gated run.

    M0 asks you to clarify · M1 writes a plan without running it · M2/M3 run
    with per-step approval. Any step that would modify Aria's own code or
    config always prompts, even with --yes.

        sov agentic "set up a python project skeleton with tests and a readme"
        sov agentic "inventory the sandbox for markdown" --plan
        sov agentic "build and test the parser" --flow "git, build, test"
    """
    run, _projects, project_id, _requests = _build_agentic_run()

    if plan_only:
        _render_plan(run.plan_only(goal, flow=flow))
        raise typer.Exit(ExitCode.OK)

    def approve(step, decision) -> bool:
        modifies_self = "code or configuration" in decision.reason
        if yes and not modifies_self:
            return True
        if STATE.json_out:
            return False  # can't prompt in json mode → hold for a human
        _print(f"\n[bold]proposed step[/bold]: {step.title}")
        _print(f"  kind: {step.action_kind}   input: {step.action_input}")
        _print(f"  [yellow]{decision.reason}[/yellow]")
        if modifies_self:
            _print("  [red]this touches Aria's own code/config — approval required[/red]")
        return typer.confirm("  run this step?")

    result = run.execute(goal, project_id, flow=flow, approve=approve,
                         allow_missing=allow_missing)
    _render_result(result)
    ok = result.decision in (
        "executed", "paused_for_review", "needs_clarification", "needs_capability")
    raise typer.Exit(ExitCode.OK if ok else ExitCode.ERROR)


@app.command(name="capabilities")
def capabilities_cmd(
    goal: str = typer.Option("", "--goal",
        help="Show the subsystem gap report for a goal."),
    route: str = typer.Option("", "--route",
        help="Show variant routing for this flow (pair with --kind)."),
    kind: str = typer.Option("shell", "--kind",
        help="Action kind to route when using --route."),
) -> None:
    """List Aria's subsystems; analyze gaps for a goal; route variants for a flow.

        sov capabilities
        sov capabilities --goal "schedule a daily backup reminder"
        sov capabilities --route "git, commit, branch" --kind shell
    """
    run, _projects, _pid, _requests = _build_agentic_run()
    reg = run.registry

    if goal:
        _render_plan(run.plan_only(goal))
        raise typer.Exit(ExitCode.OK)

    if route:
        from .workflow.capabilities import VariantRouter
        ranked = VariantRouter().rank(f"{kind}.default", route, reg)
        if STATE.json_out:
            _emit_json({"kind": kind, "flow": route,
                        "ranked": [{"name": r.capability.name, "score": r.score,
                                    "reason": r.reason} for r in ranked]})
            raise typer.Exit(ExitCode.OK)
        _print(f"\n[bold cyan]◊ variant routing[/bold cyan] for flow "
               f"[italic]{route!r}[/italic] (kind={kind})")
        if not ranked:
            _print("  [dim]no variants registered for this kind[/dim]")
        for i, r in enumerate(ranked, 1):
            mark = "★" if i == 1 else " "
            _print(f"  {mark} {r.capability.name}  [dim]score {r.score} — {r.reason}[/dim]")
        raise typer.Exit(ExitCode.OK)

    # default: list the registry
    caps = reg.all()
    if STATE.json_out:
        _emit_json({"capabilities": [
            {"name": c.name, "action_kind": c.action_kind, "status": c.status,
             "flow_tags": sorted(c.flow_tags), "variant_of": c.variant_of}
            for c in caps]})
        raise typer.Exit(ExitCode.OK)
    table = Table(title="◊ Aria's subsystems")
    table.add_column("name", style="cyan")
    table.add_column("kind")
    table.add_column("status")
    table.add_column("flows", overflow="fold", style="dim")
    for c in caps:
        style = "green" if c.status == "available" else "yellow"
        table.add_row(c.name, c.action_kind, f"[{style}]{c.status}[/{style}]",
                      ", ".join(sorted(c.flow_tags)))
    _print(table)
    missing = sorted(reg.missing_kinds())
    if missing:
        _print(f"[yellow]gaps: {', '.join(missing)}[/yellow] "
               f"[dim]— `sov agentic \"<goal needing it>\"` will draft a proposal[/dim]")


# ════════════════════════════════════════════════════════════════════════
# 📬 requests — the collaboration inbox (Aria ↔ human)  (v0.2.36.0)
#   A two-way work queue: Aria posts asks/suggestions/blockers, you answer,
#   items get logged. Pauses from `sov agentic` land here automatically.
# ════════════════════════════════════════════════════════════════════════


def _open_request_store():
    from .persistence.store import ErebloStore
    from .workflow.requests import RequestStore
    return RequestStore(ErebloStore(SETTINGS.paths.atoms_db))


requests_app = typer.Typer(
    help="📬 Collaboration inbox — Aria's asks and your answers.",
    invoke_without_command=True)


def _render_requests(items) -> None:
    if STATE.json_out:
        _emit_json([{"id": r.request_id, "short": r.request_id[-6:], "kind": r.kind,
                     "title": r.title, "status": r.status, "answer": r.answer,
                     "workflow_id": r.workflow_id, "created_at": r.created_at}
                    for r in items])
        return
    if not items:
        _print("📭 [dim]inbox is clear — nothing waiting on you[/dim]")
        return
    for r in items:
        _print(r.one_line())
        if r.body:
            for line in r.body.splitlines():
                _print(f"      [dim]{line}[/dim]")
        if r.answer:
            _print(f"      [green]↳ {r.answer}[/green]")


@requests_app.callback()
def requests_main(ctx: typer.Context) -> None:
    """With no subcommand, show what's open. 🟡"""
    if ctx.invoked_subcommand is not None:
        return
    rs = _open_request_store()
    _render_requests(rs.list_open())


@requests_app.command("list")
def requests_list_cmd(
    all_: bool = typer.Option(False, "--all", "-a", help="Include resolved/answered."),
    status: str = typer.Option("", "--status",
        help="Filter: open|answered|resolved|cancelled."),
) -> None:
    """List requests."""
    rs = _open_request_store()
    if status:
        _render_requests(rs.list(status=status))
    elif all_:
        _render_requests(rs.list())
    else:
        _render_requests(rs.list_open())


@requests_app.command("ask")
def requests_ask_cmd(
    title: str = typer.Argument(..., help="Short summary of the ask."),
    kind: str = typer.Option("question", "--kind", "-k",
        help="question|scan_files|suggestion|approval|decision|blocker|note|celebrate"),
    body: str = typer.Option("", "--body", "-b", help="Longer detail (optional)."),
) -> None:
    """File a request (Aria, a script, or you can use this)."""
    rs = _open_request_store()
    req = rs.open(kind, title, body=body)
    if STATE.json_out:
        _emit_json({"ok": True, "id": req.request_id, "short": req.request_id[-6:]})
        raise typer.Exit(ExitCode.OK)
    _print(f"{req.emoji} filed request [{req.request_id[-6:]}] — {req.title}")


@requests_app.command("show")
def requests_show_cmd(request_id: str = typer.Argument(..., help="Full or short id.")) -> None:
    """Show one request in full."""
    rs = _open_request_store()
    r = rs.get(request_id)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json(r.__dict__); raise typer.Exit(ExitCode.OK)
    body = (f"{r.emoji} [bold]{r.title}[/bold]\n"
            f"[dim]id:[/dim] {r.request_id}\n"
            f"[dim]kind:[/dim] {r.kind}   [dim]status:[/dim] {r.status_emoji} {r.status}\n"
            f"[dim]created:[/dim] {r.created_at}\n")
    if r.workflow_id:
        body += f"[dim]workflow:[/dim] {r.workflow_id}\n"
    if r.body:
        body += f"\n{r.body}\n"
    if r.answer:
        body += f"\n[green]your answer:[/green] {r.answer}\n"
    _print(Panel(body, title=f"📨 request {r.request_id[-6:]}", border_style="cyan"))


@requests_app.command("answer")
def requests_answer_cmd(
    request_id: str = typer.Argument(..., help="Full or short id."),
    text: str = typer.Argument(..., help="Your answer / guidance / solution."),
) -> None:
    """Answer a request. 🟢"""
    rs = _open_request_store()
    r = rs.answer(request_id, text)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json({"ok": True, "id": r.request_id, "status": r.status})
        raise typer.Exit(ExitCode.OK)
    _print(f"🟢 answered [{r.request_id[-6:]}] — thanks, that unblocks her ✨")


@requests_app.command("resolve")
def requests_resolve_cmd(request_id: str = typer.Argument(..., help="Full or short id.")) -> None:
    """Mark a request done and log it. ✅"""
    rs = _open_request_store()
    r = rs.resolve(request_id)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json({"ok": True, "id": r.request_id, "status": r.status})
        raise typer.Exit(ExitCode.OK)
    _print(f"✅ resolved [{r.request_id[-6:]}] — onward 🚀")


@requests_app.command("cancel")
def requests_cancel_cmd(request_id: str = typer.Argument(..., help="Full or short id.")) -> None:
    """Cancel a request without acting on it. ⚪"""
    rs = _open_request_store()
    r = rs.cancel(request_id)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json({"ok": True, "id": r.request_id, "status": r.status})
        raise typer.Exit(ExitCode.OK)
    _print(f"⚪ cancelled [{r.request_id[-6:]}]")


app.add_typer(requests_app, name="requests")


# ════════════════════════════════════════════════════════════════════════
# 🔐 vault — owner-controlled encryption at rest  (v0.2.36.0)
#   Encrypts designated files so they're unreadable without YOUR passphrase.
#   The owner is you. The key is derived from your passphrase and never
#   stored. Rotate to change it. There is no backdoor — keep a backup of the
#   passphrase. This protects files at rest; it is not DRM and cannot make
#   software "obey" anyone. See security/vault.py for the full threat model.
# ════════════════════════════════════════════════════════════════════════


def _open_vault():
    from .security.vault import Vault
    return Vault(SETTINGS.paths.config_dir / "vault")


vault_app = typer.Typer(help="🔐 Owner-controlled encryption at rest.",
                        no_args_is_help=True)


@vault_app.command("init")
def vault_init_cmd() -> None:
    """Set the owner passphrase (one time). Refuses to overwrite — use rotate."""
    from .security.vault import VaultError
    v = _open_vault()
    if v.is_initialized:
        _die(ExitCode.USAGE, "owner already set", hint="use `sov vault rotate` to change it")
    pw = typer.prompt("Set owner passphrase", hide_input=True, confirmation_prompt=True)
    try:
        v.init_owner(pw)
    except VaultError as e:
        _die(ExitCode.USAGE, str(e))
    _print("🔐 [green]owner set.[/green] keep this passphrase safe — there is no backdoor.")
    _print("[dim]you are the owner. rotate any time with `sov vault rotate`.[/dim]")


@vault_app.command("status")
def vault_status_cmd() -> None:
    """Show vault status (never prints the key)."""
    v = _open_vault()
    st = v.status()
    if STATE.json_out:
        _emit_json(st); raise typer.Exit(ExitCode.OK)
    lock = "🔐 initialized" if st["initialized"] else "🔓 not initialized"
    crypto = "available" if st["crypto_available"] else "MISSING (pip install cryptography)"
    body = (f"{lock}\n[dim]crypto:[/dim] {crypto}\n"
            f"[dim]credential:[/dim] {st['credential_path']}\n")
    if st["initialized"]:
        body += f"[dim]created:[/dim] {st.get('created_at')}\n"
    _print(Panel(body, title="🔐 vault", border_style="green"))


@vault_app.command("verify")
def vault_verify_cmd() -> None:
    """Check a passphrase against the owner credential."""
    v = _open_vault()
    if not v.is_initialized:
        _die(ExitCode.USAGE, "vault not initialized", hint="run `sov vault init`")
    pw = typer.prompt("Owner passphrase", hide_input=True)
    ok = v.verify_owner(pw)
    if STATE.json_out:
        _emit_json({"verified": ok}); raise typer.Exit(ExitCode.OK if ok else ExitCode.ERROR)
    _print("✅ [green]verified — that's you.[/green]" if ok
           else "❌ [red]no match.[/red]")
    raise typer.Exit(ExitCode.OK if ok else ExitCode.ERROR)


@vault_app.command("encrypt")
def vault_encrypt_cmd(
    path: str = typer.Argument(..., help="File to encrypt."),
    remove: bool = typer.Option(False, "--remove",
        help="Delete the plaintext after encrypting."),
    out: str = typer.Option("", "--out", help="Output path (default: <file>.enc)."),
) -> None:
    """Encrypt a file under your passphrase. 🔒"""
    from pathlib import Path
    from .security.vault import VaultError, VaultLocked, VaultUnavailable
    v = _open_vault()
    pw = typer.prompt("Owner passphrase", hide_input=True)
    try:
        dest = v.encrypt_file(Path(path).expanduser(), pw,
                              dest=Path(out).expanduser() if out else None,
                              remove_plaintext=remove)
    except (VaultLocked, VaultUnavailable, VaultError) as e:
        _die(ExitCode.ERROR, str(e))
    if STATE.json_out:
        _emit_json({"ok": True, "encrypted": str(dest)}); raise typer.Exit(ExitCode.OK)
    _print(f"🔒 encrypted → {dest}" + ("  [dim](plaintext removed)[/dim]" if remove else ""))


@vault_app.command("decrypt")
def vault_decrypt_cmd(
    path: str = typer.Argument(..., help="Encrypted (.enc) file."),
    out: str = typer.Option("", "--out", help="Output path."),
) -> None:
    """Decrypt a file under your passphrase. 🔓"""
    from pathlib import Path
    from .security.vault import VaultError, VaultLocked, VaultUnavailable
    v = _open_vault()
    pw = typer.prompt("Owner passphrase", hide_input=True)
    try:
        dest = v.decrypt_file(Path(path).expanduser(), pw,
                              dest=Path(out).expanduser() if out else None)
    except (VaultLocked, VaultUnavailable, VaultError) as e:
        _die(ExitCode.ERROR, str(e))
    if STATE.json_out:
        _emit_json({"ok": True, "decrypted": str(dest)}); raise typer.Exit(ExitCode.OK)
    _print(f"🔓 decrypted → {dest}")


@vault_app.command("rotate")
def vault_rotate_cmd(
    files: list[str] = typer.Option([], "--file",
        help="Encrypted file to re-key (repeatable)."),
) -> None:
    """Change the owner passphrase; re-encrypt any --file under the new key."""
    from pathlib import Path
    from .security.vault import VaultError, VaultLocked
    v = _open_vault()
    if not v.is_initialized:
        _die(ExitCode.USAGE, "vault not initialized", hint="run `sov vault init`")
    old = typer.prompt("Current passphrase", hide_input=True)
    new = typer.prompt("New passphrase", hide_input=True, confirmation_prompt=True)
    try:
        rewritten = v.rotate(old, new,
                             files=tuple(Path(f).expanduser() for f in files))
    except (VaultLocked, VaultError) as e:
        _die(ExitCode.ERROR, str(e))
    if STATE.json_out:
        _emit_json({"ok": True, "rekeyed": [str(p) for p in rewritten]})
        raise typer.Exit(ExitCode.OK)
    _print("🔁 [green]passphrase rotated.[/green]")
    for p in rewritten:
        _print(f"   re-encrypted: {p}")


app.add_typer(vault_app, name="vault")


