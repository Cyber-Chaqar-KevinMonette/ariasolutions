"""Tests for the resilience / robustness / edge-case scanner — both layers."""
from __future__ import annotations

import asyncio


def test_probe_certifies_a_resilient_function():
    from sovereign_agent.resilience_scan import scanner
    res = scanner.probe_callable(lambda x: str(x)[:10], name="safe", kind="any")
    assert res.resilient and res.score == 1.0   # handles everything → resilient


def test_probe_catches_an_ungraceful_crash():
    from sovereign_agent.resilience_scan import scanner
    def fragile(x):
        return x.upper()                          # crashes on None / list / int (AttributeError)
    res = scanner.probe_callable(fragile, name="fragile", kind="any")
    assert not res.resilient and res.wedged       # the wedge is caught


def test_graceful_valueerror_counts_as_survived():
    from sovereign_agent.resilience_scan import scanner
    def picky(x):
        if not x:
            raise ValueError("empty not allowed")  # declared, graceful rejection
        return x
    res = scanner.probe_callable(picky, name="picky", kind="string")
    assert res.resilient                          # graceful exceptions are fine


def test_probe_catches_a_timeout_wedge():
    from sovereign_agent.resilience_scan import scanner
    def slow(x):
        if isinstance(x, str) and len(x) > 1000:
            while True:                           # hang on huge input
                pass
        return x
    res = scanner.probe_callable(slow, name="slow", kind="string")
    assert not res.resilient and any("TIMEOUT" in w for w in res.wedged)


def test_both_layers_scan_runs():
    from sovereign_agent.resilience_scan import layers
    rep = layers.scan_both_layers()
    assert "classical" in rep and "non_classical" in rep
    # the non-classical layer is resilient (it was built that way)
    assert rep["non_classical"]["all_resilient"] is True


def test_edge_batteries_nonempty():
    from sovereign_agent.resilience_scan import probes
    assert probes.edge_strings() and probes.edge_lists() and probes.edge_numbers() and probes.edge_any()


def test_resilience_sentinel_contract(tmp_path):
    from sovereign_agent.stewardship.resilience_sentinel import ResilienceSentinel
    s = ResilienceSentinel(tmp_path)
    s.bootstrap()
    assert len(s.articles()) >= 3
    h = s.health_status()
    assert h.level in ("ok", "warning", "unknown")


def test_resilience_tool():
    from sovereign_agent.tools.resilience_scan_tools import ResilienceScanTool
    assert ResilienceScanTool.tier == 0
    r = asyncio.run(ResilienceScanTool().execute(ResilienceScanTool.Args(), trace_id="t"))
    assert r.ok and "both_layers_resilient" in r.output
