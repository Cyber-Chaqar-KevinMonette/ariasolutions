"""scripts/lib/aria_conftest.py — ONE reusable test path-shim for staged aria-* modules.

Staged modules live in `aria-<name>/payload/src/sovereign_agent/...` and are NOT in the live `src/`
tree until their apply script runs. To test them BEFORE apply, we extend the imported package's
`__path__` in-process — non-mutating, process-local. Every module's `tests/conftest.py` used to
reinvent this; now it is two lines:

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parents[2] / "scripts" / "lib"))
    from aria_conftest import extend_paths
    extend_paths(pathlib.Path(__file__).parent.parent)   # the aria-<name>/ folder

This never touches live `src/`. It only teaches the already-imported `sovereign_agent` package (and its
subpackages) to also look inside the staging payload.
"""
from __future__ import annotations

from pathlib import Path

# Subpackages a staged module may extend (so e.g. sovereign_agent.tools.<new>_tools resolves).
_DEFAULT_SUBPKGS = ("tools", "stewardship", "security", "aria_lm", "tribunal", "foresight", "frugality")


def extend_paths(module_root: Path, *, subpkgs: tuple[str, ...] = _DEFAULT_SUBPKGS,
                 extra_roots: tuple[Path, ...] = ()) -> list[str]:
    """Teach the imported sovereign_agent package to also resolve from a staging payload.

    `module_root` is the `aria-<name>/` folder; its payload is `module_root/payload/src/sovereign_agent`.
    `extra_roots` lets a module also pull in a sibling module's payload (e.g. frugality needs aria_lm
    from aria-own-mind). Returns the list of paths added (for debugging).
    """
    import sovereign_agent

    added: list[str] = []
    roots = [Path(module_root) / "payload" / "src" / "sovereign_agent", *(_norm(r) for r in extra_roots)]
    for root in roots:
        if not root.is_dir():
            continue
        if str(root) not in sovereign_agent.__path__:
            sovereign_agent.__path__.append(str(root))
            added.append(str(root))
        for sub in subpkgs:
            d = root / sub
            if not d.is_dir():
                continue
            try:
                pkg = __import__(f"sovereign_agent.{sub}", fromlist=[sub])
            except Exception:  # noqa: BLE001 — subpackage may not exist live yet; skip gracefully
                continue
            if hasattr(pkg, "__path__") and str(d) not in pkg.__path__:
                pkg.__path__.append(str(d))
                added.append(str(d))
    return added


def _norm(r: Path) -> Path:
    """Accept either an aria-<name>/ folder or a direct payload sovereign_agent root."""
    r = Path(r)
    if (r / "payload" / "src" / "sovereign_agent").is_dir():
        return r / "payload" / "src" / "sovereign_agent"
    return r
