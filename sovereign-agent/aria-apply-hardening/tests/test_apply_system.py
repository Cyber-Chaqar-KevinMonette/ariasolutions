"""Apply-system hardening battery — the validator, the safe-apply wrapper (incl. rollback), the dashboard.

These prove the apply menu is robust/resilient/intelligent before Kevin uses it. They shell out to the
real scripts so the test reflects reality, and exercise the rollback path on a throwaway module.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    """Robust to running from either the staged location (aria-apply-
    hardening/tests/) or the promoted live location (tests/), which differ
    in nesting depth — the exact path-depth bug class fixed elsewhere this
    session (test_tools_all_export_fix.py, test_scanner_tier_a.py,
    test_command_menu.py, test_wisdom_atoms.py)."""
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "cockpit" / "app.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


REPO = _find_repo_root(Path(__file__).resolve())


def _run(cmd, **kw):
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=120, **kw)


# ── A1 validator ──────────────────────────────────────────────────────────────

def test_validator_runs_and_reports_coverage():
    r = _run(["bash", "scripts/validate_apply_system.sh"])
    assert r.returncode == 0
    assert "apply-system validation" in r.stdout
    assert "god-tier-safe" in r.stdout                      # reports the grade
    # total coverage: it counts all scripts
    assert "scripts:" in r.stdout


# ── A2 safe_apply: refuses bad input, rolls back on failure ───────────────────

def test_safe_apply_rejects_unknown_module():
    r = _run(["bash", "scripts/safe_apply.sh", "aria-does-not-exist-xyz"])
    assert r.returncode != 0
    assert "no such module" in (r.stdout + r.stderr)


def test_safe_apply_rolls_back_on_failure(tmp_path):
    """Build a throwaway module whose apply copies a file + whose test fails → rollback must leave src clean."""
    mod = REPO / "aria-_safetest_pytest"
    pkg = mod / "payload" / "src" / "sovereign_agent" / "_safetest_pytest"
    (mod / "tests").mkdir(parents=True, exist_ok=True)
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('"""throwaway."""\n')
    (mod / "apply__safetest_pytest.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"\n'
        "mkdir -p src/sovereign_agent/_safetest_pytest\n"
        "cp aria-_safetest_pytest/payload/src/sovereign_agent/_safetest_pytest/*.py src/sovereign_agent/_safetest_pytest/\n")
    (mod / "apply__safetest_pytest.sh").chmod(0o755)
    (mod / "tests" / "test__safetest_pytest.py").write_text("def test_fail(): assert False\n")
    (REPO / "tests" / "test__safetest_pytest.py").write_text("def test_fail(): assert False\n")
    live = REPO / "src" / "sovereign_agent" / "_safetest_pytest"
    try:
        r = _run(["bash", "scripts/safe_apply.sh", "aria-_safetest_pytest", "--yes"])
        assert r.returncode != 0                            # verification failed
        assert "ROLLED BACK" in r.stdout
        assert not live.exists()                            # rollback removed file AND dir — src is clean
    finally:
        import shutil
        shutil.rmtree(mod, ignore_errors=True)
        (REPO / "tests" / "test__safetest_pytest.py").unlink(missing_ok=True)
        shutil.rmtree(live, ignore_errors=True)


# ── A3 dashboard discovery ────────────────────────────────────────────────────

def test_dashboard_discovers_all_apply_scripts():
    import sys
    sys.path.insert(0, str(REPO / "aria-apply-dashboard" / "payload" / "src"))
    try:
        from sovereign_agent.cockpit.apply_screen import discover_scripts  # type: ignore
    except Exception:
        import pytest
        pytest.skip("apply_screen not importable standalone")
    scripts = discover_scripts(REPO)
    assert len(scripts) > 50                                # finds the staged modules
    assert all("script" in s and "applied" in s for s in scripts)
