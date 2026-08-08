"""tools/health_record_tool.py — RecordHealthFactTool. People-Health round.

Tier 3, requires_approval=True: a scoped-but-persistent write of sensitive
third-party-capable PII. Third-party health data is irreversible-in-
consequence even though technically redactable in the DB (redaction
tombstones the row; it does not un-happen the disclosure that already
occurred), so this sits at the top authority tier alongside other
unscoped/high-consequence writes.

Resolves the person by name (via the existing PeopleChannel.resolve())
rather than requiring a raw person_id — the natural shape for a model
tool call driven by conversation ("record that Kevin has seasonal
allergies"). The consent gate itself lives in PeopleHealthChannel.
record_health_fact() — this tool does not duplicate that check, it just
surfaces whatever ConsentRequiredError comes back as an honest failure.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..tools.base import Tool, ToolResult


class _RecordHealthFactArgs(BaseModel):
    person_name: str = Field(description="The person's name (resolved via the People channel).")
    kind: str = Field(description="One of: condition, medication, allergy, appointment, vitals, note.")
    value: str = Field(description="The health fact itself.")
    dosage: str | None = Field(default=None, description="For medication facts, e.g. '2 puffs as needed'.")
    severity: str | None = Field(default=None, description="Free-form severity, e.g. 'mild', 'severe'.")
    source: str = Field(default="operator", description="operator | llm | import | inferred.")


class RecordHealthFactTool(Tool[_RecordHealthFactArgs]):
    name = "record_health_fact"
    tier = 3
    requires_approval = True
    description = (
        "Record a health fact (condition/medication/allergy/appointment/vitals/note) "
        "about a known person, offline. T3 — requires operator approval. Refuses "
        "(ConsentRequiredError) if the person is not the principal and hasn't "
        "explicitly consented to health tracking."
    )
    failure_modes = (
        "person_not_found",
        "consent_required",
        "invalid_kind_or_confidence",
    )
    Args = _RecordHealthFactArgs

    async def execute(self, args: _RecordHealthFactArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        import asyncio

        def _run() -> dict:
            from ..db import open_atoms_db
            from ..mem_channels.people import PeopleChannel
            from ..mem_channels.people_health import PeopleHealthChannel

            conn = open_atoms_db()
            try:
                pc = PeopleChannel(conn)
                person = pc.resolve(args.person_name)
                if person is None:
                    raise KeyError(f"no known person matching {args.person_name!r}")
                phc = PeopleHealthChannel(conn)
                record = phc.record_health_fact(
                    person_id=person.person_id, kind=args.kind, value=args.value,
                    dosage=args.dosage, severity=args.severity,
                    source=args.source,  # type: ignore[arg-type]
                    idempotency_id=f"tool:{trace_id}",
                )
                return {
                    "record_id": record.record_id, "person_id": person.person_id,
                    "person_name": person.canonical_name, "kind": record.kind,
                    "value": record.value, "status": record.status,
                }
            finally:
                conn.close()

        try:
            output = await asyncio.to_thread(_run)
            return ToolResult(ok=True, output=output)
        except KeyError as e:
            return ToolResult(ok=False, error=f"person_not_found: {e}")
        except PermissionError as e:
            return ToolResult(ok=False, error=f"consent_required: {e}")
        except ValueError as e:
            return ToolResult(ok=False, error=f"invalid_kind_or_confidence: {e}")
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"record_health_fact failed: {e}")
