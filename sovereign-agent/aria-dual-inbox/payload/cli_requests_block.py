requests_app = typer.Typer(
    help="📬 Collaboration inbox — Aria's asks and your answers, with context.",
    invoke_without_command=True)


def _render_requests(items, *, detail: bool = False, header: str | None = None) -> None:
    from rich.markup import escape
    if STATE.json_out:
        _emit_json([{"id": r.request_id, "short": r.short_id, "kind": r.kind,
                     "title": r.title, "body": r.body, "status": r.status,
                     "priority": r.priority, "tags": r.tags,
                     "rationale": r.rationale, "revisit_when": r.revisit_when,
                     "revisit_at": r.revisit_at, "estimate": r.estimate,
                     "due": r.is_due, "answer": r.answer,
                     "workflow_id": r.workflow_id, "created_at": r.created_at,
                     "direction": r.direction}
                    for r in items])
        return
    if header:
        _print(header)
    if not items:
        _print("📭 [dim]nothing here — inbox clear[/dim]")
        return
    for r in items:
        due = "  [red]● due[/red]" if r.is_due else ""
        _print(escape_one_line(r) + due)
        if detail:
            for line in r.context_lines():
                _print(f"      [dim]{escape(line)}[/dim]")
        else:
            bits = []
            if r.rationale:
                bits.append(f"why: {r.rationale}")
            if r.revisit_when:
                bits.append(f"when: {r.revisit_when}")
            if r.tags:
                bits.append(" ".join(f"#{t}" for t in r.tags))
            if bits:
                _print("      [dim]" + escape(" · ".join(bits)) + "[/dim]")


def escape_one_line(r) -> str:
    """one_line() but with the title markup-escaped for safe console output."""
    from rich.markup import escape
    pri = f"{r.priority_emoji} " if r.priority != "normal" else ""
    return f"{r.status_emoji} {r.emoji} {pri}[{r.short_id}] {escape(r.title)}"


@requests_app.callback()
def requests_main(ctx: typer.Context) -> None:
    """With no subcommand, show what's open FOR YOU (to_human), most urgent
    first. Aria's own inbox is a separate view — `sov requests --direction
    to_aria` or `sov aria-inbox` — so the two never get mixed together. 🟡"""
    if ctx.invoked_subcommand is not None:
        return
    rs = _open_request_store()
    from sovereign_agent.workflow.requests import DIRECTION_TO_HUMAN
    _render_requests(rs.list_open(direction=DIRECTION_TO_HUMAN))


@requests_app.command("list")
def requests_list_cmd(
    all_: bool = typer.Option(False, "--all", "-a", help="Include resolved/answered/parked."),
    status: str = typer.Option("", "--status", help="open|answered|resolved|cancelled|deferred|needs_attention|revisit"),
    kind: str = typer.Option("", "--kind", "-k", help="Filter by kind."),
    tag: str = typer.Option("", "--tag", "-t", help="Filter by tag."),
    direction: str = typer.Option("to_human", "--direction", help="to_human|to_aria|all — which inbox to read."),
    detail: bool = typer.Option(False, "--detail", "-d", help="Show full context per item."),
) -> None:
    """List requests (filterable by status, kind, tag, direction). Defaults
    to YOUR inbox (to_human) — pass --direction to_aria to see what's been
    left for her, or --direction all to see both together."""
    rs = _open_request_store()
    dir_filter = None if direction == "all" else direction
    if status:
        items = rs.list(status=status, kind=kind or None, tag=tag or None, direction=dir_filter)
    elif all_ or kind or tag:
        items = rs.list(kind=kind or None, tag=tag or None, direction=dir_filter)
    else:
        items = rs.list_open(direction=dir_filter)
    _render_requests(items, detail=detail)


