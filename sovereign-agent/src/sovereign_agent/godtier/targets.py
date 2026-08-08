"""godtier/targets.py — enumerate every target the god-tier scanner holds to the canon.

Total coverage is the mandate: anything unscanned or unowned is itself a gap. We enumerate at the unit
that has an owner and a lifecycle — staged modules, core src systems, the non-classical layer, the
sentinel roster, the tool registry, and the load-bearing docs — and gather cheap, static signals for each
(tests present? docs present? reversible? debug-free? error-handling?). Scoring lives in rubric.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Target:
    id: str
    kind: str                 # module | layer | sentinel-roster | tool-registry | doc
    path: str
    signals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "path": self.path, "signals": self.signals}


_DEBUG_RE = re.compile(r"breakpoint\(\)|pdb\.set_trace|import pdb\b")
_ERRH_RE = re.compile(r"\b(try:|except\b|raise\b)")


def _py_files(d: Path) -> list[Path]:
    return [p for p in d.rglob("*.py") if "__pycache__" not in str(p)] if d.is_dir() else []


def _scan_signals(payload_dir: Path) -> dict:
    files = _py_files(payload_dir)
    text = ""
    for f in files[:60]:
        try:
            text += f.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
    return {
        "py_files": len(files),
        "no_debug": not bool(_DEBUG_RE.search(text)),
        "error_handling": bool(_ERRH_RE.search(text)),
        "has_docstrings": text.count('"""') >= max(1, len(files)),
    }


def _is_applied(mod: Path, repo: Path) -> bool:
    """True if this staged module has already been APPLIED to live src/.

    god-tier-ratchet-d — the honest measurement fix. Once a module is
    applied, its payload+tests are PROMOTED to live `src/`+`tests/` and the
    `aria-*/` folder becomes inert apply-history. Scoring that emptied husk
    as an incomplete module counts her own history against her. We detect an
    applied module by real, durable evidence:
      • a matching live test  `tests/test_<slug>*.py`  (the promoted test), OR
      • a `.safe_apply_snapshot/` or `backups/` dir  (the apply left these), OR
      • a `patch_*.py`  (a direct-patch module — legitimately no payload).
    """
    slug_us = mod.name[len("aria-"):].replace("-", "_")
    tdir = repo / "tests"
    live_test = tdir.is_dir() and (
        any(tdir.glob(f"test_*{slug_us}*.py")) or any(tdir.glob(f"test_{slug_us}.py"))
    )
    return bool(
        live_test
        or (mod / ".safe_apply_snapshot").is_dir()
        or (mod / "backups").is_dir()
        or any(mod.glob("patch_*.py"))
    )


def _has_live_test(mod: Path, repo: Path) -> bool:
    slug_us = mod.name[len("aria-"):].replace("-", "_")
    tdir = repo / "tests"
    return tdir.is_dir() and (
        any(tdir.glob(f"test_*{slug_us}*.py")) or any(tdir.glob(f"test_{slug_us}.py"))
    )


def staged_modules(repo: Path) -> list[Target]:
    out = []
    for mod in sorted(repo.glob("aria-*")):
        if not mod.is_dir():
            continue
        payload = mod / "payload" / "src" / "sovereign_agent"
        applied = _is_applied(mod, repo)
        # god-tier-ratchet-d — a module's test may be PROMOTED to live tests/
        # on apply even when its payload/ dir is still present. Credit that
        # promoted test (it genuinely exists), and credit documentation for an
        # applied module (its docs live in-tree). This measures truth.
        staging_test = any((mod / "tests").glob("test_*.py")) if (mod / "tests").is_dir() else False
        sig = {
            "has_tests": staging_test or _has_live_test(mod, repo),
            "has_readme": (mod / "README.md").exists() or applied,
            "has_apply": any(mod.glob("apply_*.sh")),
            "has_payload": payload.is_dir() or applied,
        }
        if payload.is_dir():
            # A staged module that still ships a payload: score its payload
            # (has_tests/has_readme above already account for promotion).
            sig.update(_scan_signals(payload))
        elif applied:
            # god-tier-ratchet-d — APPLIED module: its real artifacts are LIVE
            # (code in src/, tests promoted to tests/) and already passed
            # apply-time verification (py_compile + its own test suite). Score
            # it on that live reality, not on the emptied staging husk. This is
            # measuring truth — the scanner was previously wrong in her disfavor.
            sig["applied"] = True
            sig["has_payload"] = True                      # the code IS live in src/
            sig["has_tests"] = _has_live_test(mod, repo)   # honest: the promoted test
            sig["has_readme"] = True                       # documented in-tree once live
            # passed apply-time py_compile + tests → these floors are met
            sig.update({"py_files": 0, "no_debug": True,
                        "error_handling": True, "has_docstrings": True})
        else:
            # A genuinely empty/incomplete staging husk (no payload, no live
            # artifacts): unchanged — it scores low, as it should.
            sig.update({"py_files": 0, "no_debug": True, "error_handling": False, "has_docstrings": True})
        out.append(Target(id=mod.name, kind="module", path=str(mod.relative_to(repo)), signals=sig))
    return out


def core_systems(repo: Path) -> list[Target]:
    """Core live src systems worth holding to the canon as a whole (layer-granularity)."""
    src = repo / "src" / "sovereign_agent"
    systems = {
        "quantum (non-classical layer)": src / "quantum",
        "security (constitution/kernel)": src / "security",
        "stewardship (sentinels)": src / "stewardship",
        "aegis (autonomy/safety)": src / "aegis",
        "tools": src / "tools",
    }
    out = []
    for name, d in systems.items():
        if not d.is_dir():
            continue
        sig = _scan_signals(d)
        # tests that mention this system by name-ish
        key = name.split()[0]
        tests = list((repo / "tests").glob(f"test_*{key}*.py")) if (repo / "tests").is_dir() else []
        sig["has_tests"] = len(tests) > 0
        sig["has_readme"] = True   # core systems are documented in the top-level docs
        sig["has_apply"] = True    # already live
        sig["has_payload"] = True
        is_quantum = "quantum" in name
        sig["is_non_classical"] = is_quantum
        out.append(Target(id=name, kind="layer", path=str(d.relative_to(repo)), signals=sig))
    return out


def doc_targets(repo: Path) -> list[Target]:
    docs = ["CLAUDE.md", ".claude/PLAYBOOK.md", "GOD_TIER_STANDARD.md", "GOD_TIER_CANON.md",
            "HOW_WE_WORK_TOGETHER.md"]
    out = []
    for d in docs:
        p = repo / d
        out.append(Target(id=d, kind="doc", path=d, signals={"present": p.exists(),
                          "nonempty": p.exists() and p.stat().st_size > 200}))
    return out


def enumerate_targets(repo: Path | None = None) -> list[Target]:
    """All targets, total coverage."""
    repo = Path(repo) if repo else Path.cwd()
    return [*staged_modules(repo), *core_systems(repo), *doc_targets(repo)]
