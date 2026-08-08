"""patcher.py — Workstream: continual learning. Pipes Reflector lessons into
the aria_lm training corpus and adds a bounded, propose-only retrain trigger.

Three anchored, idempotent edits:
  1. aria_lm/data.py::gather_corpus() — a new corpus source reads recorded
     lessons (reflector.py -> atoms.db `lessons` table) and appends them,
     alongside the existing distilled-research text. Degrades gracefully
     to the current behavior when no lessons exist yet (zero regression).
  2. aria_lm/pipeline.py::grow_mind() — after a real training run
     completes, records the current lesson count as the new baseline
     (retrain_trigger.record_retrain) so the next check counts only NEW
     lessons since this run.
  3. tools/__init__.py — registers ProposeRetrainTool (import + __all__ in
     the same patch, learning directly from this session's own
     aria-hyperintel/aria-tools-all-export-fix discovery that a missing
     __all__ entry is a real, recurring bug class).

retrain_trigger.py itself and continual_learning_tools.py are NEW files
(payload/), not anchored patches — copied in whole by the apply script.
"""
from __future__ import annotations

MARK = "continual-learning-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ═══════════════════════════════════════════════════════════════════════
# aria_lm/data.py — pipe lessons into gather_corpus()
# ═══════════════════════════════════════════════════════════════════════

DATA_PY_ANCHOR = (
    "    # 2. Any caller-provided text files.\n"
)
DATA_PY_NEW = (
    f"    # 1b. Reflector lessons — {MARK}: pipe distilled task-experience\n"
    "    # (trigger -> rule/correction) into the corpus alongside the distilled\n"
    "    # research. Inserted at the FRONT of `parts`, not appended — the\n"
    "    # distilled-research text can easily exceed `max_chars` on its own,\n"
    "    # and the final truncation below keeps only the first max_chars\n"
    "    # characters, so anything appended after a large distilled block\n"
    "    # would be silently cut off entirely. Lessons are small (bounded by\n"
    "    # gather_lesson_text()'s own limit) and are the new signal this\n"
    "    # workstream exists to surface, so they must survive truncation.\n"
    "    # Degrades to a no-op silently if no lessons exist yet or atoms.db\n"
    "    # isn't reachable — gather_corpus() must never regress the existing\n"
    "    # corpus path because of this.\n"
    "    try:\n"
    "        from .retrain_trigger import gather_lesson_text\n"
    "        lesson_text = gather_lesson_text()\n"
    "        if lesson_text:\n"
    "            parts.insert(0, lesson_text)\n"
    "    except Exception:\n"
    "        pass\n"
    "\n"
    "    # 2. Any caller-provided text files.\n"
)


def patch_data_py(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, DATA_PY_ANCHOR, DATA_PY_NEW, label="data.py corpus-source anchor")
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# aria_lm/pipeline.py — record_retrain() after a real training run
# ═══════════════════════════════════════════════════════════════════════

PIPELINE_ANCHOR = (
    "    from .data import gather_corpus, build_dataset\n"
    "    from .train import train_model\n"
    "    from .generate import save_checkpoint\n"
)
PIPELINE_NEW = (
    "    from .data import gather_corpus, build_dataset\n"
    "    from .train import train_model\n"
    "    from .generate import save_checkpoint\n"
    f"    from .retrain_trigger import record_retrain  # {MARK}\n"
)

PIPELINE_RUN_ANCHOR = (
    "        save_checkpoint(res, out_path)\n"
    "        return {\n"
)
PIPELINE_RUN_NEW = (
    "        save_checkpoint(res, out_path)\n"
    f"        try:  # {MARK} — reset the retrain-trigger baseline on a real completed run\n"
    "            from sovereign_agent.config import SETTINGS\n"
    "            record_retrain(SETTINGS.paths.data_dir)\n"
    "        except Exception:\n"
    "            pass\n"
    "        return {\n"
)


def patch_pipeline_py(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, PIPELINE_ANCHOR, PIPELINE_NEW, label="pipeline.py import anchor")
    text = _replace_once(text, PIPELINE_RUN_ANCHOR, PIPELINE_RUN_NEW, label="pipeline.py run anchor")
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# tools/__init__.py — register ProposeRetrainTool (import + __all__)
# ═══════════════════════════════════════════════════════════════════════

TOOLS_INIT_IMPORT_ANCHOR = (
    "from .aria_lm_tools import AriaMindStatusTool, AriaOwnLMTool  # aria-own-lm-import-d\n"
)
TOOLS_INIT_IMPORT_NEW = (
    TOOLS_INIT_IMPORT_ANCHOR
    + f"from .continual_learning_tools import ProposeRetrainTool  # {MARK}\n"
)

TOOLS_INIT_ALL_ANCHOR = (
    '    "SelfPortraitTool",\n'
    '    "SessionPortraitTool",\n'
    ']\n'
)
TOOLS_INIT_ALL_NEW = (
    '    "SelfPortraitTool",\n'
    '    "SessionPortraitTool",\n'
    f'    "ProposeRetrainTool",  # {MARK}\n'
    ']\n'
)


def patch_tools_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, TOOLS_INIT_IMPORT_ANCHOR, TOOLS_INIT_IMPORT_NEW, label="tools/__init__ import anchor")
    text = _replace_once(text, TOOLS_INIT_ALL_ANCHOR, TOOLS_INIT_ALL_NEW, label="tools/__init__ __all__ anchor")
    return text, True