@requests_app.command("ask")
def requests_ask_cmd(
    title: str = typer.Argument(..., help="Short summary — the WHAT."),
    kind: str = typer.Option("question", "--kind", "-k",
        help="question|scan_files|suggestion|approval|decision|blocker|research|note|celebrate"),
    body: str = typer.Option("", "--body", "-b", help="Longer detail."),
    why: str = typer.Option("", "--why", help="The WHY — reasoning behind it."),
    when: str = typer.Option("", "--when", help="The WHEN — a date, phase, or condition."),
    revisit_at: str = typer.Option("", "--revisit-at", help="ISO datetime to surface as 'due'."),
    priority: str = typer.Option("normal", "--priority", "-p", help="low|normal|high|urgent."),
    estimate: str = typer.Option("", "--estimate", "-e", help="Effort / prediction."),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Tag (repeatable)."),
) -> None:
    """File a request with full context. Aria, a script, or you can use this."""
    rs = _open_request_store()
    req = rs.open(kind, title, body=body, rationale=why, revisit_when=when,
                  revisit_at=revisit_at, priority=priority, estimate=estimate,
                  tags=list(tag))
    if STATE.json_out:
        _emit_json({"ok": True, "id": req.request_id, "short": req.short_id})
        raise typer.Exit(ExitCode.OK)
    _print(f"{req.emoji} filed [{req.short_id}] — {req.title}")
    for line in req.context_lines():
        _print(f"   [dim]{line}[/dim]")


@requests_app.command("tell")
def requests_tell_cmd(
    title: str = typer.Argument(..., help="Short summary — what you want her to see."),
    body: str = typer.Option("", "--body", "-b", help="Longer detail."),
    priority: str = typer.Option("normal", "--priority", "-p", help="low|normal|high|urgent."),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Tag (repeatable)."),
) -> None:
    """Leave a note FOR ARIA — the reverse direction. She reads this at a
    safe checkpoint (session start, or right after resuming from a paused
    autonomy interval), never mid-task. 📮"""
    rs = _open_request_store()
    req = rs.tell_aria(title, body=body, priority=priority, tags=list(tag))
    if STATE.json_out:
        _emit_json({"ok": True, "id": req.request_id, "short": req.short_id})
        raise typer.Exit(ExitCode.OK)
    _print(f"📮 left for Aria [{req.short_id}] — {req.title}")


@requests_app.command("show")
def requests_show_cmd(request_id: str = typer.Argument(..., help="Full or short id.")) -> None:
    """Show one request in full — what, why, when, and everything attached."""
    from rich.markup import escape
    rs = _open_request_store()
    r = rs.get(request_id)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json(r.__dict__); raise typer.Exit(ExitCode.OK)
    pri = f"  {r.priority_emoji} {r.priority}" if r.priority != "normal" else ""
    body = (f"{r.emoji} [bold]{escape(r.title)}[/bold]{pri}\n"
            f"[dim]id:[/dim] {r.request_id}\n"
            f"[dim]kind:[/dim] {r.kind}   [dim]status:[/dim] {r.status_emoji} {r.status}"
            + ("  [red]● due[/red]" if r.is_due else "") + "\n"
            f"[dim]direction:[/dim] {r.direction}\n"
            f"[dim]created:[/dim] {r.created_at}\n")
    if r.workflow_id:
        body += f"[dim]workflow:[/dim] {r.workflow_id}\n"
    if r.body:
        body += f"\n[bold]what:[/bold] {escape(r.body)}\n"
    if r.rationale:
        body += f"[bold]why:[/bold] {escape(r.rationale)}\n"
    if r.revisit_when:
        body += f"[bold]when:[/bold] {escape(r.revisit_when)}"
        if r.revisit_at:
            body += f"  [dim](at {escape(r.revisit_at)})[/dim]"
        body += "\n"
    if r.estimate:
        body += f"[bold]estimate:[/bold] {escape(r.estimate)}\n"
    if r.tags:
        body += "[bold]tags:[/bold] " + " ".join(f"#{escape(t)}" for t in r.tags) + "\n"
    if r.answer:
        body += f"\n[green]your answer:[/green] {escape(r.answer)}\n"
    _print(Panel(body, title=f"📨 request {r.short_id}", border_style="cyan"))


@requests_app.command("next")
def requests_next_cmd() -> None:
    """Show the single most pressing open request — your 'what's next'. 👉"""
    rs = _open_request_store()
    r = rs.next_open()
    if r is None:
        if STATE.json_out:
            _emit_json({"next": None}); raise typer.Exit(ExitCode.OK)
        _print("📭 [dim]nothing open — you're all caught up[/dim]")
        raise typer.Exit(ExitCode.OK)
    requests_show_cmd(r.request_id)
    if not STATE.json_out:
        _print(f"\n[dim]answer it:[/dim] sov requests answer {r.short_id} \"...\"")


