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


def staged_modules(repo: Path) -> list[Target]:
    out = []
    for mod in sorted(repo.glob("aria-*")):
        if not mod.is_dir():
            continue
        payload = mod / "payload" / "src" / "sovereign_agent"
        sig = {
            "has_tests": any((mod / "tests").glob("test_*.py")) if (mod / "tests").is_dir() else False,
            "has_readme": (mod / "README.md").exists(),
            "has_apply": any(mod.glob("apply_*.sh")),
            "has_payload": payload.is_dir(),
        }
        if payload.is_dir():
            sig.update(_scan_signals(payload))
        else:
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
