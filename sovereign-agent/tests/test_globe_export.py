"""Tests for the Godot globe export tool (Block 13.1 visualization schema)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


def _tool():
    from sovereign_agent.tools.globe_export_tool import QuantumGlobeExportTool
    return QuantumGlobeExportTool()


def _run(coro):
    return asyncio.run(coro)


def test_export_tool_t1():
    assert _tool().tier == 1


def test_export_writes_valid_schema():
    t = _tool()
    res = _run(t.execute(t.Args(), trace_id="t"))
    assert res.ok
    assert res.output["schema"] == "godot-peig-globe-v1"
    assert res.output["node_count"] == 13
    assert res.output["edge_count"] == 48
    # file written + parseable
    path = Path(res.output["written_to"])
    assert path.exists()
    data = json.loads(path.read_text())
    assert len(data["nodes"]) == 12          # 12 outer; center is separate
    assert data["center"]["name"] == "Aria"
    assert data["center"]["pos"] == [0.0, 0.0, 0.0]


def test_export_nodes_have_positions_and_schema():
    t = _tool()
    res = _run(t.execute(t.Args(), trace_id="t"))
    data = json.loads(Path(res.output["written_to"]).read_text())
    for n in data["nodes"]:
        assert {"name", "family", "pos", "phase", "PCM_rel", "negfrac", "color_hint"} <= set(n)
        assert len(n["pos"]) == 3


def test_export_edges_have_types():
    t = _tool()
    res = _run(t.execute(t.Args(), trace_id="t"))
    data = json.loads(Path(res.output["written_to"]).read_text())
    types = {e["type"] for e in data["edges"]}
    assert {"ring", "skip1", "cross", "spoke"} <= types


def test_fibonacci_sphere_distinct_points():
    from sovereign_agent.tools.globe_export_tool import _fibonacci_sphere
    pts = _fibonacci_sphere(12, radius=2.0)
    assert len(pts) == 12
    assert len(set(pts)) == 12   # all distinct
