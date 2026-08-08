"""server_plan — the living server plan: scan, audit, and evolution detection.

Kevin's ask: Aria can scan the Discord server, see what's missing from the
plan, and the plan system "always updates when enhancements or changes are
going to happen." Three pieces, all pure and durable:

  1. **Snapshot** — what the server actually looks like (role/category/
     channel names), captured by the bot (`/scan-server`, and automatically
     on every connect) and persisted to
     `<data>/discord_admin/server_snapshot.json`. Atomic writes,
     corrupt-file resilient, works offline once captured.
  2. **Audit** — the diff between the snapshot and `blueprint.py` (the plan
     of record): what's MISSING (the bot should create it), what's EXTRA
     (fine — humans add things; never deleted, only named), and a coverage
     fraction. `render_audit` turns it into the human report.
  3. **Evolution detection** — the blueprint is fingerprinted (sha256 over
     its canonical JSON). Whenever ANY consumer consults the plan (bot
     connect, `/scan-server`, `sov discord-admin scan`), a changed
     fingerprint is detected and announced: "the server plan evolved —
     re-run /setup-shop". So every future enhancement to the blueprint is
     surfaced the moment it ships — nothing drifts silently, by
     construction. State: `<data>/discord_admin/plan_state.json`.

Robustness contract: nothing in this module raises past its boundary —
a corrupt snapshot/state file degrades to "never scanned", never a crash.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from .blueprint import ServerBlueprint, canon_name, shop_blueprint

__all__ = [
    "ServerSnapshot",
    "PlanAudit",
    "save_snapshot",
    "load_snapshot",
    "blueprint_fingerprint",
    "audit_snapshot",
    "render_audit",
    "render_orphans",
    "CLEANUP_CONFIRM_PHRASE",
    "check_plan_evolution",
]

# consolidation-d (Kevin, 2026-07-18): deleting channels is DESTRUCTIVE —
# /cleanup-orphans only acts when the owner types this exact phrase.
CLEANUP_CONFIRM_PHRASE = "DELETE ORPHANS"


# ── the snapshot: what the server actually looks like ────────────────────────
@dataclass(frozen=True)
class ServerSnapshot:
    roles: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    captured_at: float = 0.0
    guild_name: str = ""

    @property
    def age_s(self) -> float:
        return max(0.0, time.time() - self.captured_at)


def _snapshot_path(data_dir: Path) -> Path:
    return Path(data_dir) / "discord_admin" / "server_snapshot.json"


def _state_path(data_dir: Path) -> Path:
    return Path(data_dir) / "discord_admin" / "plan_state.json"


def _atomic_write(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with open(tmp, "r+", encoding="utf-8") as fh:
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
    except Exception:  # noqa: BLE001
        pass


def save_snapshot(data_dir: Path, *, roles: list[str], categories: list[str],
                  channels: list[str], guild_name: str = "",
                  now: float | None = None) -> ServerSnapshot:
    """Persist what the server looks like right now. Never raises."""
    now = time.time() if now is None else now
    snap = ServerSnapshot(
        roles=sorted({str(r)[:100] for r in roles}),
        categories=sorted({str(c)[:100] for c in categories}),
        channels=sorted({str(c)[:100] for c in channels}),
        captured_at=now, guild_name=str(guild_name)[:100])
    _atomic_write(_snapshot_path(data_dir), {
        "roles": snap.roles, "categories": snap.categories,
        "channels": snap.channels, "captured_at": snap.captured_at,
        "guild_name": snap.guild_name})
    return snap


def load_snapshot(data_dir: Path) -> ServerSnapshot | None:
    """The last captured snapshot, or None (corrupt file → None, no crash)."""
    try:
        raw = json.loads(_snapshot_path(data_dir).read_text(encoding="utf-8"))
        return ServerSnapshot(
            roles=[str(r) for r in raw.get("roles", [])],
            categories=[str(c) for c in raw.get("categories", [])],
            channels=[str(c) for c in raw.get("channels", [])],
            captured_at=float(raw.get("captured_at", 0.0)),
            guild_name=str(raw.get("guild_name", "")))
    except Exception:  # noqa: BLE001
        return None


# ── the plan fingerprint: enhancements can never drift silently ──────────────
def blueprint_fingerprint(bp: ServerBlueprint | None = None) -> str:
    """A stable sha256 over the blueprint's full canonical content — any
    enhancement (new channel, role, permission intent) changes it."""
    bp = bp or shop_blueprint()
    canon = {
        "roles": [{"name": r.name, "color": r.color, "hoist": r.hoist}
                  for r in bp.roles],
        "categories": [{
            "name": cat.name, "private": cat.private,
            "read_only": cat.read_only, "allow": sorted(cat.allow_roles),
            "channels": [{"name": ch.name, "kind": ch.kind,
                          "send_all": ch.allow_send_everyone,
                          "hide": sorted(ch.hide_from),
                          "private": ch.private,
                          "allow": sorted(ch.allow_roles)}
                         for ch in cat.channels],
        } for cat in bp.categories],
    }
    blob = json.dumps(canon, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ── the audit: what's missing, what's extra, how complete ────────────────────
@dataclass(frozen=True)
class PlanAudit:
    missing_roles: list[str]
    missing_categories: list[str]
    missing_channels: list[str]
    extra_roles: list[str]
    extra_categories: list[str]
    extra_channels: list[str]
    coverage: float                 # 0..1 — fraction of planned items present
    snapshot_age_s: float
    guild_name: str = ""

    @property
    def complete(self) -> bool:
        return not (self.missing_roles or self.missing_categories
                    or self.missing_channels)

    @property
    def missing_total(self) -> int:
        return (len(self.missing_roles) + len(self.missing_categories)
                + len(self.missing_channels))


# roles Discord/integrations manage themselves — never counted as "extra"
_HOUSE_ROLES = {"@everyone"}


def audit_snapshot(snap: ServerSnapshot,
                   bp: ServerBlueprint | None = None,
                   *, now: float | None = None) -> PlanAudit:
    """Pure diff: the plan vs what the server actually has."""
    bp = bp or shop_blueprint()
    now = time.time() if now is None else now

    def split(planned: list[str], have: list[str]) -> tuple[list[str], list[str], int]:
        """(missing planned names, extra real names, present count) —
        matched by CANONICAL name, so "🛒 SHOP" satisfies "SHOP"
        (decoration is cosmetic, never drift)."""
        have_canon = {canon_name(h) for h in have}
        planned_canon = {canon_name(p) for p in planned}
        missing = sorted(p for p in planned if canon_name(p) not in have_canon)
        extra = sorted(h for h in have if canon_name(h) not in planned_canon)
        return missing, extra, len(planned) - len(missing)

    have_roles = [r for r in snap.roles if r not in _HOUSE_ROLES]
    m_roles, x_roles, p_roles = split(bp.role_names(), have_roles)
    m_cats, x_cats, p_cats = split([c.name for c in bp.categories],
                                   snap.categories)
    # discord.py's guild.channels INCLUDES categories — drop those shadow
    # entries UNLESS the name is also a genuinely planned channel (the
    # blueprint has both a WELCOME category and a #welcome channel)
    cat_canon = {canon_name(c) for c in snap.categories}
    planned_chan_canon = {canon_name(c) for c in bp.channel_names()}
    have_chans = [c for c in snap.channels
                  if canon_name(c) not in cat_canon
                  or canon_name(c) in planned_chan_canon]
    m_chans, x_chans, p_chans = split(bp.channel_names(), have_chans)
    planned_total = (len(bp.role_names()) + len(bp.categories)
                     + len(bp.channel_names()))
    return PlanAudit(
        missing_roles=m_roles,
        missing_categories=m_cats,
        missing_channels=m_chans,
        extra_roles=x_roles,
        extra_categories=x_cats,
        extra_channels=x_chans,
        coverage=((p_roles + p_cats + p_chans) / planned_total)
        if planned_total else 1.0,
        snapshot_age_s=max(0.0, now - snap.captured_at),
        guild_name=snap.guild_name)


def render_audit(a: PlanAudit) -> str:
    """The human report — honest, specific, and calm about 'extra'."""
    head = f"🗺️ Server plan audit — {a.guild_name or 'the server'}"
    age = a.snapshot_age_s
    when = ("just now" if age < 90 else
            f"{age / 60:.0f} min ago" if age < 5400 else
            f"{age / 3600:.1f} h ago")
    lines = [head, f"  snapshot: {when} · plan coverage: {a.coverage:.0%}"]
    if a.complete:
        lines.append("  ✅ COMPLETE — every planned role, category, and "
                     "channel exists.")
    else:
        lines.append(f"  🔴 {a.missing_total} planned item(s) missing "
                     "(run /setup-shop or `sov discord-admin run` → it "
                     "creates ONLY what's missing):")
        for label, items in (("role", a.missing_roles),
                             ("category", a.missing_categories),
                             ("channel", a.missing_channels)):
            for name in items:
                lines.append(f"    + {label}: {name}")
    extras = (len(a.extra_roles) + len(a.extra_categories)
              + len(a.extra_channels))
    if extras:
        shown = (a.extra_channels + a.extra_categories + a.extra_roles)[:6]
        lines.append(f"  ℹ️ {extras} item(s) beyond the plan (yours — never "
                     f"touched): {', '.join(shown)}"
                     + (" …" if extras > 6 else ""))
    return "\n".join(lines)


def render_orphans(a: PlanAudit) -> str:
    """consolidation-d: the full orphan view — every live channel/category/
    role BEYOND the blueprint, completely listed (render_audit caps at 6).
    'Immersion comes with easy navigation' — this is the cleanup worksheet.
    Deletion stays HUMAN: /cleanup-orphans + the typed phrase removes only
    the orphan CHANNELS listed here (categories only once empty; roles
    never — roles are people's)."""
    lines = [f"🧭 Consolidation audit — {a.guild_name or 'the server'}",
             f"  plan coverage: {a.coverage:.0%} · blueprint = the map"]
    orphan_total = (len(a.extra_channels) + len(a.extra_categories)
                    + len(a.extra_roles))
    if not orphan_total:
        lines.append("  ✨ CLEAN — nothing beyond the blueprint. "
                     "Navigation is exactly the map.")
    else:
        if a.extra_channels:
            lines.append(f"  📦 orphan channels ({len(a.extra_channels)}) — "
                         "not in the blueprint:")
            lines += [f"    − #{c}" for c in a.extra_channels]
        if a.extra_categories:
            lines.append(f"  🗂 orphan categories ({len(a.extra_categories)}):")
            lines += [f"    − {c}" for c in a.extra_categories]
        if a.extra_roles:
            lines.append(f"  👤 roles beyond the plan ({len(a.extra_roles)}) "
                         "— listed only, NEVER deleted:")
            lines += [f"    · {r}" for r in a.extra_roles]
        lines.append("")
        lines.append("  To remove the orphan channels above: "
                     f"/cleanup-orphans confirm:{CLEANUP_CONFIRM_PHRASE}")
        lines.append("  (deletes ONLY those channels + any emptied orphan "
                     "category; paced, audited, irreversible)")
    if a.missing_total:
        lines.append(f"  🔴 {a.missing_total} planned item(s) missing — "
                     "run /setup-shop to create them.")
    return "\n".join(lines)


# ── evolution detection: the plan announces its own changes ──────────────────
def check_plan_evolution(data_dir: Path,
                         bp: ServerBlueprint | None = None) -> str | None:
    """Consulted at every entry point (bot connect, scans, CLI). Returns an
    announcement string the FIRST time a new blueprint fingerprint is seen
    (i.e. an enhancement shipped), else None. Never raises."""
    try:
        fp = blueprint_fingerprint(bp)
        state: dict = {}
        try:
            raw = json.loads(_state_path(data_dir).read_text(encoding="utf-8"))
            state = raw if isinstance(raw, dict) else {}
        except Exception:  # noqa: BLE001
            state = {}
        prev = state.get("blueprint_fingerprint")
        if prev == fp:
            return None
        state["blueprint_fingerprint"] = fp
        state["seen_at"] = time.time()
        _atomic_write(_state_path(data_dir), state)
        if prev is None:
            return None      # first ever sighting — nothing to announce
        return ("📐 The server plan EVOLVED since the last look (an "
                "enhancement changed the blueprint). Run /scan-server to "
                "see what's now missing, then /setup-shop to build it — "
                "create-only, nothing gets deleted.")
    except Exception:  # noqa: BLE001
        return None
