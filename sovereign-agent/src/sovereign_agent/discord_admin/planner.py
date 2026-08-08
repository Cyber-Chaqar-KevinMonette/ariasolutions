"""planner — turn a blueprint into an ordered, idempotent action list.

Given the desired blueprint and a snapshot of what already exists, produce the
minimal ordered set of Discord actions to reach it. Two guarantees:

  • **Idempotent** — anything that already exists (by name) is skipped, so
    running `/setup-shop` twice is safe and only fills gaps.
  • **Create-only, never destroys** — the planner emits create/overwrite
    actions only. It will never delete a channel, role, or category. Tearing
    anything down is a separate, explicitly-confirmed command (see gate.py).

Order matters: roles first (channels reference them), then categories, then
channels, then the permission overwrites.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .blueprint import SEND, VIEW, CategorySpec, ServerBlueprint, canon_name

__all__ = ["Action", "CurrentState", "plan", "render_plan"]


@dataclass
class Action:
    op: str                      # create_role | create_category | create_channel | overwrite
    name: str
    params: dict = field(default_factory=dict)

    def describe(self) -> str:
        p = self.params
        if self.op == "create_role":
            return f"＋ role  @{self.name}  ({p.get('color', 'default')})"
        if self.op == "create_category":
            return f"＋ category  {self.name}"
        if self.op == "create_channel":
            return f"＋ channel  #{self.name}  → {p.get('category', '?')}"
        if self.op == "overwrite":
            allow = "+".join(p.get("allow", [])) or "—"
            deny = "+".join(p.get("deny", [])) or "—"
            return (f"⚙ perms  {p.get('scope')}:{self.name} · {p.get('target')}"
                    f"  allow[{allow}] deny[{deny}]")
        return f"{self.op} {self.name}"


@dataclass
class CurrentState:
    """A snapshot of what already exists in the guild (by name)."""
    roles: set[str] = field(default_factory=set)
    categories: set[str] = field(default_factory=set)
    channels: set[str] = field(default_factory=set)


def _overwrites_for_category(cat: CategorySpec) -> list[Action]:
    out: list[Action] = []
    if cat.private:
        out.append(Action("overwrite", cat.name,
                          {"scope": "category", "target": "@everyone", "deny": [VIEW]}))
        for role in cat.allow_roles:
            out.append(Action("overwrite", cat.name,
                              {"scope": "category", "target": role, "allow": [VIEW]}))
    else:
        allow = [VIEW] if cat.read_only else [VIEW, SEND]
        deny = [SEND] if cat.read_only else []
        out.append(Action("overwrite", cat.name,
                          {"scope": "category", "target": "@everyone",
                           "allow": allow, "deny": deny}))
    for ch in cat.channels:
        if ch.private:
            out.append(Action("overwrite", ch.name,
                              {"scope": "channel", "target": "@everyone", "deny": [VIEW]}))
            for role in ch.allow_roles:
                out.append(Action("overwrite", ch.name,
                                  {"scope": "channel", "target": role, "allow": [VIEW]}))
        if ch.allow_send_everyone:
            out.append(Action("overwrite", ch.name,
                              {"scope": "channel", "target": "@everyone", "allow": [SEND]}))
        for role in ch.hide_from:
            out.append(Action("overwrite", ch.name,
                              {"scope": "channel", "target": role, "deny": [VIEW]}))
    return out


def plan(bp: ServerBlueprint, current: CurrentState | None = None) -> list[Action]:
    current = current or CurrentState()
    actions: list[Action] = []
    # existing things match by CANONICAL name — "🛒 SHOP" IS "SHOP"
    # (decoration is cosmetic, never drift; see blueprint.canon_name)
    have_roles = {canon_name(n) for n in current.roles}
    have_cats = {canon_name(n) for n in current.categories}
    have_chans = {canon_name(n) for n in current.channels}

    # 1) roles (skip existing)
    for r in bp.roles:
        if canon_name(r.name) not in have_roles:
            actions.append(Action("create_role", r.name,
                                  {"color": r.color, "color_int": r.color_int,
                                   "hoist": r.hoist}))
    # 2) categories + 3) channels (skip existing)
    for cat in bp.categories:
        if canon_name(cat.name) not in have_cats:
            actions.append(Action("create_category", cat.name, {}))
        for ch in cat.channels:
            if canon_name(ch.name) not in have_chans:
                actions.append(Action("create_channel", ch.name,
                                      {"category": cat.name, "kind": ch.kind,
                                       "topic": ch.topic,
                                       "age_restricted": ch.age_restricted}))
    # 4) permission overwrites (idempotent to re-apply; always emitted)
    for cat in bp.categories:
        actions.extend(_overwrites_for_category(cat))
    return actions


def render_plan(actions: list[Action]) -> str:
    if not actions:
        return "Nothing to do — the server already matches the blueprint. ✅"
    creates = [a for a in actions if a.op.startswith("create")]
    perms = [a for a in actions if a.op == "overwrite"]
    lines = [f"Plan: {len(creates)} thing(s) to create, {len(perms)} permission "
             f"rule(s) to apply. [dim](create-only — nothing is deleted)[/dim]"]
    for a in creates:
        lines.append("  " + a.describe())
    if perms:
        lines.append("  [dim]— permissions —[/dim]")
        for a in perms:
            lines.append("  " + a.describe())
    return "\n".join(lines)