@requests_app.command("answer")
def requests_answer_cmd(
    request_id: str = typer.Argument(..., help="Full or short id."),
    text: str = typer.Argument(None, help="Your answer (omit to be prompted)."),
) -> None:
    """Answer a request. Omit the text and you'll be prompted. 🟢"""
    rs = _open_request_store()
    if text is None and not STATE.json_out:
        text = typer.prompt("Your answer")
    if not text:
        _die(ExitCode.USAGE, "no answer text given")
    r = rs.answer(request_id, text)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json({"ok": True, "id": r.request_id, "status": r.status})
        raise typer.Exit(ExitCode.OK)
    _print(f"🟢 answered [{r.short_id}] — thanks, that unblocks her ✨")


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
    _print(f"✅ resolved [{r.short_id}] — onward 🚀")


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
    _print(f"⚪ cancelled [{r.short_id}]")


@requests_app.command("defer")
def requests_defer_cmd(
    request_id: str = typer.Argument(..., help="Full or short id."),
    why: str = typer.Option("", "--why", help="Why set it aside."),
    when: str = typer.Option("", "--when", help="When to come back (date/phase/condition)."),
    revisit_at: str = typer.Option("", "--revisit-at", help="ISO datetime to surface as 'due'."),
) -> None:
    """Set a request aside for now — with why + when. ⏸️"""
    rs = _open_request_store()
    r = rs.defer(request_id, why=why or None, when=when or None,
                 when_at=revisit_at or None)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json({"ok": True, "id": r.request_id, "status": r.status})
        raise typer.Exit(ExitCode.OK)
    _print(f"⏸️  deferred [{r.short_id}]" + (f" — when: {when}" if when else ""))


@requests_app.command("flag")
def requests_flag_cmd(
    request_id: str = typer.Argument(..., help="Full or short id."),
    why: str = typer.Option("", "--why", help="Why it needs attention."),
) -> None:
    """Flag a request as needing more attention. ⚠️"""
    rs = _open_request_store()
    r = rs.flag(request_id, why=why or None)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json({"ok": True, "id": r.request_id, "status": r.status})
        raise typer.Exit(ExitCode.OK)
    _print(f"⚠️  flagged [{r.short_id}] — needs more attention")


@requests_app.command("revisit")
def requests_revisit_cmd(
    request_id: str = typer.Argument(..., help="Full or short id."),
    why: str = typer.Option("", "--why", help="Why revisit later."),
    when: str = typer.Option("", "--when", help="When/which phase to revisit."),
    revisit_at: str = typer.Option("", "--revisit-at", help="ISO datetime to surface as 'due'."),
) -> None:
    """Mark a request to come back to after more development/research. 🔖"""
    rs = _open_request_store()
    r = rs.revisit(request_id, why=why or None, when=when or None,
                   when_at=revisit_at or None)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json({"ok": True, "id": r.request_id, "status": r.status})
        raise typer.Exit(ExitCode.OK)
    _print(f"🔖 will revisit [{r.short_id}]" + (f" — {when}" if when else ""))


@requests_app.command("reopen")
def requests_reopen_cmd(request_id: str = typer.Argument(..., help="Full or short id.")) -> None:
    """Bring a parked (deferred/revisit/flagged) request back to open. 🔁"""
    rs = _open_request_store()
    r = rs.reopen(request_id)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json({"ok": True, "id": r.request_id, "status": r.status})
        raise typer.Exit(ExitCode.OK)
    _print(f"🔁 reopened [{r.short_id}] — back on the open queue")


@requests_app.command("parked")
def requests_parked_cmd(
    detail: bool = typer.Option(False, "--detail", "-d", help="Show full context."),
) -> None:
    """Everything set aside to revisit — deferred ⏸️, revisit 🔖, flagged ⚠️.
    Due items (their time has come) sort to the top. `reopen <id>` to act."""
    rs = _open_request_store()
    _render_requests(rs.parked(), detail=detail,
                     header="[bold cyan]◊ parked — to revisit[/bold cyan]")


@requests_app.command("due")
def requests_due_cmd() -> None:
    """Parked items whose revisit time has arrived — ready to readdress. ⏰"""
    rs = _open_request_store()
    items = rs.due()
    if STATE.json_out:
        _render_requests(items); raise typer.Exit(ExitCode.OK)
    if not items:
        _print("⏰ [dim]nothing due — nothing scheduled has come up yet[/dim]")
        raise typer.Exit(ExitCode.OK)
    _render_requests(items, header="[bold yellow]⏰ due to revisit now[/bold yellow]")


app.add_typer(requests_app, name="requests")
