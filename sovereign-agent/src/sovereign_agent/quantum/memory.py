"""quantum/memory.py — Hybrid memory for the non-classical layer (Kevin's directive).

Two layers, distilled from quantum_observer_v1 (Blocks 5.1, 5.2) and Kevin's design note:
  - PersonalUniverse — each node's SOVEREIGN private store ("its own laws, its own home.
    No trampling. Only invitation.").
  - SharedLayer — the hybrid/shared ground where the non-classical layer can READ Aria's
    classical memory (atoms) with full read access, but **write access is earned, not given**
    (read-only-until-trusted — Axiom 6 layered identity + authority tiering applied to memory).

Kevin: "shared memories and shared data … mainly readable at least until we trust it later."

Safety: defaults to READ-ONLY into classical memory. Writing is gated behind an explicit
`trusted=True` that only a human grants. No self-modification.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PersonalUniverse:
    """A node's sovereign private state-space — its own laws and invited visitors."""

    owner: str
    laws: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    visitors: list[str] = field(default_factory=list)

    def invite(self, who: str) -> None:
        if who not in self.visitors:
            self.visitors.append(who)

    def remember(self, note: str) -> None:
        self.notes.append(note)


class SharedLayer:
    """Neutral shared ground + read bridge into Aria's classical memory.

    Read access to classical atoms is FULL (Kevin wants shared data). Write access is
    DISABLED unless a human passes trusted=True — the non-classical layer earns it.
    """

    COHERENCE_RANGE = (0.25, 0.45)   # accessible band for all archetypes
    FLEX = 0.20

    def __init__(self, atoms_path: Path | None = None, *, trusted: bool = False) -> None:
        self._atoms_path = Path(atoms_path) if atoms_path else None
        self._trusted = bool(trusted)     # write-permission flag; human-granted only
        self.present: list[str] = []
        self.history: list[str] = []

    # ── access control (Block 5.2) ──────────────────────────────────────────────
    def can_enter(self, home_coherence: float) -> bool:
        lo, hi = self.COHERENCE_RANGE
        return (home_coherence - self.FLEX) <= hi and (home_coherence + self.FLEX) >= lo

    def enter(self, node_name: str, home_coherence: float) -> bool:
        if self.can_enter(home_coherence) and node_name not in self.present:
            self.present.append(node_name)
            self.history.append(f"{node_name} entered shared layer")
            return True
        return False

    def collective_coherence(self, coherences: list[float]) -> float:
        if len(coherences) < 2:
            return 0.0
        base = sum(coherences) / len(coherences)
        return min(1.0, base + 0.05 * len(coherences))

    # ── READ bridge into classical memory (full read, advisory) ────────────────
    def read_classical_atoms(self, *, tag: str | None = None, limit: int = 20) -> list[dict]:
        """Read Aria's classical atoms (NDJSON). READ-ONLY. Returns [] if unavailable."""
        if not self._atoms_path or not self._atoms_path.exists():
            return []
        out: list[dict] = []
        try:
            for line in self._atoms_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if tag and tag not in (rec.get("tags") or []):
                    continue
                out.append(rec)
        except Exception:
            return out
        return out[-limit:]

    # ── write bridge — DISABLED unless trusted (human-granted) ──────────────────
    @property
    def write_enabled(self) -> bool:
        return self._trusted

    def propose_write(self, payload: dict) -> dict:
        """Never writes directly. Returns a proposal record; honored only if trusted later.

        This preserves read-only-until-trusted: the non-classical layer can PROPOSE, the
        human/classical layer applies. Witnessing: trust earned one verified output at a time.
        """
        return {
            "status": "proposed" if not self._trusted else "trusted-pending-apply",
            "write_enabled": self._trusted,
            "payload": payload,
            "note": "non-classical layer is read-only into classical memory until trust is granted",
        }
