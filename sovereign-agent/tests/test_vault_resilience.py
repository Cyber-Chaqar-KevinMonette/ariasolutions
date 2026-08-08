"""Tests for Vault resilience at failure paths (M77).

Each test is self-contained. Uses tmp_path for vault dir and key path.
Cryptography library is assumed available (installed for test suite).

Coverage targets: vault.py lines 122-126 (key permissions), 172 (manifest
corruption), 214-219 (crypto-unavailable warning), 349-355 (tamper
detection), 367-377 (Merkle chain verify), 321-325 (restore without
confirm), 271 (blob dir permissions).
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import secrets
import tarfile
from pathlib import Path
from unittest import mock

import pytest
from ulid import ULID

from sovereign_agent.aegis.vault import (
    GENESIS_HASH,
    KILL_SWITCH_ENV,
    Vault,
    VaultKeyError,
    VaultRestoreRefused,
    VaultSnapshot,
    _VaultManifest,
    load_or_create_vault_key,
    _CRYPTO_AVAILABLE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_vault(tmp_path: Path) -> tuple[Vault, Path, Path]:
    """Return (vault, vault_dir, key_path)."""
    vault_dir = tmp_path / "vault"
    key_path = tmp_path / "keys" / "vault.key"
    v = Vault(vault_dir, key_path)
    v.bootstrap()
    return v, vault_dir, key_path


def _tiny_source(tmp_path: Path) -> Path:
    """Create a tiny source dir with one file."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.txt").write_text("hello aria", encoding="utf-8")
    return src


