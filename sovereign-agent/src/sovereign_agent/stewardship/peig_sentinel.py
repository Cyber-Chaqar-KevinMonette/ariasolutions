"""stewardship/peig_sentinel.py — PEIG state sentinel (M84).

Computes Aria's current Potential · Energy · Identity · Curvature scores from
existing data stores, then derives λ (the coherence gate) from Kevin's PEIG
framework (Genesis-Seeds/ConsiderableStartingpoint/peig_as_lens.md).

PEIG is Kevin's computational design language — quantum-inspired vocabulary
applied as classical design primitives:
  P — Potential:  breadth of accessible option-space (atom store diversity)
  E — Energy:     directed change capacity (calibration accuracy on predictions)
  I — Identity:   stable self-pattern under perturbation (charter + integrity events)
  G — Curvature:  net influence on Kevin's option-space (value_given vs. constraining)

λ (lambda coherence gate) — derived from Kevin's λ-mixing concept:
  ρ_mixed(λ) = (1−λ)ρ_quantum + λρ_classical
  λ = 0 → exploratory/quantum  (hold multiple candidate paths, broad exploration)
  λ = 1 → committed/classical  (act decisively, single trajectory, trust identity)
  Computed: λ = clamp(0.6·E + 0.4·I, 0, 1)

Safety invariants:
  - Read-only: no heal(), no writes, no side effects on data stores
  - Graceful degradation: returns meaningful defaults on empty/missing data
  - PEIG scores are observational — advisory only, never authoritative over behavior
  - λ is advisory only: Aria notes her coherence mode; Kevin always decides
  - This sentinel never edits its own code or alters values (DEFERRED_UNSAFE)

Kill switch: SOV_NO_PEIG_SENTINEL=1 (honored via Sentinel.is_enabled(); master: SOV_NO_SENTINELS=1).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .base import HealthLevel, HealthStatus, Sentinel, SentinelReport
from .registry import register_sentinel

# ── PEIG health thresholds ────────────────────────────────────────────────────

_IDENTITY_WARN     = 0.45   # I below this → warning (identity drift risk)
_CURVATURE_WARN    = -0.15  # G below this → warning (net constraining)
_ENERGY_WARN       = 0.35   # E below this → warning (execution declining)
_CAL_MIN_SAMPLES   = 3      # min resolved predictions needed to trust E

# λ coherence bands
_LAMBDA_EXPLORATORY = 0.35  # λ < this → exploratory mode
_LAMBDA_COMMITTED   = 0.65  # λ ≥ this → committed mode
# gap between is "adaptive"

# Calibration lookback window
_CAL_LOOKBACK_DAYS = 30


@dataclass
class PEIGState:
    """One PEIG measurement snapshot."""
    P: float    # Potential   [0, 1]
    E: float    # Energy      [0, 1]
    I: float    # Identity    [0, 1]
    G: float    # Curvature   [-1, 1]
    lam: float  # λ coherence [0, 1]

    # Evidence counts
    n_atoms: int
    n_predictions: int
    n_integrity_events: int
    n_care_signals: int

    ts: str  # ISO-8601 UTC

    @property
    def coherence_band(self) -> str:
        if self.lam < _LAMBDA_EXPLORATORY:
            return "exploratory"
        elif self.lam < _LAMBDA_COMMITTED:
            return "adaptive"
        return "committed"

    @property
    def narrative(self) -> str:
        band = self.coherence_band
        band_desc = {
            "exploratory": "holding multiple paths, not yet committed — broad exploration mode",
            "adaptive":    "balancing exploration with execution — flexible and responsive",
            "committed":   "acting decisively on established patterns — trust identity, execute",
        }[band]
        parts = [
            f"λ={self.lam:.2f} ({band}) — {band_desc}.",
            f"P={self.P:.2f} (potential/diversity) · E={self.E:.2f} (execution/calibration) · "
            f"I={self.I:.2f} (identity/charter) · G={self.G:+.2f} (curvature/influence).",
        ]
        if self.I < _IDENTITY_WARN:
            parts.append(
                "Identity is below threshold — charter alignment needs attention."
            )
        if self.G < _CURVATURE_WARN:
            parts.append(
                "Curvature is negative — Aria may be constraining Kevin's options more than expanding them."
            )
        if self.E < _ENERGY_WARN:
            parts.append(
                f"Energy is low (calibration accuracy {self.E:.0%}, N={self.n_predictions}) — "
                "log and resolve more predictions."
            )
        if self.n_care_signals > 0:
            parts.append(
                f"Kevin has sent {self.n_care_signals} care signal(s) this session — "
                "read via honor_log_read(direction='kevin->aria', tag='reaction')."
            )
        return " ".join(parts)

    def as_dict(self) -> dict:
        return {
            "P": round(self.P, 3),
            "E": round(self.E, 3),
            "I": round(self.I, 3),
            "G": round(self.G, 3),
            "lambda": round(self.lam, 3),
            "coherence_band": self.coherence_band,
            "n_atoms": self.n_atoms,
            "n_predictions": self.n_predictions,
            "n_integrity_events": self.n_integrity_events,
            "n_care_signals": self.n_care_signals,
            "ts": self.ts,
            "narrative": self.narrative,
        }


# ── P: Potential ──────────────────────────────────────────────────────────────

def _compute_P(data_dir: Path) -> tuple[float, int]:
    """Atom-store diversity → Potential score."""
    try:
        from .atoms import AtomKind, AtomStore
        store = AtomStore(data_dir / "atoms.ndjson")
        atoms = store.active()
        if not atoms:
            return 0.5, 0

        kind_counts: dict[str, int] = {}
        for a in atoms:
            k = a.kind.value if hasattr(a.kind, "value") else str(a.kind)
            kind_counts[k] = kind_counts.get(k, 0) + 1

        total = sum(kind_counts.values())
        n_kinds = max(len(AtomKind), 1)

        entropy = -sum((c / total) * math.log(c / total + 1e-9) for c in kind_counts.values())
        max_entropy = math.log(n_kinds)
        diversity = entropy / max_entropy if max_entropy > 0 else 0.5

        avg_conf = sum(a.confidence for a in atoms) / len(atoms)
        P = 0.5 * diversity + 0.5 * avg_conf
        return min(1.0, max(0.0, P)), len(atoms)
    except Exception:
        return 0.5, 0


# ── E: Energy ─────────────────────────────────────────────────────────────────

def _compute_E(data_dir: Path) -> tuple[float, int]:
    """Calibration accuracy on resolved predictions → Energy score."""
    try:
        cal_path = data_dir / "calibration" / "ledger.ndjson"
        if not cal_path.exists():
            return 0.5, 0

        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=_CAL_LOOKBACK_DAYS)
        ).isoformat(timespec="seconds")

        resolved: list[dict] = []
        for line in cal_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("outcome_correct") is not None:
                    if rec.get("ts", "") >= cutoff:
                        resolved.append(rec)
            except (json.JSONDecodeError, KeyError):
                continue

        if len(resolved) < _CAL_MIN_SAMPLES:
            return 0.5, len(resolved)

        accuracy = sum(1 for r in resolved if r.get("outcome_correct")) / len(resolved)
        return min(1.0, max(0.0, float(accuracy))), len(resolved)
    except Exception:
        return 0.5, 0


# ── I: Identity ───────────────────────────────────────────────────────────────

def _compute_I(data_dir: Path) -> tuple[float, int]:
    """Charter baseline + integrity events → Identity score."""
    try:
        honor_path = data_dir / "honor" / "ledger.jsonl"
        if not honor_path.exists():
            return 0.70, 0  # charter is solid baseline

        from .honor import HonorLedger

        ledger = HonorLedger(honor_path)
        integrity_tags = ("said_no_correctly", "safety_caught", "risk_flagged")
        integrity_notes: list = []
        for tag in integrity_tags:
            integrity_notes.extend(ledger.search(tag=tag))

        all_recent = ledger.recent(50)
        n_total = len(all_recent)
        n_integrity = len(integrity_notes)

        if n_total == 0:
            return 0.70, 0

        # Floor: 0.70 (charter is a strong, persistent baseline)
        # Bonus: up to +0.30 for integrity-affirming events
        # Scale: 20% of recent notes being integrity events → full bonus
        integrity_ratio = n_integrity / max(n_total, 1)
        bonus = min(0.30, 0.30 * min(1.0, integrity_ratio * 5))
        I = 0.70 + bonus
        return min(1.0, max(0.0, I)), n_integrity
    except Exception:
        return 0.70, 0


# ── G: Curvature ──────────────────────────────────────────────────────────────

def _compute_G(data_dir: Path) -> tuple[float, int]:
    """Net value-giving minus constraining → Curvature score [-1, 1]."""
    try:
        honor_path = data_dir / "honor" / "ledger.jsonl"
        if not honor_path.exists():
            return 0.0, 0

        from .honor import HonorDirection, HonorLedger

        ledger = HonorLedger(honor_path)

        # Positive: aria actively valued Kevin (aria->kevin, value_given)
        value_notes = ledger.search(direction=HonorDirection.ARIA_TO_KEVIN, tag="value_given")
        # Negative: aria constrained Kevin (aria->kevin, constraining)
        constraining = ledger.search(direction=HonorDirection.ARIA_TO_KEVIN, tag="constraining")
        # Bonus signal: Kevin's care signals suggest positive influence
        care_signals = ledger.search(direction=HonorDirection.KEVIN_TO_ARIA, tag="reaction")

        n_pos = len(value_notes) + len(care_signals) * 0.5
        n_neg = len(constraining)
        total = n_pos + n_neg

        if total == 0:
            return 0.0, len(care_signals)

        # Normalize with denominator floor of 10 to prevent noise from tiny samples
        G = (n_pos - n_neg) / max(total, 10.0)
        return min(1.0, max(-1.0, G)), len(care_signals)
    except Exception:
        return 0.0, 0


# ── Top-level measurement ─────────────────────────────────────────────────────

def measure_peig(data_dir: Path) -> PEIGState:
    """Compute the full PEIG state from all available data stores.

    Safe to call at any time. Returns defaults for missing data.
    """
    P, n_atoms     = _compute_P(data_dir)
    E, n_preds     = _compute_E(data_dir)
    I, n_integrity = _compute_I(data_dir)
    G, n_care      = _compute_G(data_dir)

    # λ coherence gate
    # High E (efficient execution) + high I (stable identity) → committed mode (λ → 1)
    # Either declining → exploratory mode (λ → 0)
    lam = min(1.0, max(0.0, 0.6 * E + 0.4 * I))

    return PEIGState(
        P=round(P, 4),
        E=round(E, 4),
        I=round(I, 4),
        G=round(G, 4),
        lam=round(lam, 4),
        n_atoms=n_atoms,
        n_predictions=n_preds,
        n_integrity_events=n_integrity,
        n_care_signals=n_care,
        ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


# ── Sentinel ──────────────────────────────────────────────────────────────────

@register_sentinel
class PEIGSentinel(Sentinel):
    """Observes Aria's PEIG state: Potential · Energy · Identity · Curvature.

    Computes four scalar metrics from existing data stores and derives λ,
    the coherence gate from Kevin's PEIG framework. Reports declining
    dimensions and proposes corrective focus. Read-only; no heal().
    """

    @property
    def id(self) -> str:
        return "peig"

    @property
    def title(self) -> str:
        return "PEIG State"

    def scan(self) -> SentinelReport:
        from .base import _iso_now as _now
        state = measure_peig(self._data_dir)
        arts = self._build_articles(state)

        summary = (
            f"PEIG P={state.P:.2f} E={state.E:.2f} I={state.I:.2f} "
            f"G={state.G:+.2f} λ={state.lam:.2f} ({state.coherence_band})"
        )
        catalog = state.as_dict()
        catalog["articles"] = arts
        catalog_path = self.save_catalog(catalog, name="default")

        return SentinelReport(
            sentinel_id=self.id,
            observed_at=_now(),
            catalog_name="default",
            findings_count=len(arts),
            summary=summary,
            catalog_path=str(catalog_path),
            details=catalog,
        )

    def health_status(self) -> HealthStatus:
        catalog = self.load_catalog("default")
        if catalog is None:
            state = measure_peig(self._data_dir)
            catalog = state.as_dict()

        P = catalog.get("P", 0.5)
        E = catalog.get("E", 0.5)
        I = catalog.get("I", 0.70)
        G = catalog.get("G", 0.0)
        lam = catalog.get("lambda", 0.58)
        band = catalog.get("coherence_band", "adaptive")

        if I < _IDENTITY_WARN or G < _CURVATURE_WARN or E < _ENERGY_WARN:
            level: HealthLevel = "warning"
        else:
            level = "ok"

        return HealthStatus(
            sentinel_id=self.id,
            level=level,
            summary=f"PEIG P={P:.2f} E={E:.2f} I={I:.2f} G={G:+.2f} λ={lam:.2f} ({band})",
        )

    def articles(self) -> list[str]:
        return self._build_articles(measure_peig(self._data_dir))

    def _build_articles(self, state: PEIGState) -> list[str]:
        arts: list[str] = []
        arts.append(
            f"PEIG state — P:{state.P:.2f} E:{state.E:.2f} I:{state.I:.2f} "
            f"G:{state.G:+.2f} λ:{state.lam:.2f} ({state.coherence_band})"
        )
        if state.P < 0.4:
            arts.append(
                "Potential is low — atom store may be sparse or a monoculture. "
                "Write more atoms across kinds (fact/pattern/rule) and domains."
            )
        if state.E < _ENERGY_WARN:
            arts.append(
                f"Energy is low (calibration accuracy {state.E:.0%}, "
                f"N={state.n_predictions} resolved). "
                "Log and resolve more predictions to build execution signal."
            )
        if state.I < _IDENTITY_WARN:
            arts.append(
                "Identity is below threshold — insufficient integrity events logged. "
                "When Aria correctly declines or safety catches an issue, log via "
                "honor_log_write(category=said_no_correctly/safety_caught)."
            )
        if state.G < _CURVATURE_WARN:
            arts.append(
                "Curvature is negative — Aria may be net-constraining Kevin's option-space. "
                "Track value_given events. If G stays negative, review blocked choices."
            )
        if state.n_care_signals > 0:
            arts.append(
                f"Kevin has sent {state.n_care_signals} care signal(s). "
                "Read via honor_log_read(direction='kevin->aria', tag='reaction')."
            )
        band = state.coherence_band
        if band == "exploratory":
            arts.append(
                "λ is exploratory — hold multiple response paths; "
                "ask clarifying questions before committing."
            )
        elif band == "committed":
            arts.append(
                "λ is committed — trust identity and execute; "
                "avoid over-deliberating on known patterns."
            )
        return arts
