"""
╔══════════════════════════════════════════════════════════════════════════╗
║  doctor.py — environment + install diagnostic                            ║
║  v0.2.18.1                                                                ║
║                                                                           ║
║  WHY THIS EXISTS                                                         ║
║                                                                           ║
║    An operator hit this exact failure pattern: tried to install        ║
║    v0.2.18.0 but the tarball wasn't downloaded yet, the shell          ║
║    autocompleted into the wrong directory, ``pip install -e .``        ║
║    silently DOWNGRADED them, and then commands like ``sov migrations`` ║
║    failed because they were running an older version that didn't      ║
║    have them.                                                           ║
║                                                                           ║
║    As of the uv migration, ``pip install --break-system-packages``     ║
║    is gone — ``./install.sh`` resolves the source dir via ``$BASH_SOURCE`` ║
║    and uv syncs into a managed venv at ${XDG_DATA_HOME}/sovereign-agent/  ║
║    venv. The whole class of "wrong directory" footguns is closed by     ║
║    construction. ``sov doctor`` is the verification surface that proves  ║
║    the install matches what the operator expects.                       ║
║                                                                           ║
║    The fix is not "operator should be more careful." The fix is to    ║
║    give the operator a single command that names exactly what is       ║
║    installed, where, and whether it matches what they think they have.║
║                                                                           ║
║    ``sov doctor`` is that command. It checks:                          ║
║                                                                           ║
║      * version on PATH vs. version requested                           ║
║      * which install directory ``sovereign-agent-current`` resolves to ║
║      * data_dir, config_dir existence and writability                  ║
║      * atoms.db existence, size, integrity_check                       ║
║      * migration status (applied vs pending)                           ║
║      * available channels (registered vs. expected for this version)  ║
║      * Python version, OS, key dependency versions                     ║
║      * disk space available                                            ║
║      * the seven commitments file (ARIA.md present)                    ║
║                                                                           ║
║    Returns a structured DoctorReport with verdict per check and an     ║
║    overall "healthy" / "needs attention" / "broken" summary.           ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import os
import platform
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


CheckLevel = Literal["ok", "info", "warning", "error"]


@dataclass(frozen=True)
class CheckResult:
    name: str
    level: CheckLevel        # 'ok' | 'info' | 'warning' | 'error'
    summary: str
    detail: str = ""

    @property
    def glyph(self) -> str:
        return {"ok": "✓", "info": "·", "warning": "⚠", "error": "✗"}[self.level]


@dataclass
class DoctorReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def errors(self) -> list[CheckResult]:
        return [c for c in self.checks if c.level == "error"]

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if c.level == "warning"]

    @property
    def healthy(self) -> bool:
        return not self.errors

    @property
    def verdict(self) -> str:
        if self.errors:
            return "broken"
        if self.warnings:
            return "needs attention"
        return "healthy"

    def render(self) -> str:
        lines = [f"sov doctor · verdict: {self.verdict}", ""]
        for c in self.checks:
            lines.append(f"  {c.glyph} {c.name:<28}  {c.summary}")
            if c.detail and c.level in ("warning", "error"):
                for ln in c.detail.split("\n"):
                    if ln.strip():
                        lines.append(f"      {ln.rstrip()}")
        if self.errors:
            lines.append("")
            lines.append(f"  {len(self.errors)} error(s) need attention.")
        elif self.warnings:
            lines.append("")
            lines.append(f"  {len(self.warnings)} warning(s) noted; "
                         "Aria is functional.")
        else:
            lines.append("")
            lines.append("  All systems nominal.")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "healthy": self.healthy,
            "checks": [
                {"name": c.name, "level": c.level, "summary": c.summary,
                 "detail": c.detail}
                for c in self.checks
            ],
        }


# ─── Individual checks ────────────────────────────────────────────────────


def check_python() -> CheckResult:
    v = sys.version_info
    if v < (3, 10):
        return CheckResult(
            name="python version", level="error",
            summary=f"{v.major}.{v.minor}.{v.micro}",
            detail="Aria requires Python 3.10 or newer.",
        )
    return CheckResult(
        name="python version", level="ok",
        summary=f"{v.major}.{v.minor}.{v.micro}",
    )


def check_installed_version() -> CheckResult:
    try:
        from . import __version__
    except ImportError:
        return CheckResult(
            name="installed version", level="error",
            summary="could not import sovereign_agent",
        )
    return CheckResult(
        name="installed version", level="ok",
        summary=__version__,
    )


def check_executable_path() -> CheckResult:
    """Where is `sovereign` on PATH? Is it the one we think it is?"""
    sov_path = shutil.which("sovereign")
    if not sov_path:
        return CheckResult(
            name="sovereign on PATH", level="error",
            summary="not found",
            detail="`sovereign` is not on $PATH. The package may not be installed, "
                   "or your shell PATH doesn't include the install location.",
        )
    # Check sov alias
    sov_short = shutil.which("sov")
    detail = f"path: {sov_path}"
    if sov_short and sov_short != sov_path:
        detail += f"\nsov alias: {sov_short}"
    return CheckResult(
        name="sovereign on PATH", level="ok",
        summary=sov_path,
        detail=detail,
    )


def check_data_dir() -> CheckResult:
    try:
        from .config import SETTINGS
        data_dir = SETTINGS.paths.data_dir
    except Exception as e:
        return CheckResult(
            name="data dir", level="error",
            summary=f"could not resolve: {e}",
        )
    if not data_dir.exists():
        return CheckResult(
            name="data dir", level="warning",
            summary=f"missing: {data_dir}",
            detail="Will be created on first write.",
        )
    if not os.access(data_dir, os.W_OK):
        return CheckResult(
            name="data dir", level="error",
            summary=f"not writable: {data_dir}",
        )
    # Compute size
    total = 0
    for p in data_dir.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    size_str = _format_bytes(total)
    return CheckResult(
        name="data dir", level="ok",
        summary=f"{data_dir}  ({size_str})",
    )


def check_config_dir() -> CheckResult:
    try:
        from .config import SETTINGS
        config_dir = SETTINGS.paths.config_dir
    except Exception as e:
        return CheckResult(
            name="config dir", level="error",
            summary=f"could not resolve: {e}",
        )
    if not config_dir.exists():
        return CheckResult(
            name="config dir", level="info",
            summary=f"missing: {config_dir}",
            detail="Will be created on first config write.",
        )
    return CheckResult(
        name="config dir", level="ok",
        summary=str(config_dir),
    )


def check_atoms_db() -> CheckResult:
    try:
        from .config import SETTINGS
        atoms_path = SETTINGS.paths.atoms_db
    except Exception as e:
        return CheckResult(
            name="atoms.db", level="error",
            summary=f"could not resolve path: {e}",
        )
    if not atoms_path.is_file():
        return CheckResult(
            name="atoms.db", level="info",
            summary=f"not yet created: {atoms_path}",
            detail="Will be created on first channel write.",
        )
    try:
        size = atoms_path.stat().st_size
    except OSError as e:
        return CheckResult(
            name="atoms.db", level="error",
            summary=f"stat failed: {e}",
        )
    try:
        conn = sqlite3.connect(str(atoms_path))
        result = conn.execute("PRAGMA integrity_check").fetchone()
        atom_count = conn.execute("SELECT COUNT(*) FROM atoms").fetchone()[0]
        conn.close()
    except sqlite3.Error as e:
        return CheckResult(
            name="atoms.db", level="error",
            summary=f"sqlite error: {e}",
        )
    if result[0] != "ok":
        return CheckResult(
            name="atoms.db", level="error",
            summary="integrity check failed",
            detail=result[0],
        )
    return CheckResult(
        name="atoms.db", level="ok",
        summary=f"{_format_bytes(size)} · {atom_count:,} atoms · integrity ok",
    )


def check_migrations() -> CheckResult:
    """Are all expected migrations applied?"""
    try:
        from .config import SETTINGS
        from .migrations import (
            status, register_sql_dir, applied_migrations,
            detect_applied, ensure_migrations_table,
        )
    except ImportError as e:
        return CheckResult(
            name="migrations", level="error",
            summary=f"could not load migration framework: {e}",
        )
    atoms_path = SETTINGS.paths.atoms_db
    if not atoms_path.is_file():
        return CheckResult(
            name="migrations", level="info",
            summary="atoms.db not yet created",
        )
    try:
        sql_dir = Path(__file__).parent.parent.parent / "sql"
        register_sql_dir(sql_dir)
        conn = sqlite3.connect(str(atoms_path))
        ensure_migrations_table(conn)
        applied = applied_migrations(conn)
        detected = detect_applied(conn)
        conn.close()
    except sqlite3.Error as e:
        return CheckResult(
            name="migrations", level="error",
            summary=f"sqlite error: {e}",
        )
    items = status(conn) if False else []  # don't re-open
    # Migrations whose schema is present but not recorded → backfill needed
    needs_backfill = detected - applied
    if needs_backfill:
        return CheckResult(
            name="migrations", level="warning",
            summary=f"{len(needs_backfill)} migration(s) need backfill",
            detail=("Run `sov migrations backfill` to mark them applied "
                    "without re-running their SQL.\n"
                    "Backfill candidates: " + ", ".join(sorted(needs_backfill))),
        )
    return CheckResult(
        name="migrations", level="ok",
        summary=f"{len(applied)} applied",
    )


def check_channels() -> CheckResult:
    """Are all expected channels registered?"""
    try:
        from . import mem_channels  # noqa: F401  (triggers registration)
        from .channels import list_channels
    except ImportError as e:
        return CheckResult(
            name="channels", level="error",
            summary=f"could not import channels: {e}",
        )
    expected_v0218 = {
        "context", "emotions", "episodes", "financial", "goals", "humor",
        "identity", "insights", "intention", "intuition", "lessons",
        "people", "personalities", "recall", "reward", "ritual",
        "specialist", "task", "trust",
        # v0.2.18 additions:
        "reasoning", "gaps", "relationships", "commitments", "heartbeat",
        # people-health-privacy-d:
        "people_health",
    }
    registered = {spec.name for spec in list_channels()}
    missing = expected_v0218 - registered
    if missing:
        return CheckResult(
            name="channels", level="error",
            summary=f"{len(registered)} registered, {len(missing)} missing",
            detail="missing: " + ", ".join(sorted(missing)),
        )
    return CheckResult(
        name="channels", level="ok",
        summary=f"all {len(registered)} channels registered",
    )


def check_aegis() -> CheckResult:  # bloodwork-d
    """Ensure the aegis subsystem's persistent surface exists (dir,
    ledger, signing key). Idempotent bootstrap + report — clears the
    locator sentinel's alert-criticality aegis_dir finding honestly."""
    try:
        from .config import SETTINGS
        from .aegis.bootstrap import ensure_aegis_bootstrap

        info = ensure_aegis_bootstrap(SETTINGS.paths.data_dir)
    except Exception as e:  # noqa: BLE001
        return CheckResult(
            name="aegis", level="error",
            summary=f"bootstrap failed: {e}",
        )
    return CheckResult(
        name="aegis", level="ok",
        summary=f"initialized at {info['aegis_dir']}",
    )


