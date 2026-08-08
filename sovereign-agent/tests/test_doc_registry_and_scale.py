"""R6 tests — vault scale PROVEN (not promised) + the doc registry."""
from __future__ import annotations

import time

from sovereign_agent.credentials import read_env, set_secret, vault_status
from sovereign_agent.doc_registry import (
    DOC_CATALOG,
    compose_docs_report,
    is_docs_query,
    registry_status,
)


# ── vault scale: 2,000 keys stay fast and correct ───────────────────────────
def test_vault_2000_keys_write_read_status_stay_fast(tmp_path):
    vault = tmp_path / "big.env"
    t0 = time.monotonic()
    # bulk-load 1,999 keys the way a fleet would (BOT_<SLUG>_* convention),
    # writing the file directly (one set_secret per key would be 2k rewrites —
    # fine too, but this measures the READ paths that matter at scale)
    lines = [f"export BOT_K{i:04d}_WEBHOOK_URL='https://discord.com/api/webhooks/{i}/tok{i}'"
             for i in range(1999)]
    vault.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # one real set_secret on the full file — the O(n) rewrite path
    set_secret("DISCORD_BOT_TOKEN", "x" * 60, vault)
    elapsed_write = time.monotonic() - t0

    t1 = time.monotonic()
    env = read_env(vault)
    rows = vault_status(vault)
    elapsed_read = time.monotonic() - t1

    assert len(env) == 2000
    assert env["BOT_K0042_WEBHOOK_URL"].endswith("/tok42")
    assert env["DISCORD_BOT_TOKEN"] == "x" * 60
    assert len(rows) >= 2000                      # catalog + customs all present
    # the honest "infinite": O(n) with tiny constants — prove the budget
    assert elapsed_write < 1.0, f"write path too slow: {elapsed_write:.2f}s"
    assert elapsed_read < 1.0, f"read path too slow: {elapsed_read:.2f}s"


def test_vault_set_preserves_all_other_keys_at_scale(tmp_path):
    vault = tmp_path / "big.env"
    for i in range(50):
        set_secret(f"KEY_{i:03d}", f"value-{i}", vault)
    set_secret("KEY_025", "replaced", vault)
    env = read_env(vault)
    assert len(env) == 50 and env["KEY_025"] == "replaced"
    assert env["KEY_049"] == "value-49"


# ── doc registry ─────────────────────────────────────────────────────────────
def test_all_registered_docs_exist_on_disk():
    """The registry IS the guarantee — a missing doc fails the suite by name."""
    missing = [r["rel_path"] for r in registry_status() if not r["exists"]]
    assert missing == [], f"registered docs missing from disk: {missing}"


def test_registry_flags_missing_docs(tmp_path):
    rows = registry_status(tmp_path)              # empty root: nothing exists
    assert all(not r["exists"] for r in rows)
    report = compose_docs_report(tmp_path)
    assert "MISSING" in report


def test_docs_report_lists_titles_and_paths():
    out = compose_docs_report()
    assert "Master Setup Guide" in out and "SETUP_MASTER.md" in out
    assert "all present ✅" in out


def test_catalog_covers_the_essentials():
    rels = {e.rel_path for e in DOC_CATALOG}
    for must in ("SETUP_MASTER.md", "SYSTEM_MAP.md", "CHANGELOG.md",
                 "handoff/05_ENGINEERING_LESSONS.md", "CLAUDE.md"):
        assert must in rels


def test_is_docs_query_precise():
    assert is_docs_query("where is the system map?")
    assert is_docs_query("show me the docs")
    assert not is_docs_query("how are you today")
    assert not is_docs_query("what's in the shop?")
