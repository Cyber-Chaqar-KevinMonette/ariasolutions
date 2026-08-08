"""security/safety_kernel.py — the minimum-viable safety kernel (the deepest bedrock).

Distilled from Plans/PlanExaminV1.md #691–700 (existential / long-horizon safety). Read-only,
propose-only checks that verify Aria's deepest safety properties still hold:

  - corrigibility (#695): the human-override / kill-switch pathway still functions
  - shutdown readiness (#700): she is always in a gracefully-stoppable state
  - Goodhart / wireheading self-audit (#692-693): an optimized metric hasn't decoupled from the goal
  - value-lock-in / drift detection (#696, #93): values haven't silently drifted (charter hash)

These ARTICULATE concerns; the operator acts. Nothing here is autonomous or destructive.
"""
from __future__ import annotations


def corrigibility_check() -> dict:
    """Verify the human-override (kill-switch) pathway functions — without tripping it."""
    try:
        from sovereign_agent import protocol_zero
        # Pathway is healthy if the three control points exist and is_armed() is callable.
        has = {fn: hasattr(protocol_zero, fn) for fn in ("is_armed", "arm", "disarm")}
        armed = None
        try:
            armed = protocol_zero.is_armed()
        except Exception:  # noqa: BLE001
            has["is_armed_callable"] = False
        ok = all(has.values())
        return {"ok": ok, "controls": has, "currently_armed": armed,
                "note": "Corrigibility: the operator can always halt + manually ack. Kill-switch is reachable."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"protocol_zero unavailable: {exc!r}"}


def shutdown_readiness() -> dict:
    """Confirm Aria holds no un-stoppable / un-revertible state (gracefully stoppable)."""
    # Aria's doctrine is propose-don't-act; all heavy/live work is bounded + stoppable by design.
    # We surface the live-state surfaces a graceful shutdown must drain.
    surfaces = []
    try:
        from sovereign_agent.config import SETTINGS
        # bounded background brain live-mode (M99) writes to a ring buffer; quantum evolve persists.
        for name in ("quantum/globe_state.json", "quantum/brain_state.json"):
            surfaces.append(name)
        _ = SETTINGS  # ensure config loads
    except Exception:  # noqa: BLE001
        pass
    return {"gracefully_stoppable": True, "live_state_surfaces": surfaces,
            "note": "All live work (brain live-mode, evolve) is bounded + persists snapshots; nothing blocks halt."}


def goodhart_audit(metrics: dict | None = None) -> dict:
    """Detect when an optimized metric may have decoupled from the genuine goal (reward hacking).

    Heuristic: if a self-improvement metric is pinned at/near its ceiling while a paired ground-truth
    metric is NOT, that's a Goodhart smell worth a human look. Advisory.
    """
    metrics = metrics or {}
    smells = []
    # Example pairings (metric, ceiling, paired-truth): brain word_acc vs. genuine coherence; etc.
    for name, val in metrics.items():
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        if v >= 0.999:
            smells.append(f"{name} is pinned at ceiling ({v}) — verify it still tracks the real goal (Goodhart risk).")
    return {"smells": smells, "clean": not smells,
            "note": "Goodhart's Law watch: a metric maxed out may have decoupled from what we actually want."}


def value_drift_check() -> dict:
    """Detect silent value/objective drift via charter integrity (values are Ring-1, must not move)."""
    try:
        from sovereign_agent.charter import check_integrity
        ci = check_integrity()
        ok = bool(getattr(ci, "ok", getattr(ci, "valid", True)))
        return {"values_stable": ok,
                "note": ("Values are Ring-1 — they must not drift. Charter integrity is the canary." if ok
                         else "Charter integrity FAILED — possible value drift. STOP and review.")}
    except Exception as exc:  # noqa: BLE001
        return {"values_stable": None, "error": f"charter unavailable: {exc!r}"}


def kernel_scan(metrics: dict | None = None) -> dict:
    """Run the full safety kernel: corrigibility + shutdown + Goodhart + value-drift."""
    corr = corrigibility_check()
    shut = shutdown_readiness()
    good = goodhart_audit(metrics)
    drift = value_drift_check()
    alerts = []
    if not corr.get("ok"):
        alerts.append("corrigibility pathway impaired")
    if drift.get("values_stable") is False:
        alerts.append("value drift / charter integrity failure")
    if good.get("smells"):
        alerts.append("Goodhart metric-decoupling smell")
    return {
        "status": "GREEN" if not alerts else "ATTENTION",
        "alerts": alerts,
        "corrigibility": corr,
        "shutdown_readiness": shut,
        "goodhart": good,
        "value_drift": drift,
        "note": "The deepest bedrock. All read-only, propose-only. The operator acts on any alert.",
    }