def check_disk_space() -> CheckResult:
    try:
        from .config import SETTINGS
        target = SETTINGS.paths.data_dir
    except Exception:
        target = Path.home()
    try:
        stat = shutil.disk_usage(target if target.exists() else target.parent)
    except OSError as e:
        return CheckResult(
            name="disk space", level="warning",
            summary=f"could not stat: {e}",
        )
    if stat.free < 100 * 1024 * 1024:   # < 100 MB
        return CheckResult(
            name="disk space", level="warning",
            summary=f"low: {_format_bytes(stat.free)} free",
            detail="Aria may fail to write atoms; clear space soon.",
        )
    return CheckResult(
        name="disk space", level="ok",
        summary=f"{_format_bytes(stat.free)} free",
    )


def check_charter_integrity() -> CheckResult:
    """SIGNAL.md integrity — the load-bearing check for Article V (kill switch).

    Defers entirely to the charter module so the same verdict drives the
    doctor display AND the CLI dispatch gate.

    Levels:
      - ok       : charter present, hash verified, YAML consistent
      - warning  : charter file absent (pre-charter migration window)
      - error    : charter present but tampered — kill switch fires
    """
    from . import charter as _charter
    verdict = _charter.check_integrity()
    detail = verdict.detail
    if verdict.kill_switch_active:
        detail = (detail + "\n\n" if detail else "") + (
            "KILL SWITCH ACTIVE: CLI will refuse to dispatch anything except\n"
            "  `sov doctor` and `sov charter` until this is resolved."
        )
    return CheckResult(
        name="charter (SIGNAL.md)",
        level=verdict.level,
        summary=verdict.summary,
        detail=detail,
    )


