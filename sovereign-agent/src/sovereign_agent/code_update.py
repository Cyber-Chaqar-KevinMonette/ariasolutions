"""
╔══════════════════════════════════════════════════════════════════════════╗
║  code_update.py — Safe code-update pipeline (v0.2.10)                    ║
║                                                                          ║
║  ╭─ THE WALL THAT STAYS UP ─────────────────────────────────╮            ║
║  │                                                           │            ║
║  │  The system stages a proposed change.                     │            ║
║  │  The system runs tests against the staged change.         │            ║
║  │  The OPERATOR approves the change after seeing test       │            ║
║  │   results.                                                │            ║
║  │  The system then archives current code + applies change.  │            ║
║  │  The OPERATOR can rollback any applied change.            │            ║
║  │                                                           │            ║
║  │  At no point does the system approve its own proposal.    │            ║
║  │  HMAC gate stays. Tests are evidence; not authorization.  │            ║
║  │                                                           │            ║
║  ╰───────────────────────────────────────────────────────────╯            ║
║                                                                          ║
║  Pipeline:                                                                ║
║    1. operator stages a proposed file at /tmp/myfix.py                   ║
║    2. operator creates a code_update proposal pointing at it             ║
║    3. operator runs `sov proposals stage <prop>` → copies to staging,    ║
║       runs pytest against the staged tree, records result                ║
║    4. operator reviews `sov proposals show <prop>` (sees test result)    ║
║    5. operator approves via `sov proposals approve <prop>`               ║
║    6. operator runs `sov plan code-update-apply` → archive+swap          ║
║    7. operator can `sov proposals rollback <prop>` to restore from       ║
║       archive at any point                                               ║
║                                                                          ║
║  Storage layout:                                                         ║
║    <data_dir>/staging/<proposal_id>/                                     ║
║      proposed_file.py        ← the staged candidate                      ║
║      target_relpath.txt      ← where it will go (relative to repo root)  ║
║      test_result.json        ← {ok: bool, summary: str, ran_at: iso}     ║
║                                                                          ║
║    <data_dir>/archive/<timestamp>/                                       ║
║      <relpath>               ← copy of the file as it was BEFORE swap    ║
║      meta.json               ← {proposal_id, original_path, swapped_at}  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# ─── Errors ─────────────────────────────────────────────────────────────────


class CodeUpdateError(Exception):
    """Base for code-update errors."""


class StagingError(CodeUpdateError):
    """A staging step (copy, validate, test) failed."""


class SwapError(CodeUpdateError):
    """The atomic swap (archive + replace) failed."""


# ─── Helpers ────────────────────────────────────────────────────────────────


def _utc_now_compact() -> str:
    """Compact timestamp suitable for archive directory names."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _resolve_repo_root() -> Path:
    """Find the repo root by walking up until we see pyproject.toml.

    The agent's installed package can be in editable mode (``uv sync`` /
    ``uv pip install -e .``, formerly ``pip install -e .``) where its source
    files are in the repo, OR in normal install mode where they're in
    site-packages. We support editable mode here — code-self-update against
    a non-editable install is a different, more complex case that requires
    installer interaction rather than file replacement.
    """
    # __file__ → src/sovereign_agent/code_update.py → parent.parent is repo root
    here = Path(__file__).resolve().parent.parent.parent
    if (here / "pyproject.toml").exists():
        return here
    # Fall back: walk up
    for ancestor in here.parents:
        if (ancestor / "pyproject.toml").exists():
            return ancestor
    raise CodeUpdateError(
        "could not locate repo root (no pyproject.toml found above this module). "
        "code-self-update requires an editable install."
    )


def _staging_dir(data_dir: Path, proposal_id: str) -> Path:
    return data_dir / "staging" / proposal_id


def _archive_dir(data_dir: Path, timestamp: str) -> Path:
    return data_dir / "archive" / timestamp


# ─── Stage: copy + validate + test ──────────────────────────────────────────


def stage_proposal(
    *, proposal_id: str, source_path: Path, target_relpath: str,
    data_dir: Path,
) -> Path:
    """Copy the proposed file into staging. Returns the staging directory.

    Validates:
      - source_path exists and is a regular file
      - target_relpath is relative (not absolute), within the repo
      - target_relpath, when joined to repo root, currently exists (we're
        replacing something — not creating new files via this pipeline yet)
    """
    src = Path(source_path)
    if not src.exists():
        raise StagingError(f"source path does not exist: {src}")
    if not src.is_file():
        raise StagingError(f"source path is not a regular file: {src}")

    rel = Path(target_relpath)
    if rel.is_absolute():
        raise StagingError(
            f"target_relpath must be relative (got absolute: {rel}). "
            "Specify a path relative to the repo root."
        )
    # Disallow .. traversal
    if any(part == ".." for part in rel.parts):
        raise StagingError(f"target_relpath cannot contain '..': {rel}")

    repo_root = _resolve_repo_root()
    target_abs = (repo_root / rel).resolve()
    # Confine target to the repo root
    try:
        target_abs.relative_to(repo_root)
    except ValueError:
        raise StagingError(
            f"target_relpath escapes repo root: {rel}"
        )
    if not target_abs.exists():
        raise StagingError(
            f"target file does not exist (yet): {rel}. "
            "code-update currently replaces existing files only; "
            "creation is a different operation."
        )

    staging = _staging_dir(data_dir, proposal_id)
    staging.mkdir(parents=True, exist_ok=True)

    # Copy proposed file as-is into staging/proposed_file
    proposed = staging / "proposed_file"
    shutil.copy2(src, proposed)

    # Record the target path for later swap
    (staging / "target_relpath.txt").write_text(str(rel) + "\n", encoding="utf-8")

    return staging


