"""nonclassical/robustness.py — god-tier hardening checks for the non-classical (PEIG/quantum) layer.

God-tier demands the non-classical hemisphere be as robust as the classical one. This module verifies the
properties that make a layer trustworthy: DETERMINISM (same seed → same result), GRACEFUL DEGRADATION
(missing/empty corpus → still runs, never crashes), and BOUNDED LEARNING (word_acc stays in [0,1] and the
learning curve is well-formed). Read-only; reports findings. Reuses sovereign_agent.quantum.brain.
"""
from __future__ import annotations


def _brain(**kw):
    from sovereign_agent.quantum.brain import NestedBrain
    return NestedBrain(**kw)


def check_determinism(seed: int = 2026) -> dict:
    """Same seed → same learning curve. A non-deterministic brain can't be trusted or reproduced."""
    try:
        a = _brain(seed=seed).train(epochs=8, gen_len=40)
        b = _brain(seed=seed).train(epochs=8, gen_len=40)
        same = [round(x["word_acc"], 6) for x in a] == [round(y["word_acc"], 6) for y in b]
        return {"ok": same, "note": "deterministic with seed" if same else "NON-deterministic — same seed diverged"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": repr(exc)}


def check_graceful_degradation() -> dict:
    """Empty / tiny / missing corpus must NOT crash — it degrades, never wedges."""
    findings = []
    for label, kw in (("empty corpus", {"corpus": "", "vocab": []}),
                      ("tiny corpus", {"corpus": "a", "vocab": ["a"]}),
                      ("defaults", {})):
        try:
            br = _brain(**kw)
            curve = br.train(epochs=3, gen_len=20)
            _ = br.speak(length=20)
            findings.append({"case": label, "ok": True, "epochs": len(curve)})
        except Exception as exc:  # noqa: BLE001
            findings.append({"case": label, "ok": False, "error": repr(exc)})
    return {"ok": all(f["ok"] for f in findings), "cases": findings,
            "note": "degrades gracefully on empty/tiny corpora" if all(f["ok"] for f in findings)
                    else "a degenerate corpus crashed the layer — harden it"}


def check_bounded_learning(seed: int = 7) -> dict:
    """word_acc must stay in [0,1] and the curve be well-formed (the optimized metric stays sane)."""
    try:
        curve = _brain(seed=seed).train(epochs=20, gen_len=60)
        accs = [c["word_acc"] for c in curve]
        in_range = all(0.0 <= a <= 1.0 for a in accs)
        rose = accs[-1] >= accs[0]
        return {"ok": in_range, "in_range": in_range, "rose": rose,
                "first": round(accs[0], 4), "last": round(accs[-1], 4),
                "note": "bounded + learning" if in_range and rose else "word_acc out of bounds or not learning"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": repr(exc)}


def robustness_scan() -> dict:
    det = check_determinism()
    deg = check_graceful_degradation()
    bnd = check_bounded_learning()
    ok = all(x.get("ok") for x in (det, deg, bnd))
    return {"god_tier_robust": ok, "determinism": det, "graceful_degradation": deg,
            "bounded_learning": bnd,
            "note": "Non-classical layer is god-tier robust." if ok else "Non-classical robustness gap — see findings."}
