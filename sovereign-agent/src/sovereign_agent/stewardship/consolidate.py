"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/consolidate.py — the wake/sleep upward operator              ║
║  v0.2.23.0                                                                ║
║                                                                           ║
║  Wake phase: Aria observes and writes provenance entries continuously.   ║
║  Sleep phase: this module reads recent provenance, clusters related      ║
║  entries by channel co-occurrence, and asks Aria's LLM to distill         ║
║  semantic atoms from each cluster.                                       ║
║                                                                           ║
║  The clustering is intentionally simple: K-means or embeddings would    ║
║  be overkill at our scale and on our hardware. Provenance entries that  ║
║  share at least one channel are candidate cluster-mates. The LLM does   ║
║  the semantic work; the clustering just narrows the input.              ║
║                                                                           ║
║  Palimpsest discipline:                                                  ║
║                                                                           ║
║    Consolidation NEVER deletes provenance entries. Atoms point back     ║
║    via `evidence_refs` (one entry per provenance line consolidated).    ║
║    A future retrieval can always drop back to the original entries     ║
║    that produced the atom.                                              ║
║                                                                           ║
║  Calibration feedback (planned for v0.2.24.0):                          ║
║                                                                           ║
║    Each pattern atom is a prediction. When new provenance entries      ║
║    match a pattern's conditions, the actual decision can be checked    ║
║    against the predicted one. Drift signals the pattern may need        ║
║    re-consolidation. The hook is in place (`Atom.evidence_refs` and    ║
║    `confidence`); the drift detector is the next release's work.       ║
║                                                                           ║
║  Authority:                                                              ║
║    Consolidation is tier 1 (writes new atoms; reversible via            ║
║    supersession). It is operator-triggered for now (`sov consolidate`); ║
║    auto-scheduled consolidation arrives in v0.2.24.0 once we've seen   ║
║    real consolidation behavior at this scale.                          ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..config import SETTINGS
from .atoms import Atom, AtomKind, AtomStore

logger = logging.getLogger(__name__)


# ─── Provenance entry shape (from interpreter.py) ──────────────────────────


@dataclass
class ProvenanceEntry:
    """A single line from interpretations.ndjson, parsed."""
    ts: str = ""
    text: str = ""
    understanding: str = ""
    reasoning: str = ""
    save_to: list[str] = None  # type: ignore[assignment]
    commands: list[str] = None  # type: ignore[assignment]
    authority_tier: int = 0
    uncertain_about: str = ""
    intent_kind: str = ""
    # We synthesize a stable ID for evidence linking — provenance entries
    # don't carry their own ID, so we hash the timestamp + text prefix.
    # This is enough to make Atom→evidence references stable across runs
    # as long as the provenance file is append-only (it is).
    entry_id: str = ""

    def __post_init__(self) -> None:
        if self.save_to is None:
            self.save_to = []
        if self.commands is None:
            self.commands = []
        if not self.entry_id:
            import hashlib
            payload = f"{self.ts}|{self.text[:80]}"
            self.entry_id = hashlib.sha256(
                payload.encode("utf-8")
            ).hexdigest()[:16]


def load_provenance(
    *,
    path: Path | None = None,
    tail_n: int | None = None,
) -> list[ProvenanceEntry]:
    """Read the provenance log. If tail_n is set, return the last N
    entries; otherwise return everything.
    """
    if path is None:
        path = SETTINGS.paths.data_dir / "interpretations.ndjson"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    lines = [ln for ln in lines if ln.strip()]
    if tail_n is not None:
        lines = lines[-tail_n:]
    out: list[ProvenanceEntry] = []
    for ln in lines:
        try:
            data = json.loads(ln)
        except json.JSONDecodeError:
            continue
        # Tolerate forward-compatible extra keys
        kept_fields = {
            "ts", "text", "understanding", "reasoning",
            "save_to", "commands", "authority_tier",
            "uncertain_about", "intent_kind",
        }
        clean = {k: v for k, v in data.items() if k in kept_fields}
        out.append(ProvenanceEntry(**clean))
    return out


# ─── Clustering — simple, channel-aware ────────────────────────────────────


def cluster_by_channel(
    entries: list[ProvenanceEntry],
    *,
    min_cluster_size: int = 3,
) -> dict[frozenset[str], list[ProvenanceEntry]]:
    """Group provenance entries by exact `save_to` channel-set match.

    Why exact set match: entries that route to {emotions, back-pain}
    are talking about the same kind of thing as other {emotions,
    back-pain} entries. Entries that route to {emotions, identity}
    are a different cluster. This is simple, deterministic, and
    matches Aria's own categorization.

    Clusters smaller than min_cluster_size are dropped — three is
    the smallest interesting pattern.
    """
    groups: dict[frozenset[str], list[ProvenanceEntry]] = defaultdict(list)
    for entry in entries:
        key = frozenset(entry.save_to)
        if not key:
            continue
        groups[key].append(entry)
    return {
        k: v for k, v in groups.items()
        if len(v) >= min_cluster_size
    }