def run_tests_against_staging(
    *, proposal_id: str, data_dir: Path, pytest_args: list[str] | None = None,
    timeout: int = 600,
) -> dict:
    """Apply the staged file IN-PLACE temporarily, run pytest, restore.

    Returns a dict: {ok: bool, summary: str, returncode: int, stdout_tail,
                     ran_at, duration_seconds}.

    Uses a backup+restore-around-pytest dance:
      1. read current target file content into memory
      2. write proposed content to target
      3. run pytest
      4. restore the original target content (regardless of pytest result)

    This is safe under crash because the original content is held in memory
    AND we write it back unconditionally in the finally block. If the
    process is hard-killed mid-test, the operator has the proposed file in
    staging and can manually compare/restore. The risk is bounded.
    """
    staging = _staging_dir(data_dir, proposal_id)
    proposed = staging / "proposed_file"
    target_relpath_file = staging / "target_relpath.txt"
    if not proposed.exists():
        raise StagingError(f"staging not initialized for {proposal_id}: {proposed} missing")
    if not target_relpath_file.exists():
        raise StagingError(f"staging target_relpath missing for {proposal_id}")

    rel = Path(target_relpath_file.read_text(encoding="utf-8").strip())
    repo_root = _resolve_repo_root()
    target_abs = (repo_root / rel).resolve()
    if not target_abs.exists():
        raise StagingError(f"target file no longer exists: {target_abs}")

    # Read current content
    original_bytes = target_abs.read_bytes()
    proposed_bytes = proposed.read_bytes()

    started = datetime.now(timezone.utc)
    args = pytest_args or ["-q", "--tb=short", "-x"]

    result_dict: dict = {
        "ok": False,
        "summary": "",
        "returncode": -1,
        "stdout_tail": "",
        "ran_at": _utc_now_iso(),
        "duration_seconds": 0.0,
    }
    try:
        # Apply proposed content to target (TEMPORARILY)
        target_abs.write_bytes(proposed_bytes)

        # Run pytest in the repo root
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", *args, "tests/"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "AGENT_INTERNET": "off"},
            )
            stdout_tail = (proc.stdout or "").splitlines()[-30:]
            stderr_tail = (proc.stderr or "").splitlines()[-10:]
            tail = "\n".join(stdout_tail + (["--- STDERR ---"] + stderr_tail if stderr_tail else []))
            result_dict["returncode"] = proc.returncode
            result_dict["stdout_tail"] = tail[-4000:]
            result_dict["ok"] = (proc.returncode == 0)
            # Extract a short summary line like "320 passed in 13.5s"
            for line in reversed(stdout_tail):
                if "passed" in line or "failed" in line or "error" in line:
                    result_dict["summary"] = line.strip()
                    break
            if not result_dict["summary"]:
                result_dict["summary"] = (
                    f"pytest returncode={proc.returncode}"
                )
        except subprocess.TimeoutExpired:
            result_dict["ok"] = False
            result_dict["summary"] = f"timeout after {timeout}s"
            result_dict["stdout_tail"] = "TIMEOUT"
        except Exception as e:  # noqa: BLE001
            result_dict["ok"] = False
            result_dict["summary"] = f"pytest invocation failed: {type(e).__name__}: {e}"
    finally:
        # Restore original content NO MATTER WHAT
        try:
            target_abs.write_bytes(original_bytes)
        except Exception as e:  # noqa: BLE001
            # We have the original in memory; if we can't write, we have a
            # bigger problem. Surface loudly.
            result_dict["restore_error"] = (
                f"CRITICAL: failed to restore original {target_abs}: "
                f"{type(e).__name__}: {e}. "
                f"Manual recovery: file was at {staging}/original_backup"
            )
            # Write to staging as last-resort backup
            try:
                (staging / "original_backup").write_bytes(original_bytes)
            except Exception:  # noqa: BLE001
                pass

    duration = (datetime.now(timezone.utc) - started).total_seconds()
    result_dict["duration_seconds"] = duration

    # Persist the result inside staging
    (staging / "test_result.json").write_text(
        json.dumps(result_dict, indent=2), encoding="utf-8",
    )
    return result_dict


# ─── Apply: archive + swap ──────────────────────────────────────────────────


