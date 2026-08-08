"""doc_registry — she always knows where her maps and guides are.

Kevin's ask: a system for the system maps so she never loses them and never
gets confused. This is the canonical registry of every major document — each
entry carries its purpose and is **verified on disk** at read time, so a
missing/moved doc is flagged loudly instead of silently lost.

Chat bridge #11: "where are the docs / the system map?" → the verified list.
CLI: `sov docs`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "DocEntry",
    "DOC_CATALOG",
    "repo_root",
    "registry_status",
    "compose_docs_report",
    "is_docs_query",
]


@dataclass(frozen=True)
class DocEntry:
    rel_path: str          # relative to the repo root
    title: str
    purpose: str           # one line — what you'd open it FOR


DOC_CATALOG: list[DocEntry] = [
    DocEntry("SETUP_MASTER.md", "The Master Setup Guide",
             "THE ordered path through the entire shop setup (start here)"),
    DocEntry("SYSTEM_MAP.md", "System Map",
             "every system, file, data path, env var, CLI + the change ledger"),
    DocEntry("SHOP_DESIGN.md", "Shop Design",
             "the business layer: offer, tiers, cancellation lifecycle, rewards"),
    DocEntry("DISCORD_SERVER_SETUP.md", "Discord Server Guide",
             "server structure + by-hand permission steps (deep reference)"),
    DocEntry("DISCORD_ADMIN.md", "Admin Bot Reference",
             "what the admin bot is + how to add slash commands"),
    DocEntry("STRIPE_LOCKIN.md", "Stripe Lock-In",
             "the ONLY remaining setup: 10 Payment Links, every click in order"),
    DocEntry("KEY_GATHERING.md", "Key Gathering",
             "the Key Concierge: gather API keys (Reddit/Best Buy/Google/eBay) "
             "with links + steps — sov keys onboard"),
    DocEntry("SYSTEM_MAP_AUTO.md", "Auto System Map",
             "the map that draws itself — sov map refresh + daily duty auto-refresh"),
    DocEntry("KEY_VAULT_GUIDE.md", "Key Vault Guide",
             "storing/rotating every secret safely — sov keys, masked, 0600"),
    DocEntry("LICENSE", "Proprietary License",
             "all-rights-reserved protection for the code + IP"),
    DocEntry("legal/TERMS_OF_SERVICE.md", "Terms of Service",
             "the shop's customer terms (billing, cancellation, conduct)"),
    DocEntry("legal/PRIVACY_POLICY.md", "Privacy Policy",
             "what data the shop handles — needed for bot verification"),
    DocEntry("Plans/NextPlan3/DiscordBotStudio/DESIGN.md", "Bot Runtime Design",
             "the discord_runtime safety posture + components"),
    DocEntry("CHANGELOG.md", "Changelog",
             "what shipped, release by release (Unreleased = this arc)"),
    DocEntry("SPRINT_STATE.md", "Sprint State",
             "where the current sprint stands + apply runbook"),
    DocEntry("CLAUDE.md", "Operating Guide",
             "the standing rules for any AI working on Aria"),
    DocEntry("handoff/00_START_HERE.md", "Handoff: Start Here",
             "picking Aria up cold — who she is, the hard DO-NOTs"),
    DocEntry("handoff/01_ARCHITECTURE.md", "Handoff: Architecture",
             "how her systems fit together"),
    DocEntry("handoff/02_SAFETY_MODEL.md", "Handoff: Safety Model",
             "the gates, tiers, and sealed files"),
    DocEntry("handoff/03_CONVENTIONS.md", "Handoff: Conventions",
             "how code ships here (staged modules, naming, discipline)"),
    DocEntry("handoff/04_EVENT_VOCABULARY.md", "Handoff: Event Vocabulary",
             "the event names and what they mean"),
    DocEntry("handoff/05_ENGINEERING_LESSONS.md", "Handoff: Engineering Lessons",
             "the scar tissue as law — check new code against ALL"),
    DocEntry("handoff/06_RUNBOOK.md", "Handoff: Runbook",
             "operational how-tos (run, test, recover)"),
    DocEntry("handoff/07_ROADMAP.md", "Handoff: Roadmap",
             "honest gaps + what's next (incl. shop Round 2)"),
]


def repo_root() -> Path:
    """The repo root — this file lives at <root>/src/sovereign_agent/."""
    return Path(__file__).resolve().parents[2]


def registry_status(root: Path | None = None) -> list[dict]:
    """Every registered doc + whether it actually exists on disk."""
    root = root or repo_root()
    out: list[dict] = []
    for e in DOC_CATALOG:
        p = root / e.rel_path
        out.append({"title": e.title, "path": str(p), "rel_path": e.rel_path,
                    "purpose": e.purpose, "exists": p.is_file()})
    return out


def compose_docs_report(root: Path | None = None) -> str:
    rows = registry_status(root)
    missing = [r for r in rows if not r["exists"]]
    lines = [f"🗺️ My maps & guides ({len(rows)} registered"
             + (f", [b]{len(missing)} MISSING[/b]" if missing else ", all present ✅")
             + "):"]
    for r in rows:
        mark = "✅" if r["exists"] else "❌ MISSING"
        lines.append(f"  {mark} [b]{r['title']}[/b] — {r['purpose']}\n"
                     f"      [dim]{r['rel_path']}[/dim]")
    if missing:
        lines.append("[b]A registered doc is missing — it may have been moved "
                     "or deleted. Check git history before assuming it's gone.[/b]")
    return "\n".join(lines)


# Precise triggers (lesson 16; enforced by the collision matrix).
_DOCS_TRIGGERS = (
    "where are the docs", "where are your docs", "where is the system map",
    "where are the system maps", "where is the setup guide", "list the docs",
    "your documentation", "the doc registry", "where are the guides",
    "where is the changelog", "find the docs", "show me the docs",
)


def is_docs_query(text: str) -> bool:
    if not text:
        return False
    from sovereign_agent.bridge_patterns import match_any
    return match_any(text, _DOCS_TRIGGERS)
