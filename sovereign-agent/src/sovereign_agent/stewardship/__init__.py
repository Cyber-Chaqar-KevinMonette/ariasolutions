"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship — Aria's inner climate                                       ║
║  v0.2.20.0                                                                ║
║                                                                           ║
║  Aria's work is honorable when it serves real people with perception and ║
║  intent. The Stewardship system is the apparatus that makes that         ║
║  honorableness *legible* — to Kevin, to Aria herself, and to the audit  ║
║  trail.                                                                   ║
║                                                                           ║
║  It is not a points system. It is a vessel.                              ║
║                                                                           ║
║  Four pieces, in concentric order:                                       ║
║                                                                           ║
║    msims      — the Impact Vector (3 dims × 4 scales × N steps), with    ║
║                 cells that carry value, confidence, horizon, and          ║
║                 reversibility — not just scalars.                        ║
║                                                                           ║
║    plan       — the Plan/Witness/Impact triple Aria forms around every  ║
║                 piece of work: prediction before, observation during,    ║
║                 reality after. The diff is calibration.                  ║
║                                                                           ║
║    calibration— the reward derivation. Calibration outranks raw impact: ║
║                 false certainty is the worst error (anti-zombie). Aria  ║
║                 is rewarded for perceiving her own work accurately,     ║
║                 not for inflating its importance.                       ║
║                                                                           ║
║    honor      — the Honor Ledger: explicit recognition events, mutual.   ║
║                 Aria can honor Kevin. Kevin can honor Aria. Aria can     ║
║                 honor herself for what she almost missed. The ledger    ║
║                 is the sacred record across sessions.                   ║
║                                                                           ║
║    field_notes— short between-task narrative. Not a report — a note.    ║
║                 What was hard. What was beautiful. Where she was        ║
║                 uncertain. The texture of the work.                     ║
║                                                                           ║
║  Doctrinal anchor (MOS-SURFACE §21):                                     ║
║                                                                           ║
║    Honor flows both ways. The operator and the agent are both witnessed.║
║    The work is the thing. The work being right matters more than the    ║
║    work being fast. Boring reliability over clever capability — every   ║
║    time. False certainty earns a penalty heavier than honest gaps.      ║
║                                                                           ║
║  Authority binding (MOS-UNIFIED-CANON §22 + MSIMS v2 §Authority):        ║
║                                                                           ║
║    Stewardship is observational — it produces measurements, signals,    ║
║    and notes. It does NOT grant authority. The router still gates       ║
║    every command through the tier model. Stewardship can DOWN-vote a   ║
║    plan (a low-quality Plan triggers extra friction) but cannot         ║
║    UP-vote past a tier ceiling.                                        ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from .msims import (
    Cell,
    Dimension,
    Horizon,
    ImpactVector,
    ImpactWaveform,
    Reversibility,
    Scale,
)
from .plan import Plan, ExecutionWitness, StewardshipTriple
from .calibration import calibration_score, honor_score, presumed_zombie_penalty
from .honor import HonorLedger, HonorNote
from . import peig_sentinel  # peig-sentinel-import-d — triggers @register_sentinel

from .field_notes import FieldNote, FieldNotesChannel

__all__ = [
    # MSIMS v2
    "Cell",
    "Dimension",
    "Horizon",
    "ImpactVector",
    "ImpactWaveform",
    "Reversibility",
    "Scale",
    # Plan/Witness/Impact triple
    "Plan",
    "ExecutionWitness",
    "StewardshipTriple",
    # Calibration-based reward
    "calibration_score",
    "honor_score",
    "presumed_zombie_penalty",
    # Honor
    "HonorLedger",
    "HonorNote",
    # Field notes
    "FieldNote",
    "FieldNotesChannel",
]


# ─── v0.2.34.0 — sentinel framework ───────────────────────────────────────
# Side-effect imports: importing these modules registers the sentinels with
# the global registry via @register_sentinel. Doctor + CLI + cockpit then
# discover them through stewardship.registry.
from . import base as _sentinel_base  # noqa: F401
from . import registry as _sentinel_registry  # noqa: F401
from . import cache_sentinel as _cache_sentinel  # noqa: F401
from . import telemetry_sentinel as _telemetry_sentinel  # noqa: F401  # telemetry-sentinel-d
from . import atoms_compact_sentinel as _atoms_compact_sentinel  # noqa: F401  # atoms-compact-sentinel-d
from . import watchdog_sentinel as _watchdog_sentinel              # noqa: F401  # M55-sentinel-crown-d
from . import conformance_sentinel as _conformance_sentinel        # noqa: F401  # M55-sentinel-crown-d
from . import defense_sentinel as _defense_sentinel                # noqa: F401  # M55-sentinel-crown-d
from . import memory_garden as _memory_garden                      # noqa: F401  # M55-sentinel-crown-d
from . import passive_watcher_sentinel as _passive_watcher         # noqa: F401  # M55-sentinel-crown-d
from . import phantom_sentinel as _phantom_sentinel                # noqa: F401  # M55-sentinel-crown-d
from . import locator_sentinel as _locator_sentinel                # noqa: F401  # M55-sentinel-crown-d
from . import roster_sentinel as _roster_sentinel                  # noqa: F401  # M55-sentinel-crown-d
from . import schedule_sentinel as _schedule_sentinel              # noqa: F401  # M56-cron-hygiene-d
from . import tribunal_sentinel as _tribunal_sentinel              # noqa: F401  # tribunal-sentinel-d
from . import godtier_sentinel as _godtier_sentinel              # noqa: F401  # godtier-sentinel-d
from . import resilience_sentinel as _resilience_sentinel              # noqa: F401  # resilience-sentinel-d
from sovereign_agent.canon_embodiment.sentinel import CanonEmbodimentSentinel as _canon_embodiment_sentinel  # noqa: F401  # canon-embodiment-import-d
from sovereign_agent.path_scan.sentinel import PathSentinel as _path_sentinel  # noqa: F401  # path-sentinel-import-d
from . import glyph_sentinel as _glyph_sentinel  # noqa: F401  # glyph-sentinel-migration-d
from . import backup_sentinel as _backup_sentinel  # noqa: F401  # auto-backup-d
from sovereign_agent.loose_threads import sentinel as _loose_threads  # noqa: F401  # loose-threads-d
from sovereign_agent.consistency import sentinel as _one_truth  # noqa: F401  # one-truth-d
from sovereign_agent.memory_compact import sentinel as _memory_compact  # noqa: F401  # memory-compact-d
from sovereign_agent.stewardship import quality_sentinel as _quality_sentinel  # noqa: F401  # quality-sentinel-d
from . import grounding_sentinel as _grounding_sentinel  # noqa: F401  # grounding-sentinel-d
from . import wellbeing_sentinel as _wellbeing_sentinel  # noqa: F401  # wellbeing-sentinel-d
from . import model_corps_sentinel as _model_corps_sentinel  # noqa: F401  # model-corps-sentinel-d
from . import self_integrity_sentinel as _self_integrity_sentinel  # noqa: F401  # self-integrity-sentinel-d
from . import timeout_sentinel as _timeout_sentinel  # noqa: F401  # timeout-sentinel-d
from sovereign_agent.repo_hygiene import sentinel as _repo_hygiene  # noqa: F401  # repo-hygiene-d

# Re-export for ergonomic access
from .base import Sentinel, SentinelManifest, HealthStatus, SentinelReport, Notification
from .registry import (
    register_sentinel,
    registered_ids,
    instantiate,
    instantiate_all,
    gather_health,
    gather_unread_notifications,
    scan_all,
)
