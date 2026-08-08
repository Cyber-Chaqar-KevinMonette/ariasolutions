"""tools/frugality_tools.py — Aria plans how far she can go on the hardware she has.

  frugality_catalog (T0) — the scored hardware-reduction technique catalog (honest tradeoffs).
  frugality_plan    (T0) — given a target model size + VRAM budget, the technique stack that fits + cost.

Read-only. The constructive, honest answer to hardware limits — never "the hardware isn't good enough."
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class FrugalityCatalogTool(Tool):
    """The god-tier hardware-reduction technique catalog, honestly scored.

    FAILURE MODES: read_error
    """

    name = "frugality_catalog"
    tier = 0
    description = (
        "List Aria's hardware-requirement-reduction techniques (ternary BitNet, int8/4-bit quant, QLoRA, "
        "gradient checkpointing, CPU/NVMe offload, distillation, sub-quadratic attention, quantum "
        "co-processor) — each scored by VRAM/compute saving, quality cost, effort, and status. Read-only. "
        "FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        status: str = Field("", description="Optional filter: built | available | planned.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.frugality import techniques
            items = techniques.by_status(args.status) if args.status else techniques.catalog()
            out = {"techniques": items,
                   "inference_stack": techniques.stack_for_inference(),
                   "training_stack": techniques.stack_for_training()}
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")
        return ToolResult(ok=True, output=out, metadata={"source": "frugality_catalog"})


class FrugalityPlanTool(Tool):
    """Plan which frugality stack fits a target model in the VRAM budget, with honest cost.

    FAILURE MODES: plan_error
    """

    name = "frugality_plan"
    tier = 0
    description = (
        "Given a target parameter count and VRAM budget (default ~6GB on the GTX 1070), compute the "
        "honest memory math and which frugality stack (ternary / int8 / checkpointing / QLoRA / offload) "
        "lets it fit — for inference or training. Read-only. FAILURE MODES: plan_error"
    )
    failure_modes = ("plan_error",)

    class Args(BaseModel):
        target_params: int = Field(..., ge=1, description="Target model size in parameters (e.g. 50000000).")
        mode: str = Field("inference", description="'inference' or 'training'.")
        budget_gb: float = Field(6.0, gt=0, description="Usable VRAM budget in GB.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.frugality import planner
            out = planner.plan(args.target_params, budget_gb=args.budget_gb, mode=args.mode)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"plan_error: {exc!r}")
        return ToolResult(ok=True, output=out, metadata={"source": "frugality_plan"})