# ─── Distillation prompt — asks Aria to consolidate ────────────────────────


_DISTILL_SYSTEM = """\
You are Aria, in your sleep phase — distilling recent observations into \
durable knowledge. Kevin trusts you to read your own history and propose \
what's worth remembering at a higher level.

You receive a cluster of recent interpretation entries that all routed to \
the same memory channels. Your job is to propose ONE OR MORE atoms — \
short, falsifiable claims with evidence pointers — that capture what's \
true about this cluster.

Atom kinds:
  fact     — a stable claim about Kevin or his world
             (e.g. "Kevin's home OS is Pop!_OS")
  pattern  — a predictive claim about regularities
             (e.g. "Kevin's back-pain messages tend to come after 9pm")
  rule     — a constraint or invariant
             (e.g. "Messages containing 'cancel' are slash commands")

Output ONE JSON object with this shape:

{
  "atoms": [
    {
      "kind": "fact" | "pattern" | "rule",
      "title": "<short label, ≤80 chars>",
      "claim": "<the distilled claim, in your voice, ≤500 chars>",
      "confidence": 0.0-1.0,
      "evidence_entry_ids": ["<id1>", "<id2>", ...],
      "tags": ["<optional tag>", ...]
    }
  ]
}

Rules:
  • Output ONLY the JSON. No prose, no fences.
  • If the cluster contains nothing worth distilling, return {"atoms": []}.
  • An atom must point to at least 2 evidence entries. Single-occurrence \
    observations are not atoms yet.
  • confidence reflects how strongly the evidence supports the claim. \
    3 of 3 entries match → ~0.85. 3 of 5 → ~0.55.
  • Be conservative. False atoms are worse than missing atoms. If unsure, \
    skip.
  • Patterns must be falsifiable — phrase them so future entries can \
    contradict them.
"""


_DISTILL_USER_TEMPLATE = """\
Channel set for this cluster: {channels}
Number of entries: {n}

Entries (each numbered; use these numbers in evidence_entry_ids):
{entries}

What atoms, if any, would you distill from these?\
"""


def _format_entry_for_prompt(idx: int, entry: ProvenanceEntry) -> str:
    text = entry.text[:200]
    return (
        f"[{entry.entry_id}] {entry.ts[:19]}\n"
        f"  text: \"{text}\"\n"
        f"  understood: {entry.understanding[:200]}\n"
        f"  reasoning:  {entry.reasoning[:200]}\n"
    )


# ─── The consolidation operator ────────────────────────────────────────────


