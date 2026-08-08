"""godtier/enhance.py — turn a god-tier gap into a concrete, propose-only enhancement.

Neglect is never god-tier. For a gap, draft (do NOT apply) a god-tier enhancement: the specific fix steps,
the scaffold command, and the Tribunal/foresight check to run. The drafting is hers — she names her own
weak points and proposes her own upgrades — but a human always applies. Reversible by construction.
"""
from __future__ import annotations

# gap message → concrete god-tier remediation step
_REMEDIES = {
    "no tests": "Add behavioral tests under tests/ that PROVE it works (not just imports). Run /aria-verify.",
    "no README": "Write a README: what it gives Aria, honestly, with verified results.",
    "no apply script": "Add an apply_<pkg>.sh from scripts/lib/apply_template.sh so it's reversibly applied.",
    "debugger": "Remove the breakpoint()/pdb from the payload (cleanliness floor).",
    "no error handling": "Add try/except + graceful degradation for the failure modes; never wedge.",
    "thin docstrings": "Add module + function docstrings stating intent + contract.",
    "non-classical parity": "Add robustness + parity tests so the non-classical layer is god-tier-on-par.",
    "no payload": "Confirm this is doc/script-only; if it should ship code, add the payload package.",
    "empty/stub": "Fill the doc with real, honest content.",
    "missing": "Create the document.",
}


def draft_for(scored_target: dict) -> dict:
    """Given a scored target (from rubric/scanner), draft a propose-only god-tier enhancement."""
    tid = scored_target.get("id", "?")
    gaps = scored_target.get("gaps", [])
    steps = []
    for g in gaps:
        gl = g.lower()
        step = next((v for k, v in _REMEDIES.items() if k in gl), f"Address: {g}")
        steps.append(step)
    slug = _slugify(tid)
    return {
        "target": tid,
        "band": scored_target.get("band"),
        "score": scored_target.get("score"),
        "gaps": gaps,
        "remediation_steps": steps,
        "scaffold_cmd": (f"./scripts/new_module.sh {slug}-godtier" if scored_target.get("kind") != "module"
                         else f"# enhance in place: {tid}"),
        "gate": f"./scripts/pre_apply_gate.sh aria-{slug}-godtier   # Tribunal + 14-gen foresight before apply",
        "note": "Propose-only. A human applies. Reversible by construction.",
    }


def draft_all(gaps_list: list[dict], limit: int = 10) -> list[dict]:
    return [draft_for(g) for g in gaps_list[:limit]]


def _slugify(name: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in name.lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:40] or "target"