def archive_and_swap(
    *, proposal_id: str, data_dir: Path,
) -> dict:
    """Archive the current target file and swap in the staged proposal.

    Returns a rollback descriptor:
      {
        "type": "code_rollback",
        "archive_dir": "/path/to/archive/<ts>",
        "target_relpath": "src/...",
        "proposal_id": "...",
        "swapped_at": iso,
      }

    The rollback descriptor is what gets stored on the applied proposal.
    `sov proposals rollback <prop>` reads it and reverses the swap.
    """
    staging = _staging_dir(data_dir, proposal_id)
    proposed = staging / "proposed_file"
    target_relpath_file = staging / "target_relpath.txt"
    test_result_file = staging / "test_result.json"

    if not proposed.exists():
        raise SwapError(f"staging not initialized for {proposal_id}")
    if not target_relpath_file.exists():
        raise SwapError(f"target_relpath missing for {proposal_id}")
    if not test_result_file.exists():
        raise SwapError(
            f"no test result for {proposal_id} — run "
            f"`sov proposals stage {proposal_id}` first"
        )
    test_result = json.loads(test_result_file.read_text(encoding="utf-8"))
    if not test_result.get("ok"):
        raise SwapError(
            f"refusing to swap {proposal_id}: tests failed "
            f"({test_result.get('summary', 'unknown')})"
        )

    rel = Path(target_relpath_file.read_text(encoding="utf-8").strip())
    repo_root = _resolve_repo_root()
    target_abs = (repo_root / rel).resolve()
    if not target_abs.exists():
        raise SwapError(f"target file no longer exists: {target_abs}")

    # Archive current target
    timestamp = _utc_now_compact()
    archive = _archive_dir(data_dir, timestamp)
    archive_target = archive / rel
    archive_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target_abs, archive_target)
    swapped_at = _utc_now_iso()
    (archive / "meta.json").write_text(
        json.dumps({
            "proposal_id": proposal_id,
            "target_relpath": str(rel),
            "swapped_at": swapped_at,
            "test_result_summary": test_result.get("summary", ""),
        }, indent=2),
        encoding="utf-8",
    )

    # Swap: atomic rename through a tempfile in the same directory
    proposed_bytes = proposed.read_bytes()
    tmp = target_abs.with_suffix(target_abs.suffix + ".swap-tmp")
    try:
        tmp.write_bytes(proposed_bytes)
        os.replace(tmp, target_abs)  # atomic on POSIX
    except Exception as e:  # noqa: BLE001
        # Try to clean up tmp
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:  # noqa: BLE001
            pass
        raise SwapError(f"atomic swap failed: {type(e).__name__}: {e}") from e

    return {
        "type": "code_rollback",
        "archive_dir": str(archive),
        "target_relpath": str(rel),
        "proposal_id": proposal_id,
        "swapped_at": swapped_at,
    }


# ─── Rollback: restore archived file ────────────────────────────────────────


def rollback_from_archive(*, archive_dir: Path, target_relpath: str) -> dict:
    """Restore the archived file to its target path.

    Used when the operator runs `sov proposals rollback <applied-id>`. Reads
    the archive, copies the file back, returns a result summary.

    The applied proposal stays as 'applied' (audit trail) but a new event
    `code-update-rolled-back-d` is logged.
    """
    archive = Path(archive_dir)
    rel = Path(target_relpath)
    archived_file = archive / rel

    if not archive.exists():
        raise CodeUpdateError(f"archive does not exist: {archive}")
    if not archived_file.exists():
        raise CodeUpdateError(f"archived file missing: {archived_file}")

    repo_root = _resolve_repo_root()
    target_abs = (repo_root / rel).resolve()
    try:
        target_abs.relative_to(repo_root)
    except ValueError:
        raise CodeUpdateError(f"target escapes repo root: {rel}")

    # Same atomic-swap dance for the restore
    archived_bytes = archived_file.read_bytes()
    tmp = target_abs.with_suffix(target_abs.suffix + ".rollback-tmp")
    try:
        tmp.write_bytes(archived_bytes)
        os.replace(tmp, target_abs)
    except Exception as e:  # noqa: BLE001
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:  # noqa: BLE001
            pass
        raise CodeUpdateError(f"rollback swap failed: {type(e).__name__}: {e}") from e

    return {
        "ok": True,
        "restored_to": str(target_abs),
        "from_archive": str(archive),
        "rolled_back_at": _utc_now_iso(),
    }


# ─── Stage diagnostic readers ───────────────────────────────────────────────


def get_staging_status(*, proposal_id: str, data_dir: Path) -> dict:
    """Read the current staging state for a proposal. For `proposals show`."""
    staging = _staging_dir(data_dir, proposal_id)
    if not staging.exists():
        return {"staged": False}
    out: dict = {
        "staged": True,
        "staging_dir": str(staging),
    }
    target_file = staging / "target_relpath.txt"
    if target_file.exists():
        out["target_relpath"] = target_file.read_text(encoding="utf-8").strip()
    test_result_file = staging / "test_result.json"
    if test_result_file.exists():
        try:
            out["test_result"] = json.loads(test_result_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            out["test_result"] = {"ok": False, "summary": "corrupt test_result.json"}
    return out