def _take_snapshot(vault: Vault, source: Path, label: str = "test") -> VaultSnapshot:
    return vault.snapshot(
        snapshot_id=str(ULID()),
        source=source,
        label=label,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_crypto_fallback_warning_logged(tmp_path, caplog):
    """When _CRYPTO_AVAILABLE is False, bootstrap logs a warning (not silent)."""
    vault_dir = tmp_path / "vault"
    key_path = tmp_path / "vault.key"
    v = Vault(vault_dir, key_path)

    with mock.patch("sovereign_agent.aegis.vault._CRYPTO_AVAILABLE", False):
        with caplog.at_level(logging.WARNING, logger="sovereign_agent.aegis.vault"):
            v.bootstrap()

    assert any("OBFUSCATION" in r.message.upper() or "obfuscation" in r.message
               for r in caplog.records), (
        "Expected an obfuscation-mode warning when crypto unavailable"
    )


def test_hash_mismatch_on_restore_raises(tmp_path):
    """Corrupt the blob after snapshot → restore raises ValueError hash mismatch."""
    vault, vault_dir, key_path = _make_vault(tmp_path)
    source = _tiny_source(tmp_path)
    snap = _take_snapshot(vault, source)

    # Corrupt the blob
    blob_path = Path(snap.blob_path)
    data = blob_path.read_bytes()
    blob_path.write_bytes(data[:-10] + b"\x00" * 10)  # corrupt last 10 bytes

    restore_target = tmp_path / "restore"
    with pytest.raises((ValueError, Exception)):
        vault.restore(snapshot_id=snap.snapshot_id, target=restore_target, confirm=True)


def test_merkle_chain_tamper_detection(tmp_path):
    """Corrupt prior_hash in manifest → verify_chain() returns the broken snapshot_id."""
    vault, vault_dir, key_path = _make_vault(tmp_path)
    source = _tiny_source(tmp_path)

    snap1 = _take_snapshot(vault, source, label="snap1")
    snap2 = _take_snapshot(vault, source, label="snap2")

    # Corrupt the manifest: replace snap2's prior_hash with garbage
    manifest_path = vault_dir / "manifest.jsonl"
    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 2

    snap2_data = json.loads(lines[1])
    snap2_data["prior_hash"] = "deadbeef" * 8
    lines[1] = json.dumps(snap2_data, sort_keys=True)
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    broken_id = vault.verify_chain()
    assert broken_id == snap2.snapshot_id


def test_vault_key_wrong_permissions_raises(tmp_path):
    """Existing key at mode 0o644 → load_or_create_vault_key raises VaultKeyError."""
    key_path = tmp_path / "vault.key"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(secrets.token_bytes(32))
    os.chmod(key_path, 0o644)

    with pytest.raises(VaultKeyError, match="0o644"):
        load_or_create_vault_key(key_path)


def test_manifest_jsonl_corruption_recovery(tmp_path):
    """A corrupt line in the middle of manifest.jsonl → other entries still returned."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir(mode=0o700)
    manifest_path = vault_dir / "manifest.jsonl"

    snap1_id = str(ULID())
    snap3_id = str(ULID())

    # Build 3 lines; line 2 is corrupt JSON
    line1 = json.dumps({
        "snapshot_id": snap1_id, "taken_at": "2026-01-01T00:00:00.000000Z",
        "source_root": "/tmp", "blob_path": "/tmp/a.vault",
        "blob_size": 100, "plaintext_sha256": "a" * 64,
        "cipher_mode": "aes-256-gcm", "label": "first",
        "prior_hash": GENESIS_HASH, "entry_hash": "b" * 64,
    }, sort_keys=True)
    line2_corrupt = "{not valid json at all!!!"
    line3 = json.dumps({
        "snapshot_id": snap3_id, "taken_at": "2026-01-03T00:00:00.000000Z",
        "source_root": "/tmp", "blob_path": "/tmp/c.vault",
        "blob_size": 200, "plaintext_sha256": "c" * 64,
        "cipher_mode": "aes-256-gcm", "label": "third",
        "prior_hash": "d" * 64, "entry_hash": "e" * 64,
    }, sort_keys=True)

    manifest_path.write_text(
        "\n".join([line1, line2_corrupt, line3]) + "\n", encoding="utf-8"
    )

    manifest = _VaultManifest(manifest_path)
    snaps = manifest.all()
    # Corrupt line skipped; 2 valid lines returned
    assert len(snaps) == 2
    ids = {s.snapshot_id for s in snaps}
    assert snap1_id in ids
    assert snap3_id in ids


def test_blob_directory_permissions(tmp_path):
    """After bootstrap, vault_dir has mode 0o700 and blobs_dir has mode 0o700."""
    vault_dir = tmp_path / "vault"
    key_path = tmp_path / "vault.key"
    v = Vault(vault_dir, key_path)
    v.bootstrap()

    import stat as stat_mod
    vault_mode = stat_mod.S_IMODE(vault_dir.stat().st_mode)
    blobs_mode = stat_mod.S_IMODE((vault_dir / "blobs").stat().st_mode)
    assert vault_mode == 0o700, f"vault_dir mode is {oct(vault_mode)}, expected 0o700"
    assert blobs_mode == 0o700, f"blobs_dir mode is {oct(blobs_mode)}, expected 0o700"


def test_restore_without_confirm_raises(tmp_path):
    """restore() without confirm=True → VaultRestoreRefused."""
    vault, vault_dir, key_path = _make_vault(tmp_path)
    source = _tiny_source(tmp_path)
    snap = _take_snapshot(vault, source)

    restore_target = tmp_path / "restore"
    with pytest.raises(VaultRestoreRefused, match="confirm"):
        vault.restore(snapshot_id=snap.snapshot_id, target=restore_target)


def test_obfuscation_mode_tamper_detection(tmp_path):
    """In obfuscation mode, corrupt the blob → restore raises ValueError tag mismatch."""
    vault_dir = tmp_path / "vault"
    key_path = tmp_path / "vault.key"
    v = Vault(vault_dir, key_path)

    with mock.patch("sovereign_agent.aegis.vault._CRYPTO_AVAILABLE", False):
        v.bootstrap()
        source = _tiny_source(tmp_path)
        snap = v.snapshot(
            snapshot_id=str(ULID()),
            source=source,
            label="obf-test",
        )

    assert snap.cipher_mode == "obfuscated-warning"

    # Corrupt the blob (flip the last byte of the obfuscated payload)
    blob_path = Path(snap.blob_path)
    data = bytearray(blob_path.read_bytes())
    data[-1] ^= 0xFF
    blob_path.write_bytes(bytes(data))

    restore_target = tmp_path / "restore"
    with mock.patch("sovereign_agent.aegis.vault._CRYPTO_AVAILABLE", False):
        with pytest.raises(ValueError, match="tampered"):
            v.restore(snapshot_id=snap.snapshot_id, target=restore_target, confirm=True)
