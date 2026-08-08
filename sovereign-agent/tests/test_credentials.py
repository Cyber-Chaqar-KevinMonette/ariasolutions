"""Tests for credentials.py — the Key Vault. Security-relevant: prove the
masking, the 0600 mode, preservation, and that no display path leaks a value."""
from __future__ import annotations

import json
import os
import stat

import pytest

from sovereign_agent.credentials import (
    CRED_CATALOG,
    compose_credentials_report,
    env_path,
    is_credentials_query,
    last_set_at,
    mask,
    read_env,
    relative_time,
    remove_secret,
    set_secret,
    validate_value,
    vault_status,
)

SECRET = "MTA1234567890abcdefghijklmnopqrstuvwxyz1234567890ABCD"


def _vault(tmp_path):
    return tmp_path / "keys" / "shop.env"


# ── store round-trip + file safety ──────────────────────────────────────────
def test_set_and_read_round_trip(tmp_path):
    p = _vault(tmp_path)
    set_secret("DISCORD_BOT_TOKEN", SECRET, p)
    assert read_env(p)["DISCORD_BOT_TOKEN"] == SECRET


def test_file_mode_is_0600(tmp_path):
    p = _vault(tmp_path)
    set_secret("DISCORD_BOT_TOKEN", SECRET, p)
    mode = stat.S_IMODE(os.stat(p).st_mode)
    assert mode == 0o600            # only the owner can read the vault


