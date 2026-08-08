"""Tests for self_map.auto_doc — the map that draws itself."""
from __future__ import annotations

from sovereign_agent.self_map.auto_doc import (
    collect_blueprint,
    collect_cli,
    collect_docs,
    collect_modules,
    collect_sentinels,
    collect_tests,
    render_map,
    write_map,
)


def test_collectors_report_real_inventory():
    mods = dict(collect_modules())
    assert "member_mail" in mods and "model_ladder" in mods
    assert "weather" in mods and "self_map/" in mods
    t = collect_tests()
    assert t["files"] > 100 and t["functions"] > t["files"]
    c = collect_cli()
    assert "models" in c["groups"] and "map" in c["groups"]
    assert len(collect_sentinels()) > 10
    b = collect_blueprint()
    assert "Support" in b["roles"] and b["channels"] > 10
    docs = dict(collect_docs())
    assert docs.get("STRIPE_LOCKIN.md") is True


def test_render_is_complete_and_marked_generated():
    out = render_map(now=1_784_000_000.0)
    for h in ("## Modules", "## Tests", "## CLI", "## Sentinels",
              "## Env-key catalog", "## Discord blueprint", "## Doc registry"):
        assert h in out, h
    assert "GENERATED" in out and "do not hand-edit" in out


def test_write_map_atomic_and_never_raises(tmp_path):
    p = write_map(tmp_path)
    assert p.name == "SYSTEM_MAP_AUTO.md" and p.exists()
    assert "GENERATED" in p.read_text(encoding="utf-8")
    # impossible target → still no exception (duty ticks must survive)
    bad = tmp_path / "nope"
    bad.write_text("a file, not a dir")
    write_map(bad / "sub")
