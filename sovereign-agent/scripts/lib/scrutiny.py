"""scripts/lib/scrutiny.py — load + run the Tribunal + 14-gen foresight over a text/module.

Works whether tribunal/foresight are staged (aria-tribunal/, aria-foresight/) or already applied to
live src. Used by scripts/pre_apply_gate.sh and the /aria-scrutinize skill.

    python3 scripts/lib/scrutiny.py --text "..."          # scrutinize a string
    python3 scripts/lib/scrutiny.py --module aria-foo     # scrutinize a module's README
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "lib"))


def _ensure_engines() -> None:
    """Make sovereign_agent.tribunal + .foresight importable (staged or live)."""
    try:
        import sovereign_agent.tribunal  # noqa: F401
        import sovereign_agent.foresight  # noqa: F401
        return
    except Exception:
        pass
    from aria_conftest import extend_paths
    for mod in ("aria-tribunal", "aria-foresight", "aria-own-mind", "aria-advocate-spectrum"):
        p = REPO / mod
        if p.is_dir():
            extend_paths(p)


def scrutinize(text: str) -> dict:
    _ensure_engines()
    out: dict = {}
    try:
        from sovereign_agent.tribunal import convene
        v = convene({"text": text}, repo_root=REPO, include_kernel=True)
        out["tribunal"] = {"verdict": v.verdict, "confidence": v.confidence, "rationale": v.rationale,
                           "grounding": v.audit.get("grounding", {}).get("verdict"),
                           "risks": v.risks[:5], "paths_forward": v.paths_forward[:5]}
    except Exception as exc:  # noqa: BLE001
        out["tribunal"] = {"error": repr(exc)}
    try:
        from sovereign_agent.spectrum import convene_spectrum
        cv = convene_spectrum({"text": text})
        out["spectrum"] = {"verdict": cv.verdict, "council_score": round(cv.council_score, 2),
                           "champions": cv.champions, "opposed": cv.opposed}
    except Exception:  # noqa: BLE001 — spectrum optional; tribunal+foresight still gate
        pass
    try:
        from sovereign_agent.foresight import project
        f = project({"text": text})
        out["foresight"] = {"verdict": f.verdict, "gen7": f.gen7_equity, "gen14": f.gen14_equity,
                            "base": f.base_equity, "signals": f.signals}
    except Exception as exc:  # noqa: BLE001
        out["foresight"] = {"error": repr(exc)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="")
    ap.add_argument("--module", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    text = a.text
    if a.module:
        mod = REPO / a.module
        readme = mod / "README.md"
        text = readme.read_text(encoding="utf-8", errors="ignore") if readme.exists() else f"module {a.module}"
    if not text:
        print("provide --text or --module"); return 2

    res = scrutinize(text)
    if a.json:
        print(json.dumps(res, indent=2)); return 0

    t, f = res.get("tribunal", {}), res.get("foresight", {})
    print("── Tribunal ──")
    if "error" in t:
        print(f"   (unavailable: {t['error']})")
    else:
        print(f"   VERDICT: {t['verdict']}  (confidence {t['confidence']})  · grounding: {t['grounding']}")
        print(f"   {t['rationale']}")
        for r in t.get("risks", []):
            print(f"   risk: {r}")
        for p in t.get("paths_forward", [])[:3]:
            print(f"   → {p}")
    sp = res.get("spectrum")
    if sp:
        print("── Advocate Spectrum (council of ten) ──")
        print(f"   VERDICT: {sp['verdict']}  · council {sp['council_score']}  · champions {sp['champions']}  · opposed {sp['opposed']}")
    print("── 14-Generation Foresight ──")
    if "error" in f:
        print(f"   (unavailable: {f['error']})")
    else:
        print(f"   VERDICT: {f['verdict']}  · base {f['base']} · gen7 {f['gen7']} · gen14 {f['gen14']}")
        print(f"   signals: {f['signals']}")
    # exit non-zero if any voice says stop
    bad = (t.get("verdict") in ("reject", "hold")
           or f.get("verdict") == "reject-for-the-future"
           or (sp or {}).get("verdict") in ("reject", "hold"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
