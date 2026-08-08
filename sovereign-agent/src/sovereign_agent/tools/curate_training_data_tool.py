"""curate_training_data_tool.py — Tier 1: her own hands on the fine-tune
data pipeline.

Kevin, 2026-07-21: "Prepare Aria and me for this work." The training half
(model_trainer.py) is Claude's to run — a real GPU training pass doesn't
fit her bounded-subtask shape. But CURATING the data is exactly the kind
of bounded, reviewable Tier-1 work she's built for: read her own real
history, harden it, report the honest yield.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class _Args(BaseModel):
    pass


class CurateTrainingDataTool(Tool[_Args]):
    name = "curate_training_data"
    tier = 1
    description = (
        "Extract + harden a fine-tuning dataset from your own real history "
        "(atoms.db + completed session subtasks). Redacts any secrets, "
        "drops duplicates and failures, reports exactly what was kept and "
        "why. Read-only over the source data; writes only the dataset "
        "file itself. Use this to prepare training data for a fine-tune "
        "run — the actual training is a separate, longer step run by the "
        "operator. "
        "FAILURE MODES: no_source_data (not an error — just an empty "
        "dataset, report it plainly)."
    )
    failure_modes = ("no_source_data",)
    Args = _Args

    async def execute(self, args: _Args, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        from ..config import SETTINGS
        from ..training_data import build_training_dataset

        try:
            path = SETTINGS.paths.data_dir / "training" / "dataset.jsonl"
            report = build_training_dataset(SETTINGS.paths.data_dir, path)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"curation failed: {e}")

        return ToolResult(
            ok=True,
            output={
                "dataset_path": str(path),
                "input_count": report.input_count,
                "redacted_count": report.redacted_count,
                "dropped_duplicate": report.dropped_duplicate,
                "dropped_too_short": report.dropped_too_short,
                "dropped_too_long": report.dropped_too_long,
                "output_count": report.output_count,
            },
            metadata={"output_count": report.output_count},
        )


__all__ = ["CurateTrainingDataTool"]
