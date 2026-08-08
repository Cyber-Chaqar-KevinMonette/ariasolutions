"""self_map.auto_doc — 🗺 the map that draws itself (Kevin, 2026-07-17).

"Instead of you refreshing the map constantly, can we build a system
that does it for you? This way it could save us usage and processing."

Exactly that: every MECHANICAL fact about the system — module inventory,
test counts, CLI command tree, env-key catalog, sentinel census, server
blueprint shape, doc-registry health — is DERIVED from the code itself
and written to `SYSTEM_MAP_AUTO.md`. Nobody hand-edits inventory lines
again; a session (human or AI) only writes the NARRATIVE map
(SYSTEM_MAP.md) when architecture actually changes.

Lives inside the self_map package: `build_self_map` is her live wiring
introspection; THIS module is the durable, human-readable doc that
refreshes itself. Refresh paths:
  • `sov map refresh` — explicit, anytime;
  • the duty loop regenerates it at each day boundary (crash-isolated).

Everything degrades honestly: a collector that fails reports "(couldn't
collect: …)" for its section and the rest of the map still writes.
"""
from __future__ import annotations

import ast
import time
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _pkg_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _first_doc_line(py: Path) -> str:
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
        doc = ast.get_docstring(tree) or ""
        return doc.strip().splitlines()[0][:90] if doc.strip() else ""
    except Exception:  # noqa: BLE001
        return ""


def collect_modules() -> list[tuple[str, str]]:
    """(name, first docstring line) for every top-level module + package."""
    d = _pkg_dir()
    out: list[tuple[str, str]] = []
    for py in sorted(d.glob("*.py")):
        if py.name.startswith("_"):
            continue
        out.append((py.stem, _first_doc_line(py)))
    for sub in sorted(p for p in d.iterdir()
                      if p.is_dir() and (p / "__init__.py").exists()):
        out.append((sub.name + "/", _first_doc_line(sub / "__init__.py")))
    return out


def collect_tests(root: Path | None = None) -> dict:
    tests = (root or repo_root()) / "tests"
    files = sorted(tests.glob("test_*.py"))
    n_funcs = 0
    for f in files:
        try:
            n_funcs += f.read_text(encoding="utf-8").count("def test_")
        except Exception:  # noqa: BLE001
            continue
    return {"files": len(files), "functions": n_funcs}


def collect_cli() -> dict:
    from sovereign_agent.cli import app
    groups = sorted(g.name or "?" for g in app.registered_groups)
    commands = sorted((c.name or getattr(c.callback, "__name__", "?"))
                      for c in app.registered_commands)
    return {"groups": groups, "commands": commands}


def collect_sentinels() -> list[str]:
    d = _pkg_dir() / "stewardship"
    return sorted(p.stem for p in d.glob("*_sentinel.py"))


def collect_env_catalog() -> list[str]:
    from sovereign_agent.credentials import CRED_CATALOG
    return [c.name for c in CRED_CATALOG]


def collect_blueprint() -> dict:
    from sovereign_agent.discord_admin.blueprint import shop_blueprint
    from sovereign_agent.discord_admin.server_plan import blueprint_fingerprint
    bp = shop_blueprint()
    channels = sum(len(c.channels) for c in bp.categories)
    return {"roles": bp.role_names(),
            "categories": [c.name for c in bp.categories],
            "channels": channels,
            "fingerprint": blueprint_fingerprint(bp)[:16]}


def collect_docs() -> list[tuple[str, bool]]:
    from sovereign_agent.doc_registry import registry_status
    return [(d["rel_path"], bool(d["exists"])) for d in registry_status()]


def render_map(now: float | None = None) -> str:
    """Compose the whole auto-map. Section failures degrade in place."""
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(now or time.time()))
    L: list[str] = [
        "# SYSTEM_MAP_AUTO.md — the map that draws itself",
        "",
        f"> GENERATED {stamp} by `sov map refresh` — **do not hand-edit** "
        "(it will be overwritten). The narrative architecture map is "
        "`SYSTEM_MAP.md`; THIS file is the live mechanical inventory, "
        "auto-refreshed by the duty loop at each day boundary.",
        "",
    ]

    def section(title: str, fn) -> None:
        L.append(f"## {title}")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            L.append(f"(couldn't collect: {type(exc).__name__}: {exc})")
        L.append("")

    def _modules() -> None:
        mods = collect_modules()
        L.append(f"{len(mods)} top-level modules/packages in "
                 "`src/sovereign_agent/`:")
        L.append("")
        for name, doc in mods:
            L.append(f"- `{name}`" + (f" — {doc}" if doc else ""))

    def _tests() -> None:
        t = collect_tests()
        L.append(f"{t['files']} test files · ~{t['functions']} test functions "
                 "(counted, not narrated).")

    def _cli() -> None:
        c = collect_cli()
        L.append(f"{len(c['commands'])} root commands · "
                 f"{len(c['groups'])} command groups:")
        L.append("")
        L.append("`" + "` · `".join(c["groups"]) + "`")

    def _sentinels() -> None:
        s = collect_sentinels()
        L.append(f"{len(s)} sentinels in `stewardship/`:")
        L.append("")
        L.append("`" + "` · `".join(s) + "`")

    def _env() -> None:
        names = collect_env_catalog()
        L.append(f"{len(names)} cataloged keys (vault: "
                 "`~/.config/sovereign-agent/shop.env`, masked always):")
        L.append("")
        L.append("`" + "` · `".join(names) + "`")

    def _blueprint() -> None:
        b = collect_blueprint()
        L.append(f"{len(b['roles'])} roles · {len(b['categories'])} "
                 f"categories · {b['channels']} channels · fingerprint "
                 f"`{b['fingerprint']}…`")
        L.append("")
        L.append("roles: " + ", ".join(b["roles"]))
        L.append("categories: " + ", ".join(b["categories"]))

    def _docs() -> None:
        docs = collect_docs()
        missing = [p for p, ok in docs if not ok]
        L.append(f"{len(docs)} registered docs — "
                 + ("all present ✅" if not missing
                    else f"MISSING: {', '.join(missing)}"))

    section("Modules", _modules)
    section("Tests", _tests)
    section("CLI (`sov`)", _cli)
    section("Sentinels", _sentinels)
    section("Env-key catalog", _env)
    section("Discord blueprint", _blueprint)
    section("Doc registry", _docs)
    return "\n".join(L) + "\n"


def write_map(root: Path | None = None, *, now: float | None = None) -> Path:
    """Render + atomically write SYSTEM_MAP_AUTO.md. Never raises."""
    path = (root or repo_root()) / "SYSTEM_MAP_AUTO.md"
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(render_map(now), encoding="utf-8")
        tmp.replace(path)
    except Exception:  # noqa: BLE001 — mapping must never sink a duty tick
        pass
    return path


__all__ = ["collect_modules", "collect_tests", "collect_cli",
           "collect_sentinels", "collect_env_catalog", "collect_blueprint",
           "collect_docs", "render_map", "write_map", "repo_root"]
