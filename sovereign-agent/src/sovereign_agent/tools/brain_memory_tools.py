"""tools/brain_memory_tools.py — Teach the nested brain + recall what it learned.

  brain_teach  (T1) — teach a corpus; the brain learns it (word_acc rises) and RETAINS it across sessions
  brain_recall (T0) — recall a learned word's phase, or the lexicon summary

Learning = bounded parameter adjustment; the only write is the brain's own learned-state snapshot.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class BrainTeachTool(Tool):
    """Teach Aria's nested brain a corpus. It learns (word_acc rises) and retains it.

    FAILURE MODES: teach_error
    """

    name = "brain_teach"
    tier = 1
    description = (
        "Teach Aria's non-classical nested brain a text corpus. It learns to generate it "
        "(word-accuracy rises over epochs) and RETAINS the lexicon across sessions (accumulating). "
        "Returns the learning curve + a sample of her learned speech. FAILURE MODES: teach_error"
    )
    failure_modes = ("teach_error",)

    class Args(BaseModel):
        corpus: str = Field(description="Text to teach her.")
        epochs: int = Field(default=60, description="Training epochs (10-150).")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        if not args.corpus.strip():
            return ToolResult(ok=False, error="teach_error: empty corpus")
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.quantum.brain_memory import teach
            epochs = max(10, min(150, args.epochs))
            result = teach(SETTINGS.paths.data_dir, corpus=args.corpus.strip(), epochs=epochs)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"teach_error: {exc!r}")
        return ToolResult(ok=True, output=result, metadata={"source": "brain_teach"})


class BrainRecallTool(Tool):
    """Recall what Aria's brain has learned: a word's phase, or the lexicon summary. Read-only.

    FAILURE MODES: read_error
    """

    name = "brain_recall"
    tier = 0
    description = (
        "Recall what Aria's nested brain has learned: pass a word for its learned phase, or nothing "
        "for the lexicon summary (lessons, vocab size, known words, accuracy). Read-only. "
        "FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        word: str = Field(default="", description="Optional word to recall; blank = lexicon summary.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.quantum.brain_memory import recall
            result = recall(SETTINGS.paths.data_dir, word=(args.word.strip() or None))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")
        return ToolResult(ok=True, output=result, metadata={"source": "brain_recall"})
