"""model_corps/bases.py — the ONE standing source of truth for "what base
model + temperature does each aria-<role> run on."

model-corps-unify-d (Kevin, 2026-07-21): "Just rebuild the entire models
system if you have to and make it nice." Root problem this closes: there
used to be TWO places that could each independently decide a role's base
model —

  1. `scripts/regen_model_corps.sh`'s own hardcoded bash associative array
     (BASE_MODEL/TEMPERATURE), and
  2. `model_ladder.promote_slot()`, which wrote a RAW proven model straight
     into the vault (AGENT_<SLOT>_MODEL), bypassing the persona entirely —
     confirmed as a real bug this same session (a "promoted" coder briefly
     lost its god-tier hardening until caught and fixed by hand).

Now there is exactly one file (`bases.json`, checked into the repo next to
this module, the same way `GOD_TIER_STANDARD.md` is checked in) and exactly
one code path that turns "role X should run on base model Y" into a real,
dressed, live `aria-<role>` Ollama model: `build_modelfile_text()` +
`create_model()` below. `promote_slot()` calls these directly instead of
touching the vault. `scripts/regen_model_corps.sh` reads the same file
instead of its own copy, so the two can never drift apart again.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .persona import ROLES, build_role_persona

# Only the 6 real Ollama-model roles participate in bases.json / the
# ladder — orchestrator_fast (sprint-mode-d) is a persona ALIAS on a
# testing-only model, never a standing base with its own registry entry.
_SLOTS = tuple(r for r in ROLES if r != "orchestrator_fast")

_DEFAULT_NUM_CTX = 16384


def _bases_path() -> Path:
    return Path(__file__).parent / "bases.json"


def load_bases() -> dict[str, dict]:
    """{role: {"model": ..., "temperature": ...}}. Never raises — a
    missing or corrupt file degrades to an empty dict, not a crash; every
    caller already handles an unknown/absent role gracefully."""
    try:
        data = json.loads(_bases_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_bases(bases: dict) -> None:
    """Atomic write — the same tmp+replace discipline used everywhere
    else state gets persisted in this codebase."""
    path = _bases_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(bases, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def set_base(role: str, model: str, *, temperature: float | None = None,
             num_ctx: int | None = None) -> None:
    """Record role's new base model — the durable, standing change (not
    just a live `ollama create`, which alone would silently regress the
    next time anyone re-runs the regen script).

    no-offloading-d (Kevin, 2026-07-28): "no GPU offloading allowed" --
    `num_ctx` is now a per-role override (falls back to
    `_DEFAULT_NUM_CTX` when never set), since the shared 16384 default
    was itself found forcing partial CPU offload on this hardware. Set
    via `model_ladder.dress_slot_no_offload`, which searches for the
    largest context size that keeps a role's model 100% GPU-resident
    before calling this -- never guessed or hand-picked."""
    if role not in _SLOTS:
        raise ValueError(f"unknown model_corps role {role!r}; expected one of {_SLOTS}")
    bases = load_bases()
    entry = dict(bases.get(role, {}))
    entry["model"] = model
    if temperature is not None:
        entry["temperature"] = temperature
    if num_ctx is not None:
        entry["num_ctx"] = num_ctx
    bases[role] = entry
    save_bases(bases)


def build_modelfile_text(role: str) -> str:
    """The exact Modelfile text for aria-<role> — FROM the role's current
    base + the shared god-tier persona + its temperature/num_ctx. The ONE
    place this composition happens; `scripts/regen_model_corps.sh` and
    `promote_slot()` both go through this now instead of each building
    their own copy."""
    bases = load_bases()
    entry = bases.get(role)
    if entry is None:
        raise ValueError(f"no base configured for role {role!r} in bases.json")
    base_model = entry["model"]
    temperature = entry.get("temperature", 0.3)
    num_ctx = entry.get("num_ctx", _DEFAULT_NUM_CTX)
    persona = build_role_persona(role if role in ROLES else "orchestrator")
    return (
        f"FROM {base_model}\n\n"
        f'SYSTEM """\n{persona}\n"""\n\n'
        f"PARAMETER temperature {temperature}\n"
        f"PARAMETER num_ctx {num_ctx}\n"
    )


@dataclass
class CreateResult:
    ok: bool
    model_tag: str
    detail: str = ""


def create_model(role: str, *, runner=None) -> CreateResult:
    """Actually build + register aria-<role> in Ollama on its current
    configured base. Runs `ollama create` — a real, live-impact call, but
    idempotent (overwrites the existing tag) and never touches any OTHER
    role. Never raises; failures come back as CreateResult(ok=False, ...)."""
    tag = f"aria-{role.replace('_', '-')}"
    try:
        text = build_modelfile_text(role)
    except ValueError as exc:
        return CreateResult(ok=False, model_tag=tag, detail=str(exc))

    run = runner or (lambda argv, **kw: subprocess.run(
        argv, capture_output=True, text=True, timeout=900, **kw))
    with tempfile.NamedTemporaryFile(
            mode="w", suffix=".Modelfile", delete=False, encoding="utf-8") as f:
        f.write(text)
        modelfile_path = f.name
    try:
        result = run(["ollama", "create", tag, "-f", modelfile_path])
        ok = getattr(result, "returncode", 1) == 0
        detail = (getattr(result, "stderr", "") or getattr(result, "stdout", "")).strip()
        return CreateResult(ok=ok, model_tag=tag, detail=detail if not ok else "created")
    except Exception as exc:  # noqa: BLE001
        return CreateResult(ok=False, model_tag=tag, detail=f"{type(exc).__name__}: {exc}")
    finally:
        try:
            Path(modelfile_path).unlink(missing_ok=True)
        except OSError:
            pass


__all__ = [
    "load_bases", "save_bases", "set_base", "build_modelfile_text",
    "create_model", "CreateResult",
]
