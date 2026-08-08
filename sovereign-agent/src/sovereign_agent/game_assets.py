"""game_assets — music/SFX for game projects: license-safe by construction,
storage-aware by construction.

Kevin's ask (2026-07-20): Aria can produce music/SFX herself, or download
them, "as long as they are free and opensourced" — and she "needs to be
storage aware and mindful."

Two real constraints, kept structural rather than hoped-for:

  1. License safety: `validate_license()` only accepts a small allowlist of
     licenses that are actually safe to ship in a game Kevin might sell
     (CC0 / public domain / CC-BY). Anything else — including plain "free"
     listings that are non-commercial-only — is refused before a single
     byte is written. Every accepted download is appended to a plain,
     human-readable `ASSET_LICENSES.md` inside the project workspace, so
     Kevin can check it before ever selling the game. `ALLOWED_ASSET_DOMAINS`
     restricts *where* a download can come from to sources known to publish
     openly-licensed game assets (Kenney.nl is explicitly CC0 and built for
     jams; OpenGameArt.org and Freesound.org host a mix, hence the license
     check on top of the domain check, not instead of it).

  2. Storage awareness: `check_workspace_budget()` is a soft per-project
     disk ceiling (default 500MB — generous for a jam-scope game). Callers
     (the asset downloader, godot_run's export action) check this BEFORE
     writing and refuse over budget, the same philosophy this repo already
     applies to VRAM (see CLAUDE.md's vram.py note), applied to disk on a
     resource-constrained machine.

Self-produced audio (Godot's AudioStreamGenerator, simple synthesized SFX
written directly in GDScript) needs no Python tooling here — it's game
code Aria writes directly, not a Python audio-generation subsystem.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ALLOWED_ASSET_DOMAINS",
    "ALLOWED_LICENSES",
    "DEFAULT_WORKSPACE_BUDGET_BYTES",
    "BudgetStatus",
    "validate_license",
    "domain_allowed",
    "check_workspace_budget",
    "record_asset",
    "asset_licenses_path",
]

# Known sources of openly-licensed game audio/art. Freesound and
# OpenGameArt host a MIX of licenses, so domain allowlisting alone is not
# sufficient — validate_license() is the real gate.
ALLOWED_ASSET_DOMAINS: frozenset[str] = frozenset({
    "kenney.nl",
    "opengameart.org",
    "freesound.org",
})

# Only licenses that are safe to ship in a game Kevin might sell.
# Deliberately excludes anything NC (non-commercial-only) — the stated
# goal is real, even if small, revenue.
ALLOWED_LICENSES: frozenset[str] = frozenset({"CC0", "public-domain", "CC-BY"})

DEFAULT_WORKSPACE_BUDGET_BYTES = 500 * 1024 * 1024  # 500MB, generous for a jam-scope game


def validate_license(license_id: str) -> list[str]:
    """Returns a list of problems; empty list means the license is fine to
    use commercially. Never raises — callers decide what refusing looks
    like (a tool returns ok=False; a plain function call can just check)."""
    errs: list[str] = []
    if license_id not in ALLOWED_LICENSES:
        errs.append(
            f"license {license_id!r} not in the allowed set "
            f"{sorted(ALLOWED_LICENSES)} — refusing (may not be safe to "
            "ship in a game we might sell)"
        )
    return errs


def domain_allowed(host: str) -> bool:
    host = (host or "").lower()
    return host in ALLOWED_ASSET_DOMAINS or any(
        host.endswith("." + d) for d in ALLOWED_ASSET_DOMAINS
    )


@dataclass
class BudgetStatus:
    used_bytes: int
    budget_bytes: int

    @property
    def over_budget(self) -> bool:
        return self.used_bytes > self.budget_bytes

    @property
    def remaining_bytes(self) -> int:
        return max(0, self.budget_bytes - self.used_bytes)

    @property
    def used_mb(self) -> float:
        return round(self.used_bytes / (1024 * 1024), 1)

    @property
    def budget_mb(self) -> float:
        return round(self.budget_bytes / (1024 * 1024), 1)


def _dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.is_dir():
        return 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                continue
    return total


def check_workspace_budget(
    workspace_dir: Path,
    budget_bytes: int = DEFAULT_WORKSPACE_BUDGET_BYTES,
) -> BudgetStatus:
    """Real, measured disk usage under a game project's workspace vs. its
    soft budget. Callers refuse new writes when over_budget is True rather
    than silently letting a project balloon on a resource-constrained
    machine."""
    return BudgetStatus(
        used_bytes=_dir_size_bytes(Path(workspace_dir)),
        budget_bytes=budget_bytes,
    )


def asset_licenses_path(workspace_dir: Path) -> Path:
    return Path(workspace_dir) / "ASSET_LICENSES.md"


def record_asset(
    workspace_dir: Path,
    *,
    relative_path: str,
    source_url: str,
    license_id: str,
    attribution: str = "",
) -> Path:
    """Append one line to the project's plain, human-readable license
    manifest. Called AFTER a successful download — the caller (the
    download tool) is responsible for having already refused anything
    with an unrecognized license before this is ever reached."""
    path = asset_licenses_path(workspace_dir)
    is_new = not path.is_file()
    with open(path, "a", encoding="utf-8") as fh:
        if is_new:
            fh.write(
                "# Asset licenses\n\n"
                "Every downloaded audio/art asset in this project is "
                "recorded here — check before selling this game.\n\n"
            )
        attr = f" — attribution: {attribution}" if attribution else ""
        fh.write(f"- `{relative_path}` — {license_id} — source: {source_url}{attr}\n")
    return path
