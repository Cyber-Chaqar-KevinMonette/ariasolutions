"""tools/brain_bench_tools.py — Brain speed benchmark + flood-guarded free speech.

  brain_benchmark (T0) — honest local generative latency (mean/p50/p95) + stated baseline context
  brain_speak     (T1) — free, generous speech, flood-guarded by a hard character cap
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class BrainBenchmarkTool(Tool):
    """Measure the non-classical brain's local generative latency (honest, no over-claim). Read-only.

    FAILURE MODES: bench_error
    """

    name = "brain_benchmark"
    tier = 0
    description = (
        "Benchmark the non-classical brain's LOCAL generative latency (mean/p50/p95 ms) over N runs. "
        "Honest: local, no API; not a same-task LLM-reasoning replacement; baseline is a stated reference. "
        "The brain earns higher roles only by proving faster AND better at scale. FAILURE MODES: bench_error"
    )
    failure_modes = ("bench_error",)

    class Args(BaseModel):
        runs: int = Field(default=50, description="Number of timed runs (5-500).")
        length: int = Field(default=80, description="Generated text length per run.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.quantum.brain_bench import benchmark
            result = benchmark(SETTINGS.paths.data_dir, runs=args.runs, length=args.length)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"bench_error: {exc!r}")
        return ToolResult(ok=True, output=result, metadata={"source": "brain_benchmark"})


class BrainSpeakTool(Tool):
    """Let Aria's nested brain speak freely (generous verbosity, flood-guarded). FAILURE MODES: speak_error"""

    name = "brain_speak"
    tier = 1
    description = (
        "Generate free speech from Aria's nested brain at a chosen length/temperature. Generous but "
        "FLOOD-GUARDED (hard character cap) so output never floods the system. Returns text + vocab "
        "coherence. FAILURE MODES: speak_error"
    )
    failure_modes = ("speak_error",)

    class Args(BaseModel):
        length: int = Field(default=120, description="Generation length (1-1200).")
        temp: float = Field(default=0.25, description="Temperature (0.05-1.5); lower = more focused.")
        max_chars: int = Field(default=2000, description="Hard flood cap on output chars.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.quantum.brain_bench import free_speak
            result = free_speak(SETTINGS.paths.data_dir, length=args.length, temp=args.temp,
                                max_chars=max(100, min(20000, args.max_chars)))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"speak_error: {exc!r}")
        return ToolResult(ok=True, output=result, metadata={"source": "brain_speak"})