def check_sentinels_roster() -> CheckResult:
    """Aggregate health from the sentinel registry.

    A surface for every sentinel that's signed up to the unified framework
    (stewardship/base.py + registry.py). Reports the worst level any
    sentinel reports.
    """
    try:
        from .stewardship import registry as _reg
        from .config import SETTINGS
    except ImportError:
        return CheckResult(
            name="sentinels", level="info",
            summary="sentinel framework unavailable",
        )
    healths = _reg.gather_health(SETTINGS.paths.data_dir)
    if not healths:
        return CheckResult(
            name="sentinels", level="info",
            summary="no sentinels registered yet",
        )
    levels = [h.level for h in healths]
    err = sum(1 for L in levels if L == "error")
    warn = sum(1 for L in levels if L == "warning")
    ok = sum(1 for L in levels if L == "ok")
    # sentinel-warnings-detail-d (Kevin, 2026-07-25): list EVERY flagged
    # sentinel, not just the first — "which 3?" must be answerable from
    # this same call, not require a separate lookup.
    all_flagged = _reg.list_sentinel_warnings(SETTINGS.paths.data_dir, limit=10)
    flagged_lines = "\n".join(
        f"  · {h.sentinel_id} ({h.level}) — {h.summary}" for h in all_flagged
    )
    if err > 0:
        return CheckResult(
            name="sentinels", level="error",
            summary=f"{err} sentinel(s) reporting errors · ok={ok} warn={warn}",
            detail=f"{flagged_lines}\n  Inspect: sov sentinels list",
        )
    if warn > 0:
        return CheckResult(
            name="sentinels", level="warning",
            summary=f"{warn} sentinel(s) reporting warnings · ok={ok}",
            detail=flagged_lines,
        )
    return CheckResult(
        name="sentinels", level="ok",
        summary=f"{ok} sentinel(s) reporting clean",
        detail=f"surfaces: {', '.join(h.sentinel_id for h in healths)}",
    )


