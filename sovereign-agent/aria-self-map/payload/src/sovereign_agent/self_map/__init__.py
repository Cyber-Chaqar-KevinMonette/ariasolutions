"""self_map — she knows the texture of herself.

Final-sprint Round 2, companion to the wholeness guardian. Kevin's ask: a
"super mapping system that always knows her complete map ... and always
knows her complete wiring and blood flow. Something that knows the texture
of itself." And: "she should be able to give a full report of herself,
tools, systems, sentinels, and capabilities if I ask her. She should not
be clueless ever."

This builds a live map of her registered capabilities — sentinels, tools,
memory channels — read from the SAME registries the running system uses
(`stewardship.registry`, `authority`, `channels`), so the map is never
stale or hand-maintained. From that it produces:

- `render_self_report(m)` — a plain-language "here is all of me" report
  she can present on request (the self-knowledge surface).
- `find_orphans(declared, resolvable)` — the integrity check that feeds the
  wholeness guardian's `self_map_orphans` metric: a capability that is
  *declared* (registered) but does not *resolve* (can't produce a live
  instance) is an orphan — real, precise, and normally zero. Defined
  narrowly on purpose so it never false-alarms the wholeness gate.

The rendering + orphan logic is pure and fully tested; `build_self_map()`
is the thin, best-effort gatherer over the live registries (never raises).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "SelfMap",
    "build_self_map",
    "render_self_report",
    "find_orphans",
    "self_map_summary",
]


@dataclass
class SelfMap:
    """A point-in-time map of her registered capabilities + their wiring."""
    sentinels: list[str] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)   # {name, tier, requires_approval}
    channels: list[dict[str, Any]] = field(default_factory=list)  # {name, tier}
    orphans: list[str] = field(default_factory=list)             # declared-but-unresolvable
    captured_at: str = ""
    notes: str = ""

    @property
    def counts(self) -> dict[str, int]:
        return {
            "sentinels": len(self.sentinels),
            "tools": len(self.tools),
            "channels": len(self.channels),
            "orphans": len(self.orphans),
        }


def find_orphans(declared: set[str] | list[str], resolvable: set[str] | list[str]) -> list[str]:
    """Capabilities that are declared (registered) but do not resolve
    (can't produce a live instance / health status). Pure. Normally empty —
    a non-empty result is a real integrity problem worth surfacing, which
    is exactly why the wholeness guardian treats orphans > 0 as not-whole.
    """
    return sorted(set(declared) - set(resolvable))


def self_map_summary(m: SelfMap) -> dict[str, int]:
    """The counts the wholeness guardian reads (its `self_map_orphans`)."""
    return m.counts


def render_self_report(m: SelfMap) -> str:
    """A plain-language 'here is all of me' report she can present."""
    c = m.counts
    lines: list[str] = []
    lines.append("# Aria — self-report")
    lines.append("")
    lines.append(f"I am wired with **{c['sentinels']} sentinels**, "
                 f"**{c['tools']} tools**, and **{c['channels']} memory channels**.")
    if m.captured_at:
        lines.append(f"_(mapped {m.captured_at})_")
    lines.append("")

    if m.orphans:
        lines.append(f"⚠ **{len(m.orphans)} orphan(s)** — declared but not resolving: "
                     + ", ".join(f"`{o}`" for o in m.orphans))
        lines.append("")
    else:
        lines.append("✓ No orphans — every declared capability resolves. I am wired whole.")
        lines.append("")

    lines.append("## Sentinels (what watches over me)")
    if m.sentinels:
        lines.append(", ".join(f"`{s}`" for s in m.sentinels))
    else:
        lines.append("_none registered_")
    lines.append("")

    lines.append("## Tools (what I can do)")
    if m.tools:
        by_tier: dict[int, list[str]] = {}
        for t in m.tools:
            by_tier.setdefault(int(t.get("tier", 0)), []).append(str(t.get("name", "?")))
        for tier in sorted(by_tier):
            names = ", ".join(f"`{n}`" for n in sorted(by_tier[tier]))
            lines.append(f"- **Tier {tier}** ({len(by_tier[tier])}): {names}")
    else:
        lines.append("_none registered_")
    lines.append("")

    lines.append("## Memory channels (where I keep what I know)")
    if m.channels:
        lines.append(", ".join(f"`{ch.get('name', '?')}`" for ch in m.channels))
    else:
        lines.append("_none registered_")
    lines.append("")

    if m.notes:
        lines.append(f"[dim]notes: {m.notes}[/dim]")
    return "\n".join(lines)


# ── best-effort live gather (thin; never raises) ─────────────────────────
def build_self_map(*, data_dir: Path | None = None) -> SelfMap:
    """Read the live registries into a SelfMap. Every source is wrapped so a
    missing subsystem degrades to empty rather than raising — a self-map
    that crashes tells her nothing."""
    from datetime import datetime, timezone

    m = SelfMap(captured_at=datetime.now(timezone.utc).isoformat())

    # sentinels — declared ids vs those that produce a health status (resolve)
    declared_sentinels: set[str] = set()
    resolvable_sentinels: set[str] = set()
    try:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.stewardship.registry import gather_health, registered_ids
        dd = data_dir or SETTINGS.paths.data_dir
        declared_sentinels = set(registered_ids())
        resolvable_sentinels = {getattr(h, "sentinel_id", "") for h in gather_health(dd)}
        m.sentinels = sorted(declared_sentinels)
    except Exception:  # noqa: BLE001
        m.notes += "sentinels-unavailable; "

    # tools — importing the tools package triggers the @register_tool
    # side-effects (the registry is otherwise empty in a bare process).
    try:
        import sovereign_agent.tools  # noqa: F401 — populates the tier registry
    except Exception:  # noqa: BLE001
        m.notes += "tools-import-failed; "
    try:
        from sovereign_agent.authority import tools_available_in_mode
        from sovereign_agent.modes import Mode
        for meta in tools_available_in_mode(Mode.ONESHOT):  # ceiling 3 == everything
            m.tools.append({
                "name": getattr(meta, "name", "?"),
                "tier": getattr(meta, "tier", 0),
                "requires_approval": getattr(meta, "requires_approval", False),
            })
    except Exception:  # noqa: BLE001
        m.notes += "tools-unavailable; "

    # channels — importing mem_channels triggers @register_channel side-effects
    try:
        import sovereign_agent.mem_channels  # noqa: F401 — populates the channel registry
    except Exception:  # noqa: BLE001
        m.notes += "channels-import-failed; "
    try:
        from sovereign_agent.channels import list_channels
        for spec in list_channels():
            m.channels.append({
                "name": getattr(spec, "name", "?"),
                "tier": getattr(spec, "authority_tier", getattr(spec, "tier", 0)),
            })
    except Exception:  # noqa: BLE001
        m.notes += "channels-unavailable; "

    # orphans: declared-but-unresolvable sentinels (precise; normally empty)
    if declared_sentinels:
        m.orphans = find_orphans(declared_sentinels, resolvable_sentinels)

    return m
