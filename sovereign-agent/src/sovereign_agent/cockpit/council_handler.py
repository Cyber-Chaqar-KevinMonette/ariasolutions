"""cockpit/council_handler.py — Cockpit handlers for /council and /globe.

Lets Kevin consult the non-classical globe council and see the globe, live, from the cockpit.
Advisory only — the council offers a read; Kevin decides. Pure-Python, no side effects.
"""
from __future__ import annotations


def globe_text() -> str:
    """Render the 13-node globe as text (the ascii view + a one-line summary)."""
    try:
        from sovereign_agent.quantum.globe import Globe
        g = Globe()
        g.encode_all(0.4)
        g.step()
        g.decohere_all(0.03)
        return g.ascii_view()
    except Exception as exc:  # noqa: BLE001
        return f"[yellow]globe unavailable: {exc!r}[/yellow]"


def consult_text(question: str) -> str:
    """Consult the globe council on a question; return a formatted advisory read."""
    q = (question or "").strip()
    if not q:
        return "[yellow]usage: /council <question>[/yellow]"
    try:
        from sovereign_agent.quantum.council import consult_council
        r = consult_council(q, steps=2)
    except Exception as exc:  # noqa: BLE001
        return f"[yellow]council unavailable: {exc!r}[/yellow]"

    lean = r["lean"]
    colour = {"yes": "green", "no": "red", "split": "yellow"}.get(lean, "white")
    lines = [
        f"[bold]✦ The council on:[/bold] [italic]{q}[/italic]",
        f"  lean: [{colour}]{lean.upper()}[/{colour}]  ·  disposition {r['disposition']:.2f}  "
        f"·  mode {r['coherence_mode']['band']}  ·  self-coherence {r['self_coherence']:.2f}",
    ]
    # show a few of the most decisive voices
    voices = sorted(r["council_voices"], key=lambda v: abs(v["lean_yes"] - 0.5), reverse=True)
    for v in voices[:5]:
        lines.append(f"    [dim]{v['node']:8}[/dim] ({v['family']}) [italic]{v['tone']}[/italic]: {v['voice']}")
        reg = v.get("register")
        if reg:
            lines.append(f"             [dim]↳ {reg}[/dim]")
    lines.append("  [dim]Advisory only — the council offers its read; you decide.[/dim]")
    return "\n".join(lines)