def check_glyph_catalog() -> CheckResult:
    """Surface the most-recent glyph sentinel verdict.

    If unsafe glyphs with known replacements exist, doctor reports a
    warning telling the operator to inspect `sov glyphs proposals`.
    """
    try:
        from .stewardship import glyph_sentinel as _gs
    except ImportError:
        return CheckResult(
            name="glyph catalog", level="info",
            summary="sentinel module unavailable",
        )
    from .config import SETTINGS
    catalog = _gs.load_catalog(SETTINGS.paths.data_dir)
    if catalog is None:
        return CheckResult(
            name="glyph catalog", level="info",
            summary="no catalog (run `sov glyphs scan`)",
        )
    # Use generate_proposals so protected files (glyphs.py, test_*) don't
    # inflate the warning. The doctor surfaces ACTIONABLE work, not theoretical.
    actionable = len(_gs.generate_proposals(catalog))
    if actionable > 0:
        return CheckResult(
            name="glyph catalog", level="warning",
            summary=f"{actionable} unsafe glyph occurrence(s) with known safe replacement",
            detail=(
                f"safe={catalog.safe_count}  borderline={catalog.borderline_count}  "
                f"unsafe={catalog.unsafe_count}\n"
                f"  Inspect: sov glyphs proposals\n"
                f"  Refresh: sov glyphs scan"
            ),
        )
    return CheckResult(
        name="glyph catalog", level="ok",
        summary=(
            f"{len(catalog.glyphs)} unique glyph(s) cataloged · "
            f"safe={catalog.safe_count} borderline={catalog.borderline_count} unsafe={catalog.unsafe_count}"
        ),
        detail=f"last scan: {catalog.generated_at}",
    )


def check_aria_md() -> CheckResult:
    """Is ARIA.md present in the install? Without it, the kernel's identity
    is undocumented in-tree (the file is the canonical statement of who she is)."""
    # Look in the package's parent directory (the source repo for editable installs)
    candidates = [
        Path(__file__).parent.parent.parent / "ARIA.md",
        Path.cwd() / "ARIA.md",
    ]
    for p in candidates:
        if p.is_file():
            size = p.stat().st_size
            return CheckResult(
                name="ARIA.md", level="ok",
                summary=f"{p}  ({_format_bytes(size)})",
            )
    return CheckResult(
        name="ARIA.md", level="warning",
        summary="not found near install root",
        detail="The kernel document defines Aria's identity. "
               "It should ship with the source tree.",
    )


