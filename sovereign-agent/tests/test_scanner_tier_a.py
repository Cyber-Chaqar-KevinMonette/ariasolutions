"""Behavior tests for aria-scanner-tier-a — prove each of the 6 Tier-A scanners
catches the defect it claims to, AND stays quiet on clean code. Same precision
discipline as D's path_scan: never cry wolf."""
from __future__ import annotations

from pathlib import Path

from sovereign_agent.scanner_tier_a import (
    scan_all_exports,
    scan_anchor_integrity,
    scan_authority_tier_drift,
    scan_bare_except,
    scan_import_cycles,
    scan_mutable_defaults,
    scan_secrets,
)


# ─── 1. secret-leak ─────────────────────────────────────────────────────────

def test_secret_leak_catches_api_key():
    findings = scan_secrets('API_KEY = "sk1234567890abcdefghijklmno"\n', rel_path="x.py")
    assert any(f.kind == "secret-leak" for f in findings)


def test_secret_leak_catches_aws_key_shape():
    findings = scan_secrets('KEY = "AKIAABCDEFGHIJKLMNOP"\n', rel_path="x.py")
    assert any(f.severity == "block" for f in findings)


def test_secret_leak_catches_private_key_block():
    findings = scan_secrets("-----BEGIN RSA PRIVATE KEY-----\n", rel_path="x.py")
    assert any(f.kind == "secret-leak" for f in findings)


def test_secret_leak_stays_quiet_on_placeholder():
    findings = scan_secrets('API_KEY = "changeme_replace_this_value"\n', rel_path="x.py")
    assert findings == []


def test_secret_leak_stays_quiet_on_clean_code():
    findings = scan_secrets('def f(x):\n    return x + 1\n', rel_path="x.py")
    assert findings == []


def test_secret_leak_allow_pragma_exempts():
    findings = scan_secrets('KEY = "AKIAABCDEFGHIJKLMNOP"  # scanner-tier-a: allow\n', rel_path="x.py")
    assert findings == []


# ─── 2. anchor-integrity ────────────────────────────────────────────────────

def test_anchor_integrity_catches_a_dangling_anchor(tmp_path):
    mod = tmp_path / "aria-ghost"
    mod.mkdir()
    (mod / "apply_ghost.sh").write_text(
        '#!/bin/bash\n# references an anchor that will never exist\n'
        'echo "# totally-fake-import-d"\n', encoding="utf-8",
    )
    (tmp_path / "src" / "sovereign_agent" / "tools").mkdir(parents=True)
    (tmp_path / "src" / "sovereign_agent" / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "sovereign_agent" / "stewardship").mkdir(parents=True)
    (tmp_path / "src" / "sovereign_agent" / "stewardship" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "sovereign_agent" / "cockpit").mkdir(parents=True)
    (tmp_path / "src" / "sovereign_agent" / "cockpit" / "app.py").write_text("", encoding="utf-8")

    findings = scan_anchor_integrity(tmp_path)
    assert any(f.kind == "anchor-integrity/dangling" for f in findings)


def test_anchor_integrity_stays_quiet_when_anchor_present(tmp_path):
    mod = tmp_path / "aria-real"
    mod.mkdir()
    (mod / "apply_real.sh").write_text(
        '#!/bin/bash\necho "# real-import-d"\n', encoding="utf-8",
    )
    (tmp_path / "src" / "sovereign_agent" / "tools").mkdir(parents=True)
    (tmp_path / "src" / "sovereign_agent" / "tools" / "__init__.py").write_text(
        "# real-import-d\n", encoding="utf-8",
    )
    (tmp_path / "src" / "sovereign_agent" / "stewardship").mkdir(parents=True)
    (tmp_path / "src" / "sovereign_agent" / "stewardship" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "sovereign_agent" / "cockpit").mkdir(parents=True)
    (tmp_path / "src" / "sovereign_agent" / "cockpit" / "app.py").write_text("", encoding="utf-8")

    findings = scan_anchor_integrity(tmp_path)
    assert findings == []


def test_scan_all_exports_catches_missing_export():
    src = (
        "from .foo_tool import FooTool\n"
        "__all__ = []\n"
    )
    findings = scan_all_exports(src)
    assert any("FooTool" in f.message for f in findings)


def test_scan_all_exports_stays_quiet_when_exported():
    src = (
        "from .foo_tool import FooTool\n"
        '__all__ = ["FooTool"]\n'
    )
    findings = scan_all_exports(src)
    assert findings == []


def test_scan_all_exports_catches_the_real_historical_bug():
    """Regression fixture: the exact bug found in aria-tools-all-export-fix —
    6 calibration/honor-log/self-portrait tools imported but not exported."""
    src = (
        "from .calibration_tools import LogPredictionTool, ResolvePredictionTool\n"
        "from .honor_log_tool import HonorLogReadTool\n"
        '__all__ = ["SomeOtherTool"]\n'
    )
    findings = scan_all_exports(src)
    missing = {f.message.split("'")[1] for f in findings}
    assert missing == {"LogPredictionTool", "ResolvePredictionTool", "HonorLogReadTool"}


