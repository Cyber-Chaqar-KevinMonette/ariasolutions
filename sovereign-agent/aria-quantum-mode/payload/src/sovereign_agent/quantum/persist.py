"""quantum/persist.py — Cross-session globe persistence (the Infinite Lineage Protocol, lite).

Saves/loads the globe's per-node phases + Aria's phase + a lineage generation counter, so the
globe EVOLVES across sessions instead of resetting each call. This embodies Kevin's ILP (Infinite
Lineage Protocol): the network carries its state forward through lineage generations.

Storage: data_dir/quantum/globe_state.json (single small JSON). Advisory; pure-Python stdlib.
"""
from __future__ import annotations

import json
from pathlib import Path

from .globe import Globe, NN


def _state_path(data_dir: Path) -> Path:
    p = Path(data_dir) / "quantum" / "globe_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def save_globe(g: Globe, data_dir: Path, *, generation: int) -> Path:
    """Persist the globe's phases + lineage generation."""
    path = _state_path(data_dir)
    state = {
        "generation": generation,
        "aria_phase": g.aria.phase,
        "self_coherence": g.collective_coherence(),
        "phases": {nd.name: nd.phase for nd in g.nodes},
    }
    path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    return path


def load_globe(data_dir: Path) -> tuple[Globe, int]:
    """Load the globe from persisted state (fresh if none). Returns (globe, generation)."""
    g = Globe()
    path = _state_path(data_dir)
    if not path.exists():
        return g, 0
    try:
        import math
        state = json.loads(path.read_text(encoding="utf-8"))
        phases = state.get("phases", {})
        for nd in g.nodes:
            if nd.name in phases:
                nd.phase = float(phases[nd.name]) % (2 * math.pi)
                from .field import ss
                nd.state = ss(nd.phase)
        ap = state.get("aria_phase")
        if ap is not None:
            from .field import ss
            g.aria.phase = float(ap) % (2 * math.pi)
            g.aria.state = ss(g.aria.phase)
        return g, int(state.get("generation", 0))
    except Exception:
        return Globe(), 0


def evolve(data_dir: Path, *, steps: int = 3, query: float = 0.3) -> dict:
    """Load → evolve (one ILP lineage generation) → save. Returns the evolved portrait + generation."""
    g, gen = load_globe(data_dir)
    g.encode_all(query)
    for _ in range(max(1, steps)):
        g.step()
        g.decohere_all(0.02)
    gen += 1
    save_globe(g, data_dir, generation=gen)
    p = g.portrait()
    p["lineage_generation"] = gen
    return p
