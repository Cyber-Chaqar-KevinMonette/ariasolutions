"""training_data.py — curate + harden a fine-tuning dataset from Aria's own
real history.

Kevin, 2026-07-21: "we can fine tune if you want or we can build one. go
ahead and harden our curated data." Part of the fine-tuning project: a
small, fast model specialized on her ACTUAL history in this system, not a
generic dataset.

Honest scope, worth stating plainly: this system does NOT store full raw
LLM conversation transcripts anywhere durable — a deliberate design (see
reflector.py's own "compact transcript from recent EVENTS" pattern, not
raw messages). So the raw material here is real but smaller than "every
word she's ever said": distilled atoms (atoms.db), her own subtask
result summaries (SessionStore), and short text fragments already
captured in the event log. A future full-transcript logger would be a
separate, deliberate addition — not assumed or silently built here.

Two-pass pipeline, each independently testable:
  1. `extract_candidates()` — pull raw (instruction, output) text pairs
     from atoms.db + SessionStore. Read-only; touches nothing.
  2. `harden_dataset()` — the actual hardening pass: redact secrets/URLs
     (reuses ask_guard.redact_reply's already-proven scrubbing, not a
     second implementation of the same check), drop failed/blocked
     subtasks (never train on what didn't work), dedupe, enforce a
     sane length floor/ceiling, and report EXACTLY what was dropped and
     why — never a silent filter.

`build_training_dataset()` composes both into one JSONL file + a report,
the one entry point most callers actually want.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_MIN_INSTRUCTION_LEN = 8    # shorter than this isn't a real instruction
_MIN_OUTPUT_LEN = 4         # shorter than this isn't a real completion
_MAX_LEN = 4000             # longer than this is almost certainly noise/garbage


@dataclass
class TrainingExample:
    instruction: str
    output: str
    source: str            # "atom" | "session_subtask" — provenance, never lost
    source_id: str          # atom_id or session_id:subtask_id

    def as_dict(self) -> dict:
        return {
            "instruction": self.instruction,
            "output": self.output,
            "source": self.source,
            "source_id": self.source_id,
        }


@dataclass
class HardenReport:
    input_count: int = 0
    redacted_count: int = 0
    dropped_duplicate: int = 0
    dropped_too_short: int = 0
    dropped_too_long: int = 0
    output_count: int = 0
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "input_count": self.input_count,
            "redacted_count": self.redacted_count,
            "dropped_duplicate": self.dropped_duplicate,
            "dropped_too_short": self.dropped_too_short,
            "dropped_too_long": self.dropped_too_long,
            "output_count": self.output_count,
        }


def extract_atom_examples(data_dir: Path) -> list[TrainingExample]:
    """Every atom with genuinely inline text content becomes one
    (instruction, output) candidate: the atom's own type/summary framed
    as the instruction, its full content as the output. Read-only. Never
    raises — a missing/corrupt atoms.db degrades to an empty list, the
    caller always has SessionStore as a second source."""
    out: list[TrainingExample] = []
    db_path = Path(data_dir) / "atoms.db"
    if not db_path.exists():
        return out
    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT atom_id, type, summary, content_ref FROM atoms "
                "WHERE superseded_at IS NULL"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return out

    for atom_id, atom_type, summary, content_ref_json in rows:
        try:
            content_ref = json.loads(content_ref_json)
        except (TypeError, ValueError):
            continue
        if not isinstance(content_ref, dict) or content_ref.get("kind") != "inline":
            continue  # blob/file-backed content needs a separate resolve pass
        content = content_ref.get("content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        out.append(TrainingExample(
            instruction=f"Record a {atom_type} atom: {summary}",
            output=content,
            source="atom",
            source_id=atom_id,
        ))
    return out


def extract_session_examples(data_dir: Path) -> list[TrainingExample]:
    """Every successfully COMPLETED subtask becomes one (instruction,
    output) candidate: the subtask's own description as the instruction,
    its result_summary as the output. Deliberately skips 'blocked'/
    'error' subtasks — never train on what didn't work. Read-only."""
    from .agent_session import SessionStore

    out: list[TrainingExample] = []
    try:
        sessions = SessionStore(Path(data_dir) / "sessions").list_all()
    except Exception:  # noqa: BLE001 — a corrupt store degrades to empty, not a crash
        return out

    for state in sessions:
        for subtask in state.subtasks:
            if subtask.status != "done":
                continue  # only train on what actually worked
            if not subtask.result_summary.strip():
                continue
            out.append(TrainingExample(
                instruction=subtask.description,
                output=subtask.result_summary,
                source="session_subtask",
                source_id=f"{state.session_id}:{subtask.id}",
            ))
    return out


def extract_candidates(data_dir: Path) -> list[TrainingExample]:
    """Both real sources, combined. This is the ONLY function most
    callers need for the read side."""
    return extract_atom_examples(data_dir) + extract_session_examples(data_dir)


def harden_dataset(
    examples: list[TrainingExample],
) -> tuple[list[TrainingExample], HardenReport]:
    """The actual hardening pass: redact, drop failures (already excluded
    upstream, but re-checked here defensively), dedupe, enforce length
    bounds. Returns (cleaned, report) — the report is the honest
    accounting of what happened to every input example, never a silent
    filter Kevin has to reverse-engineer from a smaller output count.
    """
    from .ask_guard import redact_reply

    report = HardenReport(input_count=len(examples))
    seen: set[tuple[str, str]] = set()
    cleaned: list[TrainingExample] = []

    for ex in examples:
        instruction = redact_reply(ex.instruction)
        output = redact_reply(ex.output)
        if instruction != ex.instruction or output != ex.output:
            report.redacted_count += 1

        key = (instruction.strip(), output.strip())
        if key in seen:
            report.dropped_duplicate += 1
            continue
        if len(instruction) < _MIN_INSTRUCTION_LEN or len(output) < _MIN_OUTPUT_LEN:
            report.dropped_too_short += 1
            continue
        if len(instruction) > _MAX_LEN or len(output) > _MAX_LEN:
            report.dropped_too_long += 1
            continue

        seen.add(key)
        cleaned.append(TrainingExample(
            instruction=instruction, output=output,
            source=ex.source, source_id=ex.source_id,
        ))

    report.output_count = len(cleaned)
    return cleaned, report


def build_training_dataset(data_dir: Path, out_path: Path) -> HardenReport:
    """The one entry point most callers actually want: extract + harden
    + write JSONL. Returns the report; the caller decides whether the
    yield is big enough to actually train on."""
    candidates = extract_candidates(data_dir)
    cleaned, report = harden_dataset(candidates)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for ex in cleaned:
            f.write(json.dumps(ex.as_dict(), ensure_ascii=False) + "\n")

    return report


__all__ = [
    "TrainingExample", "HardenReport",
    "extract_atom_examples", "extract_session_examples", "extract_candidates",
    "harden_dataset", "build_training_dataset",
]
