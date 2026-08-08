"""tools/git_reflect.py — Git commit reflection loop (M61).

  git_commit_reflect()    T0 — write experience atom after a commit
  git_week_summary()      T0 — commits vs reflection coverage for last 7 days
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

try:
    from sovereign_agent.db import open_atoms_db
except ImportError:
    open_atoms_db = None  # type: ignore[assignment]

try:
    from sovereign_agent.memory import Atom, write_atom
except ImportError:
    Atom = None  # type: ignore[assignment]
    write_atom = None  # type: ignore[assignment]

try:
    from sovereign_agent.config import SETTINGS
    _REPO_ROOT: Path | None = SETTINGS.paths.data_dir.parent.parent
except Exception:  # noqa: BLE001
    _REPO_ROOT = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_root() -> str:
    if _REPO_ROOT and _REPO_ROOT.is_dir():
        return str(_REPO_ROOT)
    return "."


def _atom_exists_for_sha(sha_prefix: str) -> bool:
    """Check if a git-reflect experience atom already exists for this sha prefix."""
    if open_atoms_db is None:
        return False
    try:
        conn = open_atoms_db()
        rows = conn.execute(
            "SELECT COUNT(*) FROM atoms "
            "WHERE type='experience' AND scope_tags LIKE ?",
            (f'%"{sha_prefix}"%',),
        ).fetchone()
        conn.close()
        return (rows[0] if rows else 0) > 0
    except Exception:  # noqa: BLE001
        return False


def _git_commits_last_7_days() -> list[str]:
    """Return list of commit shas from last 7 days."""
    try:
        result = subprocess.run(
            ["git", "log", "--since=7 days ago", "--pretty=format:%H"],
            capture_output=True, text=True, timeout=5, cwd=_repo_root(),
        )
        return [sha[:8] for sha in result.stdout.strip().splitlines() if sha.strip()]
    except Exception:  # noqa: BLE001
        return []


def _git_reflect_atoms() -> list[str]:
    """Return list of sha prefixes that have reflection atoms."""
    if open_atoms_db is None:
        return []
    try:
        conn = open_atoms_db()
        rows = conn.execute(
            "SELECT scope_tags FROM atoms "
            "WHERE type='experience' AND scope_tags LIKE '%\"git\"%' AND scope_tags LIKE '%\"commit\"%' "
            "AND superseded_at IS NULL",
        ).fetchall()
        shas = []
        for (tags_json,) in rows:
            try:
                tags = json.loads(tags_json) if isinstance(tags_json, str) else (tags_json or [])
                for tag in tags:
                    if len(tag) == 8 and all(c in "0123456789abcdef" for c in tag.lower()):
                        shas.append(tag)
            except Exception:  # noqa: BLE001
                pass
        conn.close()
        return shas
    except Exception:  # noqa: BLE001
        return []


# ── GitCommitReflectTool ──────────────────────────────────────────────────────

class _ReflectArgs(BaseModel):
    commit_sha: str = Field(description="The full or short (8-char) commit SHA.")
    what_changed: str = Field(description="What was changed in this commit (files, modules, behavior).")
    why_it_mattered: str = Field(description="Why this change was meaningful for Aria's growth or value.")
    what_surprised_me: str = Field(
        default="",
        description="Anything unexpected encountered during this commit's work.",
    )
    surprise_level: float = Field(
        default=0.1, ge=0.0, le=1.0,
        description="How surprising was this commit's outcome? 0=routine, 1=completely unexpected.",
    )


class GitCommitReflectTool(Tool[_ReflectArgs]):
    name = "git_commit_reflect"
    tier = 0
    description = (
        "Write an experience atom documenting a git commit — what changed, why it mattered, "
        "and what surprised you. Call this immediately after every git_commit() call. "
        "Idempotent: skips silently if a reflection atom for this commit SHA already exists. "
        "Closes the eval loop: commits earn points, but only reflected commits teach."
    )
    failure_modes = ("db_write_failed",)
    Args = _ReflectArgs

    async def execute(self, args: _ReflectArgs, *, trace_id: str) -> ToolResult:
        if open_atoms_db is None or Atom is None or write_atom is None:
            return ToolResult(ok=False, error="DB or write_atom unavailable.")

        sha_prefix = args.commit_sha[:8].lower()

        # Idempotency check
        already = await asyncio.to_thread(_atom_exists_for_sha, sha_prefix)
        if already:
            return ToolResult(ok=True, output={
                "idempotent": True,
                "commit_sha": sha_prefix,
                "note": "Reflection atom already exists for this commit — skipped.",
            })

        content = {
            "commit_sha": sha_prefix,
            "what_changed": args.what_changed,
            "why_it_mattered": args.why_it_mattered,
            "what_surprised_me": args.what_surprised_me,
            "surprise_level": args.surprise_level,
            "domain": "git",
        }
        summary = f"[git/{sha_prefix}] {args.why_it_mattered[:100]}"

        atom = Atom(
            type="experience",
            summary=summary,
            content_ref={"kind": "inline", "content": json.dumps(content)},
            claims=[],
            parents=[trace_id],
            confidence=1.0,
            created_by={"actor": "git-experience-crown", "version": "M61"},
            scope_tags=["git", "commit", sha_prefix],
        )
        try:
            conn = open_atoms_db()
            atom_id = await asyncio.to_thread(write_atom, conn, atom)
            conn.commit()
            return ToolResult(ok=True, output={
                "atom_id": str(atom_id),
                "commit_sha": sha_prefix,
                "summary": summary,
                "surprise_level": args.surprise_level,
                "idempotent": False,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"git_commit_reflect failed: {e}")


# ── GitWeekSummaryTool ────────────────────────────────────────────────────────

class _WeekArgs(BaseModel):
    days: int = Field(default=7, ge=1, le=30, description="How many days of git history to cover.")


class GitWeekSummaryTool(Tool[_WeekArgs]):
    name = "git_week_summary"
    tier = 0
    description = (
        "Summarize git commit coverage for the last N days. "
        "Returns: commits with reflection atoms, commits missing reflections, "
        "and coverage_pct. Use to see how well the commit→reflect loop is closing."
    )
    failure_modes = ("git_unavailable",)
    Args = _WeekArgs

    async def execute(self, args: _WeekArgs, *, trace_id: str) -> ToolResult:
        try:
            commits = await asyncio.to_thread(_git_commits_last_7_days)
            reflected_shas = set(await asyncio.to_thread(_git_reflect_atoms))

            with_reflection = [sha for sha in commits if sha in reflected_shas]
            without_reflection = [sha for sha in commits if sha not in reflected_shas]
            total = len(commits)
            coverage = round(len(with_reflection) / total, 3) if total > 0 else 0.0

            return ToolResult(ok=True, output={
                "days": args.days,
                "total_commits": total,
                "reflected_count": len(with_reflection),
                "gap_count": len(without_reflection),
                "coverage_pct": round(coverage * 100, 1),
                "commits_with_reflection": with_reflection,
                "commits_without_reflection": without_reflection,
                "note": (
                    "Coverage 100% — every commit has a reflection."
                    if coverage == 1.0 and total > 0
                    else f"{len(without_reflection)} commit(s) missing reflection — call git_commit_reflect() for each."
                    if without_reflection
                    else "No commits found in the last 7 days."
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"git_week_summary failed: {e}")


__all__ = ["GitCommitReflectTool", "GitWeekSummaryTool"]
