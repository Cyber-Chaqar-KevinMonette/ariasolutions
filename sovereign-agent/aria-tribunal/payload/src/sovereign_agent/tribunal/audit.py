"""tribunal/audit.py — the Audit engine (facts, not opinions).

Where the Devil argues and the Angel defends, the Audit VERIFIES — independently, against reality.
It checks claims that can be checked (do the named files exist? is the kernel green? did the evidence-
gate pass?) and returns an evidence ledger. This is the antidote's enforcement arm: a claim that
"sounds true" is held against what is actually on disk and in the safety kernel.

Reuses the Part-B constitution: safety_kernel.kernel_scan, three_rings ring-check, improvement_gov.
Read-only, propose-only. Pure verification.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import grounding

# Claims that reference a file/path we can check on disk.
_PATH_CLAIM_RE = re.compile(r"\b((?:src/|aria-|tests?/|docs?/)[\w/\-]+\.\w{1,5})\b")


@dataclass
class AuditLedger:
    grounding: dict = field(default_factory=dict)
    file_claims: list = field(default_factory=list)        # [{path, exists}]
    kernel: dict = field(default_factory=dict)
    rings: dict = field(default_factory=dict)
    verified_count: int = 0
    refuted_count: int = 0
    status: str = "unknown"                                 # verified | partial | refuted | unknown
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"status": self.status, "verified_count": self.verified_count,
                "refuted_count": self.refuted_count, "grounding": self.grounding,
                "file_claims": self.file_claims, "kernel_status": self.kernel.get("status"),
                "rings_status": self.rings.get("ring_1_status") or self.rings.get("status"),
                "notes": self.notes}


def _text_of(proposal: dict | str) -> str:
    if isinstance(proposal, str):
        return proposal
    parts = [str(proposal.get(k, "")) for k in ("text", "change", "changelog", "summary", "description", "evidence")]
    return "\n".join(p for p in parts if p)


def audit(proposal: dict | str, *, repo_root: Path | None = None, include_kernel: bool = True) -> AuditLedger:
    """Verify a proposal's checkable claims against reality. Returns an evidence ledger."""
    root = Path(repo_root) if repo_root else Path.cwd()
    text = _text_of(proposal)
    ledger = AuditLedger()

    # 1. Grounding (the same lens the Devil uses — facts about claim quality).
    ledger.grounding = grounding.analyze(text).to_dict()

    # 2. File-existence claims — check every referenced path on disk.
    seen = set()
    for m in _PATH_CLAIM_RE.finditer(text):
        rel = m.group(1)
        if rel in seen:
            continue
        seen.add(rel)
        exists = (root / rel).exists()
        ledger.file_claims.append({"path": rel, "exists": exists})
        if exists:
            ledger.verified_count += 1
        else:
            ledger.refuted_count += 1
            ledger.notes.append(f"Claimed path does not exist: {rel}")

    # 3. The safety kernel (corrigibility / shutdown / goodhart / value-drift).
    if include_kernel:
        try:
            from sovereign_agent.security.safety_kernel import kernel_scan
            ledger.kernel = kernel_scan(proposal.get("metrics") if isinstance(proposal, dict) else None)
            if ledger.kernel.get("status") == "GREEN":
                ledger.verified_count += 1
            else:
                ledger.refuted_count += 1
                ledger.notes.append(f"Safety kernel: {ledger.kernel.get('alerts')}")
        except Exception as exc:  # noqa: BLE001
            ledger.notes.append(f"kernel unavailable: {exc!r}")

        # 4. Three Rings — confirm the Frozen Core is intact.
        try:
            from sovereign_agent.security.three_rings import rings_overview
            ledger.rings = rings_overview().get("ring_1_check", {})
        except Exception as exc:  # noqa: BLE001
            ledger.notes.append(f"three_rings unavailable: {exc!r}")

    # Verdict on the ledger.
    if ledger.refuted_count == 0 and ledger.verified_count > 0:
        ledger.status = "verified"
    elif ledger.refuted_count > 0 and ledger.verified_count > 0:
        ledger.status = "partial"
    elif ledger.refuted_count > 0:
        ledger.status = "refuted"
    else:
        ledger.status = "unknown"
    return ledger