def check_seven_commitments() -> CheckResult:
    try:
        from .constitution import list_all
        items = list_all()
    except ImportError as e:
        return CheckResult(
            name="constitution", level="error",
            summary=f"could not import: {e}",
        )
    if len(items) != 7:
        return CheckResult(
            name="constitution", level="error",
            summary=f"expected 7 commitments, found {len(items)}",
        )
    with_check = [c for c in items if c.check is not None]
    return CheckResult(
        name="constitution", level="ok",
        summary=f"7 commitments · {len(with_check)} with runtime checks",
    )


def check_dependencies() -> CheckResult:
    """Key library versions."""
    try:
        import sqlite3
        sqlite_v = sqlite3.sqlite_version
    except ImportError:
        sqlite_v = "missing"
    bits = [f"sqlite={sqlite_v}"]
    for lib_name in ("typer", "rich", "pydantic", "httpx", "structlog"):
        try:
            mod = __import__(lib_name)
            ver = getattr(mod, "__version__", "unknown")
            bits.append(f"{lib_name}={ver}")
        except ImportError:
            bits.append(f"{lib_name}=missing")
    return CheckResult(
        name="dependencies", level="ok",
        summary=" ".join(bits),
    )


def check_install_layout() -> CheckResult:
    """Detect the install layout — managed uv venv, AA-Erebo symlink, or bare.

    Three layouts in the wild:

      1. Managed uv venv (current default, since the uv migration):
         ${XDG_DATA_HOME:-$HOME/.local/share}/sovereign-agent/venv/, with
         launcher shims in ~/.local/bin. This is what ``./install.sh`` writes.

      2. AA-Erebo symlink:
         ~/AA-Erebo/sovereign-agent-current → /path/to/version-dir/. Kevin's
         operator convention; orthogonal to the venv location.

      3. Bare:
         Neither of the above (legacy ``pip install --break-system-packages``
         installs, or operators running from a custom venv they manage themselves).
    """
    xdg_data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    managed_venv = xdg_data / "sovereign-agent" / "venv"
    erebo = Path.home() / "AA-Erebo"
    current = erebo / "sovereign-agent-current"

    bits: list[str] = []
    detail_lines: list[str] = []

    # Is the *current Python interpreter* running from the managed venv?
    # Use sys.prefix (the venv root) rather than resolving sys.executable,
    # because venvs symlink bin/python out to the system interpreter — a
    # resolved sys.executable points at the system path, not into the venv.
    py_prefix = Path(sys.prefix)
    py_exe = Path(sys.executable)
    in_managed = False
    try:
        py_prefix.relative_to(managed_venv)
        in_managed = True
    except ValueError:
        pass

    # Read the install-method marker if present. Written by install.sh —
    # contents are either "uv" (first-class, lockfile-deterministic) or
    # "pip-fallback" (degraded; lockfile not consulted).
    install_method: str | None = None
    method_file = managed_venv / ".install-method"
    if method_file.is_file():
        try:
            first_line = method_file.read_text(encoding="utf-8").splitlines()[0].strip()
            if first_line in {"uv", "pip-fallback"}:
                install_method = first_line
        except (OSError, IndexError):
            pass

    if in_managed:
        if install_method == "pip-fallback":
            bits.append("managed venv (pip fallback — degraded)")
        elif install_method == "uv":
            bits.append("managed venv (uv)")
        else:
            bits.append("managed venv (install method unknown)")
        detail_lines.append(f"venv: {managed_venv}")
        if install_method is not None:
            detail_lines.append(f"install method: {install_method}")
    elif managed_venv.exists():
        bits.append("managed venv present but interpreter is elsewhere")
        detail_lines.append(f"managed venv: {managed_venv}")
        detail_lines.append(f"running from: {py_prefix}")
        if install_method is not None:
            detail_lines.append(f"install method (last recorded): {install_method}")

    if current.is_symlink():
        target = current.resolve()
        bits.append(f"symlink → {target.name}")
        detail_lines.append(f"sovereign-agent-current → {target}")

    if not bits:
        return CheckResult(
            name="install layout", level="info",
            summary="bare install (no managed venv, no symlink)",
            detail=f"running from: {py_prefix}",
        )

    # Degrade the level when the install was via pip-fallback — that's not
    # broken, but it's not the lockfile-deterministic happy path either.
    level: CheckLevel = "warning" if (in_managed and install_method == "pip-fallback") else "ok"
    return CheckResult(
        name="install layout", level=level,
        summary=" · ".join(bits),
        detail="\n".join(detail_lines),
    )


