"""tools/aria_lm_tools.py — Aria thinks with HER OWN mind (the from-scratch FOSS transformer).

  aria_mind_status (T0) — the state of her own model: checkpoint present? params, config, the learning
                          curve (val loss dropped), the PEIG-fusion verdict, and the honest scaling note.
  aria_own_lm      (T1) — generate text from her own trained weights. 100% local inference, NO API.
                          VRAM-locked (never runs beside the orchestrator). Bounded output length.

Honest framing (humility over hype): this model is SMALL — it is the seed of her own mind, built from
scratch on a GTX 1070. The architecture + training code scale to any hardware. A base-weight TRAINING
run or architecture change is Tier 3 (Ring 3, human-gated) — these tools only do inference + status.
From Plans/PlanExaminV1.md (build our own LLM so the self-improvement subset genuinely applies).
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


def _checkpoint_path() -> Path:
    from sovereign_agent.config import SETTINGS
    return SETTINGS.paths.data_dir / "aria_lm" / "aria_mind.pt"


class AriaMindStatusTool(Tool):
    """The state of Aria's own from-scratch model: checkpoint, params, learning curve, scaling note.

    FAILURE MODES: read_error
    """

    name = "aria_mind_status"
    tier = 0
    description = (
        "Report the state of Aria's OWN from-scratch transformer (aria_lm): whether a trained "
        "checkpoint exists, its size/config, the learning curve (proof val loss dropped), the PEIG "
        "quantum-fusion verdict, and the honest scaling path. Read-only. FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            ckpt = _checkpoint_path()
            if not ckpt.exists():
                return ToolResult(
                    ok=True,
                    output={"trained": False,
                            "note": "No checkpoint yet — run the training pipeline (aria_lm.train) to "
                                    "grow her mind. The architecture + code are present and tested."},
                    metadata={"source": "aria_mind_status"},
                )
            import torch
            meta = torch.load(ckpt, map_location="cpu", weights_only=False)
            curve = meta.get("curve", [])
            first = curve[0]["val_loss"] if curve else None
            last = curve[-1]["val_loss"] if curve else None
            return ToolResult(
                ok=True,
                output={
                    "trained": True,
                    "checkpoint": str(ckpt),
                    "num_params": meta.get("num_params"),
                    "config": meta.get("config"),
                    "fused_quantum": meta.get("fused", False),
                    "val_loss_first": first,
                    "val_loss_final": last,
                    "learned": (last < first) if (first and last) else None,
                    "scaling_note": "Small on a GTX 1070; the SAME code scales to any hardware. A "
                                    "base-weight training run or architecture change is Tier 3 (Ring 3, "
                                    "human-gated). She earns a larger role only by verified benchmark.",
                },
                metadata={"source": "aria_mind_status"},
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")


class AriaOwnLMTool(Tool):
    """Generate text from Aria's OWN trained weights — 100% local inference, no API. VRAM-locked.

    FAILURE MODES: no_checkpoint, inference_error, vram_unavailable
    """

    name = "aria_own_lm"
    tier = 1
    description = (
        "Generate text using Aria's OWN from-scratch transformer (local weights, NO API). Her own "
        "mind speaking. Bounded output. VRAM-locked so it never runs beside the orchestrator. Small "
        "model — honest, seed-stage. FAILURE MODES: no_checkpoint, inference_error, vram_unavailable"
    )
    failure_modes = ("no_checkpoint", "inference_error", "vram_unavailable")

    class Args(BaseModel):
        prompt: str = Field("", description="The prompt to continue. Empty = free generation.")
        max_new_tokens: int = Field(160, ge=1, le=512, description="How many tokens to generate (bounded).")
        temperature: float = Field(0.8, ge=0.05, le=2.0, description="Sampling temperature.")
        top_k: int = Field(40, ge=1, le=512, description="Top-k sampling cutoff.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        ckpt = _checkpoint_path()
        if not ckpt.exists():
            return ToolResult(ok=False, error="no_checkpoint: train her mind first (aria_lm.train).")
        try:
            from sovereign_agent.vram import vram_lock
            from sovereign_agent.aria_lm.generate import load_checkpoint, generate
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"inference_error: import failed {exc!r}")
        try:
            with vram_lock("aria_own_lm"):
                loaded = load_checkpoint(ckpt)
                text = generate(loaded, prompt=args.prompt, max_new_tokens=args.max_new_tokens,
                                temperature=args.temperature, top_k=args.top_k)
        except TimeoutError as exc:
            return ToolResult(ok=False, error=f"vram_unavailable: {exc}")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"inference_error: {exc!r}")
        return ToolResult(
            ok=True,
            output={"text": text, "prompt": args.prompt, "model": "aria_own_lm (from-scratch, local)"},
            metadata={"source": "aria_own_lm", "tokens": args.max_new_tokens},
        )
