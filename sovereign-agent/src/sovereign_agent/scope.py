"""scope.py — her ability to SCOPE: pre-registered honesty at the boundary
of a piece of work.

Kevin's ask (Keys round, mid-flight): *"hardening her ability to scope —
in her work, in her research, and anywhere else it can matter most; part
of her persistence and horizon abilities."* And for her designing and
architecting too (K8's workflow drafts carry these contracts).

The framing that makes this HERS: her stewardship already lives by
Plan/Witness/Impact — prediction before, observation during, reality
after. A ScopeContract applies that same discipline to the BOUNDARY of
work: she writes down what DONE means and what she will NOT touch
*before* starting, so completion is checkable and drift is visible —
never discovered after the fact.

  - Operator-declared: `/work fix the parser | scope: only src/parser;
    out: tests, docs; done: parse errors gone; max: 8`
  - Persisted beside the session file (`sessions/<sid>.scope.json`) — her
    persistence; a resumed session re-reads its own contract.
  - Folded into the session guidance preamble — she self-polices against
    her own written words.
  - Teeth at the exact door scope creep enters: NEXT_SUBTASK proposals
    matching the `out:` list are held for review, never silently
    appended. Approaching `max:` emits `scope-drift-d` long before the
    budget wall does the blunt stopping.

The v1 in/out check is deliberately a transparent keyword heuristic —
honest and predictable for an 8B vessel; an LLM-refined check can layer
on later without changing the contract shape.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

DRIFT_THRESHOLD = 0.8  # of max_subtasks


@dataclass
class ScopeContract:
    goal: str
    in_scope: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    done_when: str = ""
    max_subtasks: int = 12
    # Kevin (mid-round): scope her OBSERVATION and SECURITY too.
    # observe: what she deliberately watches/verifies while working —
    # her witnessing, scoped. security: declared security bounds for
    # THIS work (e.g. "no network", "read-only outside the sandbox").
    # Stated plainly: v1 security bounds are self-policing discipline in
    # the prompt + visible in the contract; the ENFORCED walls remain the
    # authority gate, pathguard, and tier ceilings — a contract narrows
    # behavior inside those walls, it never widens them.
    observe: list[str] = field(default_factory=list)
    security: list[str] = field(default_factory=list)
    # garden-d — her assigned garden for this work (operator-granted
    # directory; ENFORCED by pathguard, not just self-policed).
    garden_dir: str = ""

    def as_dict(self) -> dict:
        return asdict(self)

    def is_out_of_scope(self, description: str) -> bool:
        """True when the description trips an out_of_scope term. Transparent
        keyword heuristic (v1) — case-insensitive substring match."""
        desc = (description or "").lower()
        return any(term.lower() in desc for term in self.out_of_scope if term.strip())

    def format_for_prompt(self) -> str:
        lines = ["═══ SCOPE CONTRACT (you wrote this before starting) ═══"]
        if self.in_scope:
            lines.append("IN scope: " + "; ".join(self.in_scope))
        if self.out_of_scope:
            lines.append("OUT of scope (do NOT touch): " + "; ".join(self.out_of_scope))
        if self.done_when:
            lines.append("DONE means: " + self.done_when)
        if self.observe:
            lines.append("WATCH while working (verify these as you go): "
                         + "; ".join(self.observe))
        if self.garden_dir:  # garden-d
            lines.append(
                "YOUR GARDEN: " + self.garden_dir
                + " — tend here; the loop refuses writes outside it."
            )
        if self.security:
            lines.append("SECURITY bounds for this work (hold yourself to "
                         "these, beyond the always-on gates): "
                         + "; ".join(self.security))
        lines.append(
            f"Stay inside this contract. Proposals outside it are held for "
            f"operator review. Queue ceiling: {self.max_subtasks} subtasks."
        )
        return "\n".join(lines)


_SCOPE_SPLIT_RE = re.compile(r"\|\s*scope\s*:", re.IGNORECASE)


def parse_goal_with_scope(raw: str) -> tuple[str, ScopeContract | None]:
    """Split `/work <goal> | scope: <spec>` into (goal, contract|None).

    Spec grammar (all parts optional, `;`-separated within a part):
      `<in terms> ; out: <out terms> ; done: <text> ; max: <n>`
    """
    parts = _SCOPE_SPLIT_RE.split(raw, maxsplit=1)
    goal = parts[0].strip()
    if len(parts) == 1:
        return goal, None
    spec = parts[1].strip()
    contract = ScopeContract(goal=goal)
    for chunk in [c.strip() for c in spec.split(";") if c.strip()]:
        low = chunk.lower()
        if low.startswith("dir:"):  # garden-d
            contract.garden_dir = chunk[4:].strip()
        elif low.startswith("watch:"):
            contract.observe.extend(
                t.strip() for t in chunk[6:].split(",") if t.strip()
            )
        elif low.startswith("security:"):
            contract.security.extend(
                t.strip() for t in chunk[9:].split(",") if t.strip()
            )
        elif low.startswith("out:"):
            contract.out_of_scope.extend(
                t.strip() for t in chunk[4:].split(",") if t.strip()
            )
        elif low.startswith("done:"):
            contract.done_when = chunk[5:].strip()
        elif low.startswith("max:"):
            try:
                contract.max_subtasks = max(1, int(chunk[4:].strip()))
            except ValueError:
                pass
        else:
            contract.in_scope.extend(
                t.strip() for t in chunk.split(",") if t.strip()
            )
    return goal, contract


# ── persistence (beside the session file — her persistence) ──────────────


def _scope_path(session_id: str, data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    return Path(data_dir) / "sessions" / f"{session_id}.scope.json"


def save_scope(session_id: str, contract: ScopeContract,
               data_dir: Path | None = None) -> Path:
    path = _scope_path(session_id, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(contract.as_dict(), indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def load_scope(session_id: str, data_dir: Path | None = None) -> ScopeContract | None:
    """None when no contract was declared (fully backward compatible) or on
    any read failure — scope is a discipline, never a crash."""
    try:
        path = _scope_path(session_id, data_dir)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return ScopeContract(
            goal=data.get("goal", ""),
            in_scope=list(data.get("in_scope", [])),
            out_of_scope=list(data.get("out_of_scope", [])),
            done_when=data.get("done_when", ""),
            max_subtasks=int(data.get("max_subtasks", 12)),
            observe=list(data.get("observe", [])),
            security=list(data.get("security", [])),
            garden_dir=str(data.get("garden_dir", "")),  # garden-d
        )
    except Exception:  # noqa: BLE001
        return None
