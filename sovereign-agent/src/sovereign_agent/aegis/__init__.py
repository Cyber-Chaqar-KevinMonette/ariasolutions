"""
╔══════════════════════════════════════════════════════════════════════════╗
║  aegis — Aria's incident response plane                                   ║
║  v0.2.35.0 RC1 — "The Kernel"                                             ║
║                                                                           ║
║  Stewardship watches the work being done. Aegis watches the system that  ║
║  does the work. They share the fractal shape (manifest → catalogs →     ║
║  atoms, hash-bound) but their job is different. Stewardship is          ║
║  reflective. Aegis is defensive and reparative.                          ║
║                                                                           ║
║  Modules:                                                                 ║
║                                                                           ║
║    radius      — Blast radius taxonomy (R0..R5). Authority gate.        ║
║    incidents   — Typed records: Incident, DamageReport, RepairPlan,     ║
║                  DryRunReport, RepairResult, Evidence.                  ║
║    leases      — RepairLease + HMAC signing. Sentinels need a fresh,   ║
║                  signed, scoped, time-bounded lease to touch the       ║
║                  system. This is what stops sentinels from fighting.   ║
║    ledger      — Append-only, hash-chained incident log.               ║
║    defcon      — DEFCON state machine (GREEN/YELLOW/ORANGE/RED/BLACK). ║
║    medical     — MedicalCapability mixin every Sentinel composes in.   ║
║    bitemporal  — Two-axis time storage, append-only, Merkle-anchored. ║
║                  The substrate that makes "you cannot silently rewrite ║
║                  history" structural rather than aspirational.         ║
║    vault       — Encrypted out-of-band snapshot store (AES-256-GCM via ║
║                  cryptography lib, separate dir, separate key).        ║
║                  The real "lockdown and restore" mechanism.            ║
║    conductor   — The orchestrator. Singleton. Receives lockdown        ║
║                  requests, applies quorum rules, issues leases, owns   ║
║                  the dead-man's switch. The ONLY module whose          ║
║                  articles say "I direct other sentinels."              ║
║                                                                           ║
║  Doctrinal anchors:                                                      ║
║                                                                           ║
║    STANDARDS-CE-2026.05.24      — the master canon                     ║
║    DEFENSE-CATALOG-CE-2026.05.24 — threat taxonomy + postures          ║
║    PHANTOM-DOCTRINE-CE-2026.05.24 — canary/honey/decoy + Vault         ║
║    LOVE-DOCTRINE-CE-2026.05.24   — love-at-core as structural          ║
║                                    resilience                            ║
║                                                                           ║
║  Master kill switch:                                                     ║
║                                                                           ║
║    SOV_NO_AEGIS=1   — disables Aegis entirely. System reverts to       ║
║                       v0.2.34 behavior (Sentinels propose, operator     ║
║                       acts directly).                                    ║
║                                                                           ║
║  Component kill switches:                                                ║
║                                                                           ║
║    SOV_NO_VAULT=1   — disables vault snapshot/restore. Existing        ║
║                       snapshots on disk remain readable; no new ones    ║
║                       get written; restore() refuses.                  ║
║                                                                           ║
║  The defense is the love. The love is the defense.                       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from .radius import BlastRadius
from .incidents import (
    Incident,
    IncidentId,
    DamageReport,
    RepairPlan,
    RepairStep,
    DryRunReport,
    RepairResult,
    Evidence,
)
from .leases import RepairLease, LeaseRefused, sign_lease, verify_lease
from .ledger import AegisLedger, LedgerEntry
from .defcon import Defcon, DefconTransition, transition_allowed
from .medical import MedicalCapability, MedicalRefusal
from .bitemporal import BitemporalRecord, BitemporalStore, OPEN_TX
from .vault import (
    Vault,
    VaultSnapshot,
    VaultKeyError,
    VaultRestoreRefused,
    load_or_create_vault_key,
)
from .conductor import AegisConductor, ConductorState

MASTER_KILL_SWITCH_ENV = "SOV_NO_AEGIS"


__all__ = [
    # radius
    "BlastRadius",
    # incidents
    "Incident", "IncidentId",
    "DamageReport", "RepairPlan", "RepairStep",
    "DryRunReport", "RepairResult", "Evidence",
    # leases
    "RepairLease", "LeaseRefused", "sign_lease", "verify_lease",
    # ledger
    "AegisLedger", "LedgerEntry",
    # defcon
    "Defcon", "DefconTransition", "transition_allowed",
    # medical
    "MedicalCapability", "MedicalRefusal",
    # bitemporal
    "BitemporalRecord", "BitemporalStore", "OPEN_TX",
    # vault
    "Vault", "VaultSnapshot",
    "VaultKeyError", "VaultRestoreRefused",
    "load_or_create_vault_key",
    # conductor
    "AegisConductor", "ConductorState",
    # globals
    "MASTER_KILL_SWITCH_ENV",
]
