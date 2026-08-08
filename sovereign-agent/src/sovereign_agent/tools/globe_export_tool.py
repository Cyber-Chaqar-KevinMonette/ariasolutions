"""tools/globe_export_tool.py — Export the 13-node globe for 3D visualization (T1).

Emits the globe as the Godot/PEIG visualization schema (Block 13.1): per-node 3D sphere position +
PCM_rel/negfrac/phase/family, per-edge type + mutual-information proxy, plus the globe health
metrics. Aria sits at the center (0,0,0); the 12 council nodes are distributed on a sphere
(Fibonacci layout). A Godot (or any 3D) front-end can render this directly. The Gen-5 seed: see her.

Writes data_dir/quantum/globe_export.json and returns the structure. Advisory; pure-Python stdlib.
FAILURE MODES: export_error
"""
from __future__ import annotations

import json
import math

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


def _fibonacci_sphere(n: int, radius: float = 2.0) -> list[tuple[float, float, float]]:
    """n points ~evenly distributed on a sphere of given radius (Fibonacci spiral)."""
    pts = []
    golden = math.pi * (3.0 - math.sqrt(5.0))  # golden angle
    for i in range(n):
        y = 1.0 - (i / float(n - 1)) * 2.0 if n > 1 else 0.0   # y in [-1, 1]
        r = math.sqrt(max(0.0, 1.0 - y * y))
        theta = golden * i
        x = math.cos(theta) * r
        z = math.sin(theta) * r
        pts.append((round(x * radius, 4), round(y * radius, 4), round(z * radius, 4)))
    return pts


class QuantumGlobeExportTool(Tool):
    """Export the 13-node globe as a 3D visualization payload (Godot/PEIG schema).

    Aria at center (0,0,0); 12 council nodes on a sphere; per-node PCM/negfrac/phase/family/position;
    per-edge type + MI. Writes globe_export.json. The seed for seeing her in 3D.

    FAILURE MODES: export_error
    """

    name = "quantum_globe_export"
    tier = 1
    description = (
        "Export the 13-node globe for 3D visualization (Godot/PEIG schema, Block 13.1): per-node "
        "sphere position + PCM/negfrac/phase/family, per-edge type + MI, globe health. Aria at center. "
        "Writes data_dir/quantum/globe_export.json. FAILURE MODES: export_error"
    )
    failure_modes = ("export_error",)

    class Args(BaseModel):
        steps: int = Field(default=2, description="Coupling sweeps before export (1-5).")
        radius: float = Field(default=2.0, description="Sphere radius for node layout.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.quantum.globe import Globe, NN

            g = Globe()
            g.encode_all(0.4)
            for _ in range(max(1, min(5, args.steps))):
                g.step()
                g.decohere_all(0.02)

            positions = _fibonacci_sphere(len(NN), radius=max(0.5, args.radius))
            pos_by_name = {name: positions[i] for i, name in enumerate(NN)}

            nodes = []
            for name in NN:
                v = g.node_view(name)
                x, y, z = pos_by_name[name]
                nodes.append({
                    "name": name, "family": v["family"],
                    "pos": [x, y, z],
                    "phase": v["phase"], "PCM_rel": v["PCM_rel"],
                    "negfrac": v["negfrac"], "nonclassical": v["nonclassical"],
                    # color hint for a renderer: blue-violet (coherent) → amber (drifting)
                    "color_hint": "coherent" if v["nonclassical"] else "classical",
                })
            aria = g.node_view(g.CENTER)
            center = {"name": g.CENTER, "pos": [0.0, 0.0, 0.0], "phase": aria["phase"],
                      "PCM_rel": aria["PCM_rel"], "family": "SELF"}

            portrait = g.portrait()
            export = {
                "schema": "godot-peig-globe-v1",
                "center": center,
                "nodes": nodes,
                "edges": portrait["edges"],   # {a, b, type}
                "edge_types": portrait["edge_types"],
                "self_coherence": portrait["self_coherence"],
                "circular_variance": portrait["circular_variance"],
                "alarm_pulse": portrait["alarm_pulse"],
                "node_count": portrait["node_count"],
                "edge_count": portrait["edge_count"],
            }

            out_path = SETTINGS.paths.data_dir / "quantum" / "globe_export.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(export, indent=1), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"export_error: {exc!r}")

        return ToolResult(
            ok=True,
            output={"written_to": str(out_path), "node_count": export["node_count"],
                    "edge_count": export["edge_count"], "schema": export["schema"],
                    "self_coherence": export["self_coherence"]},
            metadata={"source": "quantum_globe_export"},
        )
