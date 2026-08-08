"""model_corps — the god-tier model roster: one shared hardened persona, generated
from mos_canon.py's frozen priorities + GOD_TIER_STANDARD.md's nine floor
dimensions, regenerated into every role's Ollama Modelfile by
`scripts/regen_model_corps.sh`. Staged; applied via apply_model_corps.sh."""
from __future__ import annotations

from .bases import (
    CreateResult,
    build_modelfile_text,
    create_model,
    load_bases,
    save_bases,
    set_base,
)
from .persona import (
    ROLES,
    build_god_tier_preamble,
    build_role_persona,
    parse_god_tier_dimensions,
)

__all__ = [
    "ROLES",
    "build_god_tier_preamble",
    "build_role_persona",
    "parse_god_tier_dimensions",
    "CreateResult",
    "build_modelfile_text",
    "create_model",
    "load_bases",
    "save_bases",
    "set_base",
]
