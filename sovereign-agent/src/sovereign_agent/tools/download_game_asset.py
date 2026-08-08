"""download_game_asset — Tier 1. Fetch an openly-licensed audio/art asset
into a game project's workspace.

License-safe by construction: refuses to write anything whose license
isn't in game_assets.ALLOWED_LICENSES (CC0 / public-domain / CC-BY) —
never just documents the rule and hopes. Domain-restricted to known
open-asset sources (game_assets.ALLOWED_ASSET_DOMAINS). Storage-aware:
refuses when the project workspace is already over its soft budget
(game_assets.check_workspace_budget). Every accepted download is recorded
in the project's ASSET_LICENSES.md via game_assets.record_asset — a real
manifest Kevin can check before ever selling the game.

Binary-capable where write_file.py is UTF-8-text-only by design — this is
a genuinely new capability, not a reuse of an existing write tool.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from .. import game_assets
from ..game_projects import game_workspace_dir, load_by_slug
from ..modes import Mode
from ..pathguard import PathScopeViolation, check_write_path
from .base import Tool, ToolResult

_MAX_ASSET_BYTES = 20 * 1024 * 1024  # 20MB per file — generous for SFX/short music, not video


class _Args(BaseModel):
    project_slug: str = Field(description="Slug of a registered game project (see game_projects)")
    url: str = Field(description="Full URL to fetch. Domain must be on the open-asset allowlist.")
    relative_path: str = Field(
        description="Where to save it, relative to the project's assets/ dir "
                    "(e.g. 'audio/jump.wav')"
    )
    license_id: str = Field(
        description="One of: CC0, public-domain, CC-BY. Anything else is refused."
    )
    attribution: str = Field(
        default="", description="Required if license_id is CC-BY; the credit text."
    )


class DownloadGameAssetTool(Tool[_Args]):
    name = "download_game_asset"
    tier = 1
    description = (
        "Download an openly-licensed audio/art asset (from kenney.nl, "
        "opengameart.org, or freesound.org) into a game project's "
        "assets/ folder. Refuses anything not CC0/public-domain/CC-BY, "
        "anything from an un-allowlisted domain, anything over 20MB, and "
        "anything that would push the project workspace over its storage "
        "budget. Records every accepted asset in ASSET_LICENSES.md. "
        "FAILURE MODES: unknown_project; domain_not_allowlisted; "
        "license_not_allowed; missing_attribution; over_budget; "
        "too_large; download_failed; path_scope_violation."
    )
    failure_modes = (
        "unknown_project",
        "domain_not_allowlisted",
        "license_not_allowed",
        "missing_attribution",
        "over_budget",
        "too_large",
        "download_failed",
        "path_scope_violation",
    )
    Args = _Args

    def __init__(self, mode: Mode | None = None, data_dir: Path | None = None) -> None:
        self._mode = mode or Mode.ONESHOT
        self._data_dir = data_dir

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        data_dir = self._data_dir
        if data_dir is None:
            from ..config import SETTINGS
            data_dir = SETTINGS.paths.data_dir

        project = load_by_slug(args.project_slug, data_dir)
        if project is None:
            return ToolResult(ok=False, error=f"unknown_project: {args.project_slug!r}")

        try:
            host = (urlparse(args.url).hostname or "").lower()
        except ValueError as e:
            return ToolResult(ok=False, error=f"invalid URL: {e}")
        if not game_assets.domain_allowed(host):
            return ToolResult(
                ok=False,
                error=f"domain_not_allowlisted: {host} not in {sorted(game_assets.ALLOWED_ASSET_DOMAINS)}",
            )

        license_errs = game_assets.validate_license(args.license_id)
        if license_errs:
            return ToolResult(ok=False, error="license_not_allowed: " + "; ".join(license_errs))
        if args.license_id == "CC-BY" and not args.attribution.strip():
            return ToolResult(ok=False, error="missing_attribution: CC-BY requires attribution text")

        workspace = game_workspace_dir(args.project_slug, sandbox_dir=None)
        budget = game_assets.check_workspace_budget(workspace)
        if budget.over_budget:
            return ToolResult(
                ok=False,
                error=f"over_budget: workspace already {budget.used_mb}MB / {budget.budget_mb}MB",
            )

        target = workspace / "assets" / args.relative_path
        try:
            resolved = check_write_path(target, self._mode)
        except PathScopeViolation as e:
            return ToolResult(ok=False, error=f"path_scope_violation: {e}")

        try:
            async with httpx.AsyncClient(
                timeout=20.0, follow_redirects=True,
                headers={"User-Agent": "sovereign-agent/0.1"},
            ) as client:
                resp = await client.get(args.url)
        except httpx.HTTPError as e:
            return ToolResult(ok=False, error=f"download_failed: {type(e).__name__}: {e}")

        if not (200 <= resp.status_code < 300):
            return ToolResult(ok=False, error=f"download_failed: status {resp.status_code}")
        if len(resp.content) > _MAX_ASSET_BYTES:
            return ToolResult(
                ok=False,
                error=f"too_large: {len(resp.content)} bytes exceeds {_MAX_ASSET_BYTES}",
            )

        resolved.parent.mkdir(parents=True, exist_ok=True)
        tmp = resolved.with_suffix(resolved.suffix + ".tmp")
        tmp.write_bytes(resp.content)
        tmp.replace(resolved)

        manifest = game_assets.record_asset(
            workspace,
            relative_path=f"assets/{args.relative_path}",
            source_url=args.url,
            license_id=args.license_id,
            attribution=args.attribution,
        )

        return ToolResult(ok=True, output={
            "saved_to": str(resolved),
            "bytes": len(resp.content),
            "license": args.license_id,
            "manifest": str(manifest),
            "workspace_used_mb": game_assets.check_workspace_budget(workspace).used_mb,
        })


__all__ = ["DownloadGameAssetTool"]
