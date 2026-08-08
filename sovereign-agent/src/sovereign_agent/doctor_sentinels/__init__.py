"""Aria's self-healing surface — the SovDoctor sentinels.

Renamed from ``doctor/`` to ``doctor_sentinels/`` so it no longer shadows
the top-level ``doctor.py`` module (the ``sov doctor`` environment/install
diagnostic that defines ``run_diagnostic``/``check_*``). A package named
``doctor`` next to a module named ``doctor.py`` makes the package win on
import, which silently broke ``from .doctor import run_diagnostic``. The two
are complementary: ``doctor.py`` diagnoses; this surface heals.

R0 (her own data_dir, venv, build artifacts): autonomously cleanable.
R2+ (operator's shell, system state): report-only, never modified.

v0.2.39.1 adds filesystem-level ghost-venv detection that works
regardless of launcher (UV strips VIRTUAL_ENV from child processes,
so the env-var detector is blind under uv run).
"""
from sovereign_agent.doctor_sentinels.doctor import (
    SovDoctor, DoctorIssue, HealAction,
    IssueKind, Scope, Severity,
    LEGACY_VENV_LOCATIONS,
)

__all__ = [
    "SovDoctor", "DoctorIssue", "HealAction",
    "IssueKind", "Scope", "Severity",
    "LEGACY_VENV_LOCATIONS",
]
