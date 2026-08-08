"""gate — the safety rules for the admin bot. Powerful tool, tight leash.

An admin bot that can edit channels, roles, and permissions is genuinely
powerful, so every command passes this gate first:

  • **Owner-only** — only the configured owner (you) may run admin commands.
    Everyone else is refused, no matter what they type.
  • **Destructive actions need explicit confirmation** — deletes and mass
    permission wipes never happen on a single word; they require `confirm=True`.
  • **The auto-setup is create-only** (see planner.py), so the common path
    (`/setup-shop`) can only build/repair — it can't tear anything down.

Pure + deterministic so the rules are unit-tested, not just trusted.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "DESTRUCTIVE_OPS",
    "is_owner",
    "is_destructive",
    "needs_confirmation",
    "GateResult",
    "check_command",
]

# ops that change/remove existing structure irreversibly
DESTRUCTIVE_OPS = {"delete_role", "delete_category", "delete_channel", "wipe_permissions"}


def is_owner(user_id: int | str | None, owner_id: int | str | None) -> bool:
    """True only if the caller is the configured owner. Missing/blank → False
    (fail closed — no owner configured means nobody is trusted)."""
    if user_id is None or owner_id is None:
        return False
    return str(user_id).strip() == str(owner_id).strip() and str(owner_id).strip() != ""


def is_destructive(op: str) -> bool:
    return op in DESTRUCTIVE_OPS


def needs_confirmation(actions) -> bool:
    """Any destructive action in the batch forces an explicit confirm."""
    return any(is_destructive(getattr(a, "op", a)) for a in actions)


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    reason: str = ""


def check_command(*, user_id, owner_id, op: str, confirm: bool = False) -> GateResult:
    """The single decision point every admin command calls before acting."""
    if not is_owner(user_id, owner_id):
        return GateResult(False, "admin commands are owner-only")
    if is_destructive(op) and not confirm:
        return GateResult(False, f"'{op}' is destructive — re-run with confirm=true")
    return GateResult(True, "ok")