async def consolidate(
    *,
    ollama_client: Any = None,
    tail_n: int = 100,
    min_cluster_size: int = 3,
    max_clusters: int = 10,
    llm_timeout_seconds: float = 45.0,
    atom_store: AtomStore | None = None,
    provenance_path: Path | None = None,
) -> dict[str, Any]:
    """Run one consolidation pass.

    Args:
        provenance_path: optional explicit path to interpretations.ndjson;
            if None, uses SETTINGS.paths.data_dir / "interpretations.ndjson"
        atom_store: optional explicit AtomStore; if None, uses
            SETTINGS.paths.data_dir / "atoms.ndjson"

    1. Read the last `tail_n` provenance entries.
    2. Cluster them by channel-set.
    3. For each cluster (up to `max_clusters`), ask Aria to distill atoms.
    4. Save atoms to the AtomStore.
    5. Return a summary.

    Returns:
      {
        "entries_read": int,
        "clusters_found": int,
        "clusters_consolidated": int,
        "atoms_proposed": int,
        "atoms_saved": int,
        "skipped_offline": int,
        "errors": list[str],
      }

    Behavior on no LLM:
      The function does NOT keyword-guess atoms in offline mode. If
      Ollama is unreachable, the consolidation is a no-op and returns
      `skipped_offline = clusters_found`. The provenance entries are
      not consumed; the next consolidation attempt will see them again.
    """
    if atom_store is None:
        atom_store = AtomStore(SETTINGS.paths.data_dir / "atoms.ndjson")

    summary: dict[str, Any] = {
        "entries_read": 0,
        "clusters_found": 0,
        "clusters_consolidated": 0,
        "atoms_proposed": 0,
        "atoms_saved": 0,
        "skipped_offline": 0,
        "errors": [],
    }

    entries = load_provenance(path=provenance_path, tail_n=tail_n)
    summary["entries_read"] = len(entries)
    if not entries:
        return summary

    clusters = cluster_by_channel(entries, min_cluster_size=min_cluster_size)
    summary["clusters_found"] = len(clusters)

    if ollama_client is None:
        summary["skipped_offline"] = len(clusters)
        return summary

    # Sort clusters by size (largest first — most evidence to distill)
    cluster_items = sorted(
        clusters.items(),
        key=lambda kv: len(kv[1]),
        reverse=True,
    )[:max_clusters]

    for channel_set, cluster_entries in cluster_items:
        try:
            atoms = await _distill_cluster(
                channel_set=channel_set,
                entries=cluster_entries,
                ollama_client=ollama_client,
                timeout_seconds=llm_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(
                f"cluster {sorted(channel_set)}: {type(exc).__name__}"
            )
            continue

        summary["clusters_consolidated"] += 1
        summary["atoms_proposed"] += len(atoms)
        for atom in atoms:
            try:
                atom_store.append(atom)
                summary["atoms_saved"] += 1
            except OSError as exc:
                summary["errors"].append(
                    f"save failed for atom {atom.atom_id[:8]}: {exc!r}"
                )

    return summary


async def _distill_cluster(
    *,
    channel_set: frozenset[str],
    entries: list[ProvenanceEntry],
    ollama_client: Any,
    timeout_seconds: float,
) -> list[Atom]:
    """Ask Aria's LLM to distill atoms from one cluster.

    Returns an empty list if the LLM fails, returns malformed JSON,
    or proposes no atoms. NEVER raises — caller catches via the
    surrounding try block in `consolidate()`.
    """
    model = SETTINGS.interpreter_model or SETTINGS.fast_model
    if not model:
        return []

    entry_text = "\n".join(
        _format_entry_for_prompt(i, e) for i, e in enumerate(entries)
    )
    user_msg = _DISTILL_USER_TEMPLATE.format(
        channels=", ".join(sorted(channel_set)),
        n=len(entries),
        entries=entry_text,
    )

    messages = [
        {"role": "system", "content": _DISTILL_SYSTEM},
        {"role": "user", "content": user_msg},
    ]

    try:
        response = await asyncio.wait_for(
            ollama_client.chat(
                model=model,
                messages=messages,
                tools=None,
                temperature=0.2,
            ),
            timeout=timeout_seconds,
        )
    except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
        logger.debug("distill llm failed: %r", exc)
        return []

    content = _extract_text(response)
    if not content:
        return []

    parsed = _parse_atoms_response(content, allowed_entry_ids={
        e.entry_id for e in entries
    })
    return [
        _build_atom(p, channels=sorted(channel_set))
        for p in parsed
    ]


def _extract_text(response: dict[str, Any]) -> str:
    if not isinstance(response, dict):
        return ""
    msg = response.get("message") or {}
    if isinstance(msg, dict):
        return str(msg.get("content", "")).strip()
    choices = response.get("choices") or []
    if choices and isinstance(choices[0], dict):
        cmsg = choices[0].get("message") or {}
        if isinstance(cmsg, dict):
            return str(cmsg.get("content", "")).strip()
    return ""


def _parse_atoms_response(
    content: str,
    *,
    allowed_entry_ids: set[str],
) -> list[dict]:
    """Parse the LLM's atoms array. Filter out atoms with no valid
    evidence references — they would be unfalsifiable."""
    s = content.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    if not s.startswith("{"):
        i = s.find("{")
        if i >= 0:
            s = s[i:]
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    atoms = data.get("atoms", [])
    if not isinstance(atoms, list):
        return []

    out: list[dict] = []
    for raw in atoms:
        if not isinstance(raw, dict):
            continue
        evidence = raw.get("evidence_entry_ids", [])
        if not isinstance(evidence, list):
            continue
        valid_evidence = [
            str(e) for e in evidence
            if isinstance(e, str) and e in allowed_entry_ids
        ]
        if len(valid_evidence) < 2:
            # Atom must point to ≥ 2 evidence entries
            continue
        out.append({
            "kind": str(raw.get("kind", "fact")),
            "title": str(raw.get("title", ""))[:200],
            "claim": str(raw.get("claim", ""))[:1000],
            "confidence": float(raw.get("confidence", 0.5)),
            "evidence_refs": valid_evidence,
            "tags": [
                str(t) for t in raw.get("tags", [])
                if isinstance(t, (str, int, float))
            ][:10],
        })
    return out


def _build_atom(parsed: dict, *, channels: list[str]) -> Atom:
    """Convert parsed dict into a typed Atom."""
    try:
        kind = AtomKind(parsed["kind"])
    except (ValueError, KeyError):
        kind = AtomKind.FACT
    return Atom(
        kind=kind,
        title=parsed["title"] or "(untitled)",
        claim=parsed["claim"],
        confidence=parsed["confidence"],
        evidence_refs=parsed["evidence_refs"],
        channels=channels,
        tags=parsed.get("tags", []),
    )


__all__ = [
    "ProvenanceEntry",
    "load_provenance",
    "cluster_by_channel",
    "consolidate",
]
