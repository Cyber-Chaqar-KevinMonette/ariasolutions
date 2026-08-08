"""sovereign_agent.security — Aria's DEFENSIVE immune system.

Incident response for her own machine: detect tampering of her crown jewels, alert, quarantine for
analysis, and reversibly heal from verified backups. No offensive capability — defense only.
"""
from .immune import (
    crown_jewels, record_baseline, check_integrity, quarantine, heal_from_backup,
)

__all__ = ["crown_jewels", "record_baseline", "check_integrity", "quarantine", "heal_from_backup"]