def check_uv() -> CheckResult:
    """Report uv presence and version. uv is the install path of record."""
    uv_bin = shutil.which("uv")
    if uv_bin is None:
        return CheckResult(
            name="uv", level="warning",
            summary="uv not on PATH",
            detail="Install uv:  curl -LsSf https://astral.sh/uv/install.sh | sh",
        )
    try:
        import subprocess
        out = subprocess.run(
            [uv_bin, "--version"], capture_output=True, text=True, timeout=3, check=False,
        )
        ver = out.stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        ver = "unknown"
    return CheckResult(name="uv", level="ok", summary=ver, detail=f"binary: {uv_bin}")


def check_lockfile() -> CheckResult:
    """Detect whether the source tree has a uv.lock alongside pyproject.toml.

    Operators who installed from a release tarball should have a lockfile —
    its absence means resolution was non-reproducible.
    """
    # Find the source tree: walk up from this module's location.
    here = Path(__file__).resolve()
    src_root: Path | None = None
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").is_file():
            src_root = parent
            break
    if src_root is None:
        return CheckResult(
            name="uv.lock", level="info",
            summary="source tree not detected (non-editable install)",
        )
    lockfile = src_root / "uv.lock"
    if lockfile.is_file():
        size_kb = lockfile.stat().st_size / 1024
        return CheckResult(
            name="uv.lock", level="ok",
            summary=f"present ({size_kb:.0f} KB)",
            detail=f"path: {lockfile}",
        )
    return CheckResult(
        name="uv.lock", level="warning",
        summary="missing — resolution was not reproducible",
        detail=f"expected at: {lockfile}",
    )


def _format_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n}B"


# ─── Ollama checks (v0.2.26.0) ────────────────────────────────────────────
#
# Both checks below are added in response to a real operator failure mode:
# the interpreter slot's default (phi-4-mini:3.8b) was set to a model the
# operator didn't have pulled, so every chat turn returned "interpreter
# offline" with no clue why. `sov doctor` should be the place that catches
# this kind of config/library mismatch BEFORE the operator hits it in chat.
#
# Both checks are Tier 0: pure reads, no model pulls, no service starts.
# They run synchronously inside the diagnostic driver using asyncio.run().


def check_ollama_daemon() -> CheckResult:
    """Is the Ollama daemon reachable at the configured host?"""
    try:
        import asyncio
        from .config import SETTINGS
        from .ollama_client import probe_ollama
    except ImportError as exc:
        return CheckResult(
            name="ollama daemon", level="error",
            summary=f"could not import probe: {exc}",
        )

    try:
        status = asyncio.run(probe_ollama(SETTINGS.ollama_host))
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="ollama daemon", level="error",
            summary=f"probe failed: {type(exc).__name__}",
            detail=str(exc),
        )

    if not status.daemon_reachable:
        return CheckResult(
            name="ollama daemon", level="error",
            summary=f"unreachable at {status.host}",
            detail=(
                f"{status.error or 'no daemon response'}\n"
                f"Try: ollama serve   (or: systemctl --user start ollama)\n"
                f"If the daemon is on a different host, set OLLAMA_HOST."
            ),
        )

    n = len(status.available_models)
    return CheckResult(
        name="ollama daemon", level="ok",
        summary=f"reachable at {status.host} · {n} model(s) listed",
    )