def test_preserves_comments_and_other_lines(tmp_path):
    p = _vault(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("# my precious comment\nexport OTHER='keep-me'\n", encoding="utf-8")
    set_secret("DISCORD_OWNER_ID", "12345", p)
    text = p.read_text()
    assert "# my precious comment" in text and "keep-me" in text
    assert read_env(p) == {"OTHER": "keep-me", "DISCORD_OWNER_ID": "12345"}


def test_replaces_existing_and_collapses_duplicates(tmp_path):
    p = _vault(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("export K1='old'\nexport K1='older'\n", encoding="utf-8")
    set_secret("K1", "new", p)
    assert p.read_text().count("K1") == 1
    assert read_env(p)["K1"] == "new"


def test_quote_safe_values(tmp_path):
    p = _vault(tmp_path)
    tricky = "abc'def\"ghi$`~"
    set_secret("CUSTOM_KEY", tricky, p)
    assert read_env(p)["CUSTOM_KEY"] == tricky


def test_set_updates_current_process_env(tmp_path, monkeypatch):
    monkeypatch.delenv("MY_TEST_VAULT_KEY", raising=False)
    set_secret("MY_TEST_VAULT_KEY", "live-now", _vault(tmp_path))
    assert os.environ["MY_TEST_VAULT_KEY"] == "live-now"
    os.environ.pop("MY_TEST_VAULT_KEY", None)


def test_set_rejects_bad_names_and_empty(tmp_path):
    p = _vault(tmp_path)
    with pytest.raises(ValueError):
        set_secret("bad name!", "x", p)          # spaces/punct → invalid
    with pytest.raises(ValueError):
        set_secret("GOOD_NAME", "   ", p)        # blank value
    with pytest.raises(ValueError):
        set_secret("GOOD_NAME", "two\nlines", p) # multi-line value


def test_set_normalizes_lowercase_names(tmp_path):
    p = _vault(tmp_path)
    set_secret("my_custom_key", "v", p)          # friendly: upper-cased for you
    assert read_env(p)["MY_CUSTOM_KEY"] == "v"


def test_remove(tmp_path):
    p = _vault(tmp_path)
    set_secret("GONE_SOON", "value", p)
    assert remove_secret("GONE_SOON", p) is True
    assert "GONE_SOON" not in read_env(p)
    assert remove_secret("GONE_SOON", p) is False


def test_env_path_override(monkeypatch, tmp_path):
    target = tmp_path / "custom.env"
    monkeypatch.setenv("ARIA_KEYS_FILE", str(target))
    assert env_path() == target


# ── masking: no display path can leak ───────────────────────────────────────
def test_mask_never_reveals_more_than_last4():
    assert mask(SECRET) == "••••" + SECRET[-4:]
    assert mask("short") == "••••(set)"
    assert mask("") == "(not set)"


def test_vault_status_and_report_never_contain_the_value(tmp_path):
    p = _vault(tmp_path)
    set_secret("DISCORD_BOT_TOKEN", SECRET, p)
    set_secret("MY_CUSTOM_THING", "super-secret-password-9876", p)
    for row in vault_status(p):
        assert SECRET not in str(row) and "super-secret-password" not in str(row)
    report = compose_credentials_report(p)
    assert SECRET not in report and "super-secret-password" not in report
    assert "MY_CUSTOM_THING" in report        # the NAME may show — never the value


def test_status_covers_catalog_plus_custom(tmp_path):
    p = _vault(tmp_path)
    set_secret("MY_CUSTOM_THING", "v", p)
    rows = vault_status(p)
    names = [r["name"] for r in rows]
    assert all(spec.name in names for spec in CRED_CATALOG)
    custom = next(r for r in rows if r["name"] == "MY_CUSTOM_THING")
    assert custom["custom"] and custom["set"]


# ── validation (warn-only) + report + bridge ────────────────────────────────
def test_validate_warns_but_never_blocks(tmp_path):
    assert validate_value("DISCORD_OWNER_ID", "not-digits")
    assert validate_value("DISCORD_WEBHOOK_URL", "https://example.com/x")
    assert validate_value("STRIPE_SECRET_KEY", "pk_wrong")
    assert validate_value("DISCORD_OWNER_ID", "123456789") == []
    # a "bad" value still saves — warn-only by design
    p = _vault(tmp_path)
    set_secret("DISCORD_OWNER_ID", "not-digits", p)
    assert read_env(p)["DISCORD_OWNER_ID"] == "not-digits"


def test_report_shows_ready_vs_missing(tmp_path):
    p = _vault(tmp_path)
    set_secret("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/x", p)
    rep = compose_credentials_report(p)
    assert "🟢 base delivery" in rep or "🟢" in rep
    assert "missing" in rep                      # admin bot vars not set yet
    assert "DISCORD_BOT_TOKEN" in rep


def test_is_credentials_query():
    assert is_credentials_query("is your key vault set up?")
    assert is_credentials_query("which keys are missing?")
    assert not is_credentials_query("how are you today")
    assert not is_credentials_query("what's in the shop?")


def test_catalog_covers_every_shop_feature():
    """Kevin: the keys menu should be as complete as possible — every env
    var the shop stack reads must be teachable from the catalog."""
    from sovereign_agent.credentials import CRED_CATALOG
    names = {c.name for c in CRED_CATALOG}
    for needed in ("DISCORD_WEBHOOK_URL", "DISCORD_SHOP_WEBHOOK_URL",
                   "DISCORD_STATUS_WEBHOOK_URL", "DISCORD_ADS_WEBHOOK_URL",
                   "DISCORD_BOT_TOKEN", "DISCORD_OWNER_ID", "DISCORD_GUILD_ID",
                   "DISCORD_ENABLE_CHAT_INTENT", "DISCORD_ENABLE_MEMBERS_INTENT",
                   "DISCORD_ADS_AUTO", "STRIPE_SECRET_KEY"):
        assert needed in names, needed
    for spec in CRED_CATALOG:      # every entry teaches: what, where, format
        assert spec.what and spec.where and spec.hint, spec.name


def test_switch_values_are_validated():
    from sovereign_agent.credentials import validate_value
    assert validate_value("DISCORD_ENABLE_CHAT_INTENT", "yes")
    assert not validate_value("DISCORD_ENABLE_CHAT_INTENT", "1")
    assert not validate_value("DISCORD_ADS_AUTO", "0")
    # the ads webhook validates like every webhook
    assert validate_value("DISCORD_ADS_WEBHOOK_URL", "http://not-discord")
    assert not validate_value("DISCORD_ADS_WEBHOOK_URL",
                              "https://discord.com/api/webhooks/1/x")


def test_catalog_includes_cloud_mode_fast_lane_keys():
    """cloud-mode-d: Groq/Cerebras are the fast-lane keys for /cloud on —
    teachable from the vault like every other credential."""
    from sovereign_agent.credentials import CRED_CATALOG
    names = {c.name for c in CRED_CATALOG}
    assert "GROQ_API_KEY" in names
    assert "CEREBRAS_API_KEY" in names


def test_groq_key_format_is_validated():
    from sovereign_agent.credentials import validate_value
    assert validate_value("GROQ_API_KEY", "not-a-real-key")
    assert not validate_value("GROQ_API_KEY", "gsk_abc123")


def test_probe_groq_hits_the_models_endpoint_with_bearer_auth(tmp_path):
    from sovereign_agent.credentials import probe_groq

    class _Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    seen = {}
    def opener(url, headers, timeout):
        seen["url"] = url
        seen["headers"] = headers
        return _Resp()

    ok, detail = probe_groq("gsk_secretvalue", opener=opener)
    assert ok and "200" in detail
    assert seen["url"] == "https://api.groq.com/openai/v1/models"
    assert seen["headers"]["Authorization"] == "Bearer gsk_secretvalue"


def test_probe_groq_reports_rejected_key():
    from sovereign_agent.credentials import probe_groq

    class _Err401(Exception):
        code = 401

    def bad(url, headers, timeout):
        raise _Err401()

    ok, detail = probe_groq("bad-key", opener=bad)
    assert not ok and "401" in detail


def test_probe_cerebras_hits_the_models_endpoint():
    from sovereign_agent.credentials import probe_cerebras

    class _Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    seen = {}
    def opener(url, headers, timeout):
        seen["url"] = url
        return _Resp()

    ok, detail = probe_cerebras("some-key", opener=opener)
    assert ok


# ── reddit oauth (shared token exchange, reused by fetchers.py) ─────────────
def test_reddit_client_credentials_token_success():
    from sovereign_agent.credentials import reddit_client_credentials_token

    class _Resp:
        status = 200
        def read(self):
            return b'{"access_token": "tok123", "expires_in": 3600}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    seen = {}
    def opener(url, headers, data, timeout):
        seen["url"] = url
        seen["headers"] = headers
        seen["data"] = data
        return _Resp()

    body, detail = reddit_client_credentials_token("cid", "secret", opener=opener)
    assert body == {"access_token": "tok123", "expires_in": 3600}
    assert "token issued" in detail
    assert seen["url"] == "https://www.reddit.com/api/v1/access_token"
    assert seen["headers"]["Authorization"].startswith("Basic ")
    assert seen["data"] == b"grant_type=client_credentials"


def test_reddit_client_credentials_token_missing_secret():
    from sovereign_agent.credentials import reddit_client_credentials_token
    body, detail = reddit_client_credentials_token("cid", "")
    assert body is None and "SECRET missing" in detail


def test_reddit_client_credentials_token_missing_id():
    from sovereign_agent.credentials import reddit_client_credentials_token
    body, detail = reddit_client_credentials_token("", "secret")
    assert body is None and "not set" in detail


def test_reddit_client_credentials_token_rejected():
    from sovereign_agent.credentials import reddit_client_credentials_token

    class _Err401(Exception):
        code = 401

    def bad(url, headers, data, timeout):
        raise _Err401()

    body, detail = reddit_client_credentials_token("cid", "secret", opener=bad)
    assert body is None and "401" in detail


def test_reddit_client_credentials_token_no_access_token_in_body():
    from sovereign_agent.credentials import reddit_client_credentials_token

    class _Resp:
        status = 200
        def read(self):
            return b'{"error": "unsupported_grant_type"}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    body, detail = reddit_client_credentials_token(
        "cid", "secret", opener=lambda *a: _Resp())
    assert body is None and "no access_token" in detail


def test_probe_reddit_delegates_to_the_shared_token_exchange(monkeypatch):
    from sovereign_agent import credentials as creds
    monkeypatch.setattr(creds, "read_env", lambda *a, **k: {"REDDIT_CLIENT_SECRET": "sec"})

    class _Resp:
        status = 200
        def read(self):
            return b'{"access_token": "tok", "expires_in": 3600}'
        def __enter__(self): return self
        def __exit__(self, *a): return False

    ok, detail = creds.probe_reddit("cid", opener=lambda *a: _Resp())
    assert ok and "token issued" in detail


def test_probe_reddit_not_set():
    from sovereign_agent.credentials import probe_reddit
    ok, detail = probe_reddit("")
    assert not ok and detail == "not set"


def test_check_all_includes_groq_and_cerebras(tmp_path):
    from sovereign_agent.credentials import check_all, set_secret
    vault = tmp_path / "v.env"
    set_secret("GROQ_API_KEY", "gsk_realkey", vault)

    results = check_all(vault)
    by = {r["name"]: r for r in results}
    assert "GROQ_API_KEY" in by
    assert "CEREBRAS_API_KEY" in by
    assert by["CEREBRAS_API_KEY"]["checked"] is False  # unset → skipped
    assert "gsk_realkey" not in json.dumps(results)


# ── last-set-timestamp-d ─────────────────────────────────────────────────────
def test_last_set_at_is_none_before_ever_setting(tmp_path):
    p = _vault(tmp_path)
    assert last_set_at("GROQ_API_KEY", p) is None


def test_set_secret_records_a_last_set_timestamp(tmp_path):
    p = _vault(tmp_path)
    set_secret("GROQ_API_KEY", "gsk_abc123", p)
    ts = last_set_at("GROQ_API_KEY", p)
    assert ts is not None
    assert ts.endswith("Z")  # ISO-8601 UTC


def test_re_setting_a_key_updates_its_timestamp(tmp_path):
    import time
    p = _vault(tmp_path)
    set_secret("GROQ_API_KEY", "gsk_old", p)
    first = last_set_at("GROQ_API_KEY", p)
    time.sleep(1.1)
    set_secret("GROQ_API_KEY", "gsk_new", p)
    second = last_set_at("GROQ_API_KEY", p)
    assert second != first


def test_removing_a_key_clears_its_timestamp(tmp_path):
    p = _vault(tmp_path)
    set_secret("GROQ_API_KEY", "gsk_abc123", p)
    assert last_set_at("GROQ_API_KEY", p) is not None
    remove_secret("GROQ_API_KEY", p)
    assert last_set_at("GROQ_API_KEY", p) is None


def test_meta_file_never_contains_the_secret_value(tmp_path):
    p = _vault(tmp_path)
    set_secret("GROQ_API_KEY", "gsk_supersecretvalue", p)
    meta_path = p.with_suffix(p.suffix + ".meta.json")
    assert meta_path.is_file()
    assert "gsk_supersecretvalue" not in meta_path.read_text()


def test_meta_file_is_0600(tmp_path):
    p = _vault(tmp_path)
    set_secret("GROQ_API_KEY", "gsk_abc123", p)
    meta_path = p.with_suffix(p.suffix + ".meta.json")
    mode = stat.S_IMODE(meta_path.stat().st_mode)
    assert mode == 0o600


def test_vault_status_carries_last_set_fields(tmp_path):
    p = _vault(tmp_path)
    set_secret("GROQ_API_KEY", "gsk_abc123", p)
    rows = vault_status(p)
    row = next(r for r in rows if r["name"] == "GROQ_API_KEY")
    assert row["last_set"] is not None
    assert row["last_set_relative"] == "just now"
    unset_row = next(r for r in rows if r["name"] == "CEREBRAS_API_KEY")
    assert unset_row["last_set"] is None
    assert unset_row["last_set_relative"] == "never"


def test_relative_time_buckets():
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)

    def iso(delta):
        return (now - delta).strftime("%Y-%m-%dT%H:%M:%SZ")

    assert relative_time(None) == "never"
    assert relative_time("garbage") == "unknown"
    assert relative_time(iso(timedelta(seconds=10)), now=now) == "just now"
    assert relative_time(iso(timedelta(minutes=5)), now=now) == "5m ago"
    assert relative_time(iso(timedelta(hours=3)), now=now) == "3h ago"
    assert relative_time(iso(timedelta(days=2)), now=now) == "2d ago"
    assert relative_time(iso(timedelta(days=40)), now=now) == (now - timedelta(days=40)).strftime("%Y-%m-%d")
