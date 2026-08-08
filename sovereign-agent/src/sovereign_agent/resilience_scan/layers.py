"""resilience_scan/layers.py — certify BOTH layers (classical + non-classical) resilient.

Runs the edge battery over representative entry points of each layer and reports whether each degrades
gracefully. Classical: text-processing helpers. Non-classical: the superposition processor + the PEIG brain.
Honest: it reports exactly which (if any) entry points wedge, per layer.
"""
from __future__ import annotations

from . import scanner


def scan_non_classical() -> list[dict]:
    """Probe the non-classical entry points with edge inputs."""
    out = []
    # superposition processor: process(query, candidates) — probe with edge queries + edge candidate lists
    try:
        from sovereign_agent.nonclassical_supreme import superpose
        out.append(scanner.probe_callable(
            lambda q: superpose.process(q if isinstance(q, str) else str(q), ["a", "b", "c"], seed=0),
            name="nc.superpose.process(query)", kind="string").to_dict())
        out.append(scanner.probe_callable(
            lambda c: superpose.process("pick", c if isinstance(c, list) else [str(c)], seed=0),
            name="nc.superpose.process(candidates)", kind="list").to_dict())
    except Exception as exc:  # noqa: BLE001
        out.append({"target": "nc.superpose", "resilient": None, "note": f"unavailable: {exc!r}"})
    # PEIG brain: gen_text / score_text on edge inputs
    try:
        from sovereign_agent.quantum.brain import NestedBrain
        br = NestedBrain(seed=1)
        out.append(scanner.probe_callable(
            lambda s: br.score_text(s if isinstance(s, str) else str(s), 0, 10),
            name="nc.brain.score_text", kind="string").to_dict())
    except Exception as exc:  # noqa: BLE001
        out.append({"target": "nc.brain", "resilient": None, "note": f"unavailable: {exc!r}"})
    return out


def scan_classical() -> list[dict]:
    """Probe representative classical entry points with edge inputs."""
    out = []
    try:
        from sovereign_agent.tribunal import grounding
        out.append(scanner.probe_callable(grounding.analyze, name="classical.grounding.analyze",
                                          kind="string").to_dict())
    except Exception as exc:  # noqa: BLE001
        out.append({"target": "classical.grounding", "resilient": None, "note": f"unavailable: {exc!r}"})
    try:
        from sovereign_agent.foresight import foresight as _f
        out.append(scanner.probe_callable(lambda s: _f.project(s if isinstance(s, str) else str(s)),
                                          name="classical.foresight.project", kind="string").to_dict())
    except Exception as exc:  # noqa: BLE001
        out.append({"target": "classical.foresight", "resilient": None, "note": f"unavailable: {exc!r}"})
    return out


def scan_both_layers() -> dict:
    """The cross-layer resilience certification."""
    cl = scan_classical()
    nc = scan_non_classical()
    def _ok(rows):
        checked = [r for r in rows if r.get("resilient") is not None]
        return all(r["resilient"] for r in checked) if checked else None
    return {
        "classical": {"targets": cl, "all_resilient": _ok(cl)},
        "non_classical": {"targets": nc, "all_resilient": _ok(nc)},
        "both_layers_resilient": bool(_ok(cl)) and bool(_ok(nc)),
        "note": "God-tier resilience holds for BOTH layers when every probed entry point degrades gracefully.",
    }