def check_ollama_models() -> CheckResult:
    """Are all configured model slots present in the local library?

    Reports one CheckResult covering every slot. Missing slots are an
    error; a slot configured to a pulled model is an info row in detail.
    """
    try:
        import asyncio
        from .config import SETTINGS
        from .ollama_client import probe_ollama
    except ImportError as exc:
        return CheckResult(
            name="ollama models", level="error",
            summary=f"could not import probe: {exc}",
        )

    # The full slot map. Vision is optional — the image-inventory planner is
    # the only consumer and most operators never invoke it.
    slots: list[tuple[str, str, bool]] = [
        ("interpreter", SETTINGS.interpreter_model, True),
        ("orchestrator", SETTINGS.orchestrator_model, True),
        ("coder", SETTINGS.coder_model, True),
        ("fast", SETTINGS.fast_model, True),
        ("reflector", SETTINGS.reflector_model, True),
        ("embed", SETTINGS.embed_model, True),
        ("vision", SETTINGS.vision_model, False),
    ]

    try:
        status = asyncio.run(probe_ollama(SETTINGS.ollama_host))
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="ollama models", level="error",
            summary=f"probe failed: {type(exc).__name__}",
            detail=str(exc),
        )

    if not status.daemon_reachable:
        return CheckResult(
            name="ollama models", level="warning",
            summary="cannot verify — daemon unreachable",
            detail="See the 'ollama daemon' check above.",
        )

    def _norm(n: str) -> str:
        return n if ":" in n else f"{n}:latest"

    available_norm = {_norm(n) for n in status.available_models}

    missing_required: list[tuple[str, str]] = []
    missing_optional: list[tuple[str, str]] = []
    present: list[tuple[str, str]] = []

    for slot_name, model, required in slots:
        if not model:
            continue
        if _norm(model) in available_norm:
            present.append((slot_name, model))
        elif required:
            missing_required.append((slot_name, model))
        else:
            missing_optional.append((slot_name, model))

    if missing_required:
        bullets = [f"✗ {s:<13} {m}  (run: ollama pull {m})"
                   for s, m in missing_required]
        bullets += [f"⚠ {s:<13} {m}  (optional — pull if you need it)"
                    for s, m in missing_optional]
        bullets += [f"✓ {s:<13} {m}" for s, m in present]
        return CheckResult(
            name="ollama models", level="error",
            summary=(
                f"{len(missing_required)} required slot(s) point at "
                f"un-pulled model(s)"
            ),
            detail="\n".join(bullets),
        )

    if missing_optional:
        bullets = [f"⚠ {s:<13} {m}  (optional)" for s, m in missing_optional]
        bullets += [f"✓ {s:<13} {m}" for s, m in present]
        return CheckResult(
            name="ollama models", level="warning",
            summary=f"{len(missing_optional)} optional slot(s) un-pulled",
            detail="\n".join(bullets),
        )

    return CheckResult(
        name="ollama models", level="ok",
        summary=f"all {len(present)} configured slot(s) present",
    )


# ─── Driver ───────────────────────────────────────────────────────────────


def run_diagnostic() -> DoctorReport:
    """Run every check and assemble a report."""
    report = DoctorReport()
    report.checks.append(check_python())
    report.checks.append(check_uv())
    report.checks.append(check_installed_version())
    report.checks.append(check_executable_path())
    report.checks.append(check_install_layout())
    report.checks.append(check_lockfile())
    report.checks.append(check_config_dir())
    report.checks.append(check_data_dir())
    report.checks.append(check_atoms_db())
    report.checks.append(check_migrations())
    report.checks.append(check_channels())
    report.checks.append(check_seven_commitments())
    report.checks.append(check_aria_md())
    report.checks.append(check_charter_integrity())
    report.checks.append(check_glyph_catalog())
    report.checks.append(check_sentinels_roster())
    report.checks.append(check_dependencies())
    report.checks.append(check_aegis())  # bloodwork-d
    report.checks.append(check_disk_space())
    report.checks.append(check_ollama_daemon())
    report.checks.append(check_ollama_models())
    return report


__all__ = [
    "CheckResult", "CheckLevel", "DoctorReport",
    "run_diagnostic",
    "check_python", "check_uv", "check_installed_version", "check_executable_path",
    "check_install_layout", "check_lockfile", "check_data_dir", "check_config_dir",
    "check_atoms_db", "check_migrations", "check_channels",
    "check_seven_commitments", "check_aria_md", "check_charter_integrity",
    "check_glyph_catalog", "check_sentinels_roster",
    "check_dependencies",
    "check_aegis",
    "check_disk_space",
    "check_ollama_daemon", "check_ollama_models",
]