# ─── 3. import-cycle ────────────────────────────────────────────────────────

def test_import_cycle_catches_a_real_cycle(tmp_path):
    src_root = tmp_path / "src" / "sovereign_agent"
    (src_root / "a").mkdir(parents=True)
    (src_root / "a" / "__init__.py").write_text("", encoding="utf-8")
    (src_root / "a" / "mod1.py").write_text("from sovereign_agent.a.mod2 import x\n", encoding="utf-8")
    (src_root / "a" / "mod2.py").write_text("from sovereign_agent.a.mod1 import y\n", encoding="utf-8")

    findings = scan_import_cycles(src_root)
    assert any(f.kind == "import-cycle" for f in findings)


def test_import_cycle_stays_quiet_on_acyclic_imports(tmp_path):
    src_root = tmp_path / "src" / "sovereign_agent"
    (src_root / "a").mkdir(parents=True)
    (src_root / "a" / "__init__.py").write_text("", encoding="utf-8")
    (src_root / "a" / "mod1.py").write_text("from sovereign_agent.a.mod2 import x\n", encoding="utf-8")
    (src_root / "a" / "mod2.py").write_text("x = 1\n", encoding="utf-8")

    findings = scan_import_cycles(src_root)
    assert findings == []


# ─── 4. authority-tier-drift ─────────────────────────────────────────────────

def test_authority_tier_drift_catches_tier3_without_approval():
    src = 'ToolMeta(name="x", tier=3, description="d", failure_modes=("e",))\n'
    findings = scan_authority_tier_drift(src, rel_path="x.py")
    assert any(f.kind == "authority-tier-drift" for f in findings)


def test_authority_tier_drift_stays_quiet_when_approval_declared():
    src = ('ToolMeta(name="x", tier=3, description="d", requires_approval=True, '
           'failure_modes=("e",))\n')
    findings = scan_authority_tier_drift(src, rel_path="x.py")
    assert findings == []


def test_authority_tier_drift_stays_quiet_for_tier0():
    src = 'ToolMeta(name="x", tier=0, description="d", failure_modes=("e",))\n'
    findings = scan_authority_tier_drift(src, rel_path="x.py")
    assert findings == []


# ─── 5. bare-except ──────────────────────────────────────────────────────────

def test_bare_except_catches_naked_except():
    findings = scan_bare_except("try:\n    f()\nexcept:\n    pass\n", rel_path="x.py")
    assert any(f.kind == "bare-except" for f in findings)


def test_bare_except_catches_swallowed_exception():
    findings = scan_bare_except("try:\n    f()\nexcept Exception:\n    pass\n", rel_path="x.py")
    assert any(f.kind == "bare-except" for f in findings)


def test_bare_except_stays_quiet_when_exception_is_handled():
    findings = scan_bare_except(
        "try:\n    f()\nexcept Exception as exc:\n    log(exc)\n    raise\n", rel_path="x.py",
    )
    assert findings == []


def test_bare_except_allow_pragma_exempts():
    findings = scan_bare_except(
        "try:\n    f()\nexcept:  # scanner-tier-a: allow\n    pass\n", rel_path="x.py",
    )
    assert findings == []


# ─── 6. mutable-default-arg ──────────────────────────────────────────────────

def test_mutable_default_catches_list_default():
    findings = scan_mutable_defaults("def f(x=[]):\n    return x\n", rel_path="x.py")
    assert any(f.kind == "mutable-default-arg" for f in findings)


def test_mutable_default_catches_dict_default():
    findings = scan_mutable_defaults("def f(x={}):\n    return x\n", rel_path="x.py")
    assert any(f.kind == "mutable-default-arg" for f in findings)


def test_mutable_default_stays_quiet_on_none_default():
    findings = scan_mutable_defaults("def f(x=None):\n    return x or []\n", rel_path="x.py")
    assert findings == []


def test_mutable_default_stays_quiet_on_immutable_defaults():
    findings = scan_mutable_defaults("def f(x=1, y='a', z=(1, 2)):\n    return x\n", rel_path="x.py")
    assert findings == []


# ─── self-scan sanity: the module doesn't flag its own pattern table ────────

def test_scanner_does_not_self_flag_on_its_own_source():
    """Robust to running from either the staged location (aria-scanner-tier-a/
    tests/) or the final live location (tests/), which differ in nesting depth —
    find the actual installed module via its own __file__ instead of assuming
    a fixed relative path."""
    import sovereign_agent.scanner_tier_a.scanner as _scanner_mod

    this_file = Path(_scanner_mod.__file__).resolve()
    text = this_file.read_text(encoding="utf-8")
    findings = scan_secrets(text, rel_path="scanner.py")
    assert findings == [], [f.excerpt for f in findings]
