"""cockpit/run_surface.py — payload-aware event rendering + live run state.

THE GAP THIS CLOSES (Keys round K1, researched 2026-07-04): the cockpit's
`_render_event` discarded the payload for ~80 event types — a running
session/workflow showed its steps, subtasks, budgets, and completions as
bare flag names scrolling past; failure events (`-x`) rendered WHITE; and
there was no live surface at all answering "what is she doing right now,
how far along, is the run healthy?"

Two pieces, both fed by the cockpit's EXISTING 1s events tailer (no second
tailer — the same lesson the atelier learned):

  1. `render_rich_event(ev)` — a renderer registry by event family
     (session-*, subtask-*, workflow-step-*, prompt-diet-d, ingest-skip-x,
     qa-*). Returns a formatted Rich markup line, or None to fall through
     to the generic renderer exactly as before. Unknown flags are
     untouched by design.

  2. `RunState` — a tiny cross-event tracker (goal from ingest-d, subtask
     progress, token totals from token-usage-d, breaker state from
     circuit-open-x, completion). Everything comes through events.jsonl
     because the loop usually runs in a SEPARATE process (`sov run`
     subprocess) — the cockpit can never read its in-process registries;
     the event stream is the one honest cross-process window.

`is_failure_flag` backs the `-x`-renders-red fix in `_render_event`.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def is_failure_flag(flag: str) -> bool:
    return flag.endswith("-x")


def _p(ev: dict) -> dict:
    payload = ev.get("payload")
    return payload if isinstance(payload, dict) else {}


# ─── Rich rendering per event family ──────────────────────────────────────


def render_rich_event(ev: dict) -> str | None:
    """A Rich-markup line for known event families, else None (caller
    falls through to the generic flag renderer, byte-for-byte as before)."""
    flag = ev.get("flag", "")
    p = _p(ev)
    try:
        if flag == "session-start-d":
            pending = p.get("subtasks_pending", "?")
            return f"[bold cyan]◊ session start[/bold cyan] [dim]· {pending} subtask(s) pending[/dim]"
        if flag == "session-complete-d":
            done, total = p.get("done", "?"), p.get("total", "?")
            return f"[bold green]◊ session complete[/bold green] · {done}/{total} subtasks"
        if flag == "session-budget-d":
            return (f"[yellow]◊ budget {p.get('kind', '?')}:[/yellow] "
                    f"{p.get('used', '?')}/{p.get('limit', '?')}")
        if flag == "subtask-start-d":
            desc = str(p.get("description", ""))[:70]
            return f"[cyan]▸ subtask[/cyan] T{p.get('tier', '?')} · {desc}"
        if flag == "subtask-done-d":
            summary = str(p.get("summary", ""))[:70]
            return (f"[green]✓ subtask[/green] · {p.get('iterations', '?')} iter · "
                    f"{p.get('tokens', '?')}t{' · ' + summary if summary else ''}")
        if flag == "subtask-blocked-d":
            return f"[red]✗ subtask blocked[/red] · {str(p.get('reason', p.get('error', '')))[:80]}"
        if flag == "workflow-step-start-d":
            return (f"[cyan]▸ step[/cyan] {str(p.get('title', ''))[:60]} "
                    f"[dim]({p.get('action_kind', '?')})[/dim]")
        if flag == "workflow-step-done-d":
            return f"[green]✓ step[/green] {str(p.get('title', ''))[:60]}"
        if flag == "workflow-step-blocked-d":
            return (f"[red]✗ step blocked[/red] {str(p.get('title', ''))[:50]} · "
                    f"{str(p.get('error', ''))[:60]}")
        if flag == "prompt-diet-d":
            return (f"[dim]⌁ diet: tools {p.get('tools_sent', '?')}/"
                    f"{p.get('tools_registered', '?')} · prompt "
                    f"{p.get('prompt_chars', '?')}c[/dim]")
        if flag == "ingest-skip-x":
            return (f"[red]✗ ingest skipped {p.get('skipped_corrupt_lines', '?')} "
                    f"corrupt line(s)[/red]")
        if flag == "circuit-open-x":
            return f"[red]✗ circuit OPEN[/red] · tool {p.get('tool', '?')}"
        if flag == "scope-review-d":  # scope-contract-d
            return (f"[yellow]◊ scope review:[/yellow] held — "
                    f"{str(p.get('description', ''))[:70]}")
        if flag == "scope-drift-d":  # scope-contract-d
            return (f"[yellow]◊ scope drift:[/yellow] {p.get('subtasks', '?')}/"
                    f"{p.get('max', '?')} subtasks — nearing the contract ceiling")
        if flag == "workflow-designed-d":  # workflow-champion-d
            return (f"[cyan]◊ designed:[/cyan] {str(p.get('title', ''))[:50]} "
                    f"[dim]({p.get('steps', '?')} steps — review + /work to run)[/dim]")
        if flag == "qa-start-d":
            return f"[magenta]? wondering:[/magenta] {str(p.get('question', ''))[:80]}"
        if flag == "qa-d":
            return (f"[magenta]◊ Q&A[/magenta] {str(p.get('question', ''))[:50]} "
                    f"[dim]→ {str(p.get('answer', ''))[:60]}[/dim]")
    except Exception:  # noqa: BLE001 — a rendering bug must never break the tailer
        return None
    return None


# ─── Cross-event run state ────────────────────────────────────────────────


@dataclass
class RunState:
    """What she's doing right now, distilled from the event stream."""

    active: bool = False
    goal: str = ""
    mode: str = ""
    subtasks_done: int = 0
    subtasks_seen: int = 0
    current_subtask: str = ""
    tokens: int = 0
    tok_s: float = 0.0  # token-speed-d — latest per-call throughput
    breaker_open_tool: str = ""
    last_flag: str = ""
    last_ts: str = ""
    outcome: str = ""
    _extra: dict = field(default_factory=dict)

    def ingest(self, ev: dict) -> None:
        """Feed one event. Never raises — the tailer must survive anything."""
        try:
            flag = ev.get("flag", "")
            p = _p(ev)
            self.last_flag = flag
            self.last_ts = ev.get("ts", "")[11:19]
            if flag == "ingest-d":
                self.active = True
                self.outcome = ""
                self.goal = str(p.get("goal", ""))[:120]
                self.mode = str(p.get("mode", ""))
                self.subtasks_done = 0
                self.subtasks_seen = 0
                self.current_subtask = ""
                self.tokens = 0
                self.tok_s = 0.0
                self.breaker_open_tool = ""
            elif flag == "session-start-d":
                self.active = True
                self.outcome = ""
            elif flag == "subtask-start-d":
                self.subtasks_seen += 1
                self.current_subtask = str(p.get("description", ""))[:80]
            elif flag == "subtask-done-d":
                self.subtasks_done += 1
                self.current_subtask = ""
            elif flag == "token-usage-d":
                self.tokens = int(p.get("running_total", self.tokens) or 0)
                self.tok_s = float(p.get("tok_s", 0.0) or 0.0)
            elif flag == "circuit-open-x":
                self.breaker_open_tool = str(p.get("tool", "?"))
            elif flag == "session-complete-d":
                self.active = False
                self.outcome = f"complete {p.get('done', '?')}/{p.get('total', '?')}"
            elif flag in ("settle-d", "trace-end-d") and self.mode:
                # A plain agent_loop run (no session wrapper) settles here.
                self.active = False
                if flag == "settle-d":
                    self.outcome = "settled"
            elif flag == "halted-d":
                self.active = False
                self.outcome = "HALTED"
        except Exception:  # noqa: BLE001
            pass

    def render_strip(self) -> str:
        """One status line for the run strip. Rich markup."""
        if self.breaker_open_tool:
            breaker = f"  [red]⛒ {self.breaker_open_tool}[/red]"
        else:
            breaker = ""
        if self.active:
            progress = ""
            if self.subtasks_seen:
                progress = f" · {self.subtasks_done}/{self.subtasks_seen}✓"
            current = f" · {self.current_subtask[:40]}" if self.current_subtask else ""
            tokens = f" · {self.tokens}t" if self.tokens else ""
            return (f"[bold cyan]◊ run[/bold cyan] {self.goal[:44]}"
                    f"{progress}{current}{tokens}{breaker}")
        if self.outcome:
            color = "red" if "HALT" in self.outcome else "green"
            return f"[{color}]◊ {self.outcome}[/{color}] [dim]{self.goal[:40]}[/dim]{breaker}"
        return f"[b]◊ no run active[/b]{breaker}"

    def render_pane(self) -> str:
        """Multi-line detail for a dedicated run pane (K2's layout rows)."""
        lines = [self.render_strip()]
        if self.active or self.outcome:
            if self.mode:
                lines.append(f"[dim]mode:[/dim] {self.mode}")
            if self.current_subtask:
                lines.append(f"[dim]now:[/dim] {self.current_subtask}")
            lines.append(f"[dim]last:[/dim] {self.last_flag} @ {self.last_ts}")
        return "\n".join(lines)

    def render_token_strip(self) -> str:
        """token-speed-d (Kevin, 2026-07-21): "add a token counter to
        observability so I can always watch the token speed and session
        token total." A dedicated, always-visible strip -- separate from
        render_strip()'s goal/progress line, which only carries a token
        count inline and disappears entirely when no run is active."""
        # label-contrast-d (Kevin, 2026-07-25): the label was [dim] on
        # BOTH lines -- easy to read as an empty box at a glance. Bold
        # label, dim only the "nothing yet" detail.
        if not self.tok_s and not self.tokens:
            return "[b]◊ tokens[/b]\n[dim](none yet)[/dim]"
        return f"[b]◊ tokens[/b]\n{self.tok_s:.1f} tok/s · {self.tokens}t session"
