"""Tests for aegis/encrypted_at_rest.py — AES-256-GCM at-rest encryption.

These tests use fast Argon2id parameters (time_cost=1, memory_kb=64, parallelism=1)
to keep the test suite fast while still exercising the real crypto path.

The production defaults (time_cost=2, memory_kb=19456) are intentionally slow to
resist offline dictionary attacks — we don't want that in unit tests.
"""
from __future__ import annotations

import pytest

from sovereign_agent.aegis.encrypted_at_rest import (
    HEADER_SIZE,
    MAGIC,
    Argon2Params,
    AtRestError,
    AtRestSession,
    MalformedCiphertext,
    WrongPassphrase,
    decrypt_bytes,
    encrypt_bytes,
    _CRYPTO_AVAILABLE,
    KILL_SWITCH_ENV,
)

# Fast params for tests — do NOT use in production
_FAST = Argon2Params(time_cost=1, memory_kb=64, parallelism=1)
_PASSPHRASE = b"test-passphrase-for-aria-unit-tests"


@pytest.mark.skipif(not _CRYPTO_AVAILABLE, reason="cryptography+argon2-cffi not installed")
class TestEncryptDecryptRoundtrip:
    def test_encrypt_produces_bytes(self):
        blob = encrypt_bytes(b"hello world", _PASSPHRASE, params=_FAST)
        assert isinstance(blob, bytes)
        assert len(blob) > HEADER_SIZE

    def test_decrypt_roundtrip(self):
        plaintext = b"sovereign agent at rest encryption test"
        blob = encrypt_bytes(plaintext, _PASSPHRASE, params=_FAST)
        recovered = decrypt_bytes(blob, _PASSPHRASE, params=_FAST)
        assert recovered == plaintext

    def test_magic_bytes_present(self):
        blob = encrypt_bytes(b"magic test", _PASSPHRASE, params=_FAST)
        assert blob[:len(MAGIC)] == MAGIC

    def test_different_passphrases_produce_different_ciphertext(self):
        pt = b"same plaintext"
        blob1 = encrypt_bytes(pt, b"passphrase-one", params=_FAST)
        blob2 = encrypt_bytes(pt, b"passphrase-two", params=_FAST)
        # Different passphrases → different derived keys → different ciphertext
        assert blob1 != blob2

    def test_same_plaintext_produces_different_blobs(self):
        """Each call uses a fresh random salt + nonce — blobs are never identical."""
        pt = b"determinism test"
        blob1 = encrypt_bytes(pt, _PASSPHRASE, params=_FAST)
        blob2 = encrypt_bytes(pt, _PASSPHRASE, params=_FAST)
        assert blob1 != blob2

    def test_wrong_passphrase_raises_wrong_passphrase(self):
        blob = encrypt_bytes(b"secret data", _PASSPHRASE, params=_FAST)
        with pytest.raises(WrongPassphrase):
            decrypt_bytes(blob, b"wrong-passphrase", params=_FAST)

    def test_tampered_ciphertext_raises_wrong_passphrase(self):
        blob = encrypt_bytes(b"tamper test", _PASSPHRASE, params=_FAST)
        # Flip a byte in the ciphertext region (after header)
        tampered = bytearray(blob)
        tampered[-1] ^= 0xFF
        with pytest.raises(WrongPassphrase):
            decrypt_bytes(bytes(tampered), _PASSPHRASE, params=_FAST)

    def test_empty_plaintext_roundtrip(self):
        blob = encrypt_bytes(b"", _PASSPHRASE, params=_FAST)
        recovered = decrypt_bytes(blob, _PASSPHRASE, params=_FAST)
        assert recovered == b""

    def test_large_plaintext_roundtrip(self):
        large = b"A" * 100_000
        blob = encrypt_bytes(large, _PASSPHRASE, params=_FAST)
        recovered = decrypt_bytes(blob, _PASSPHRASE, params=_FAST)
        assert recovered == large

    def test_custom_aad_roundtrip(self):
        pt = b"associated data test"
        aad = b"custom-aad-value"
        blob = encrypt_bytes(pt, _PASSPHRASE, aad=aad, params=_FAST)
        recovered = decrypt_bytes(blob, _PASSPHRASE, aad=aad, params=_FAST)
        assert recovered == pt

    def test_wrong_aad_raises_wrong_passphrase(self):
        pt = b"aad mismatch"
        blob = encrypt_bytes(pt, _PASSPHRASE, aad=b"original-aad", params=_FAST)
        with pytest.raises(WrongPassphrase):
            decrypt_bytes(blob, _PASSPHRASE, aad=b"different-aad", params=_FAST)


@pytest.mark.skipif(not _CRYPTO_AVAILABLE, reason="cryptography+argon2-cffi not installed")
class TestDeriveKey:
    def test_derive_key_returns_32_bytes(self):
        from sovereign_agent.aegis.encrypted_at_rest import derive_key, SALT_SIZE
        salt = b"\x00" * SALT_SIZE
        key = derive_key(_PASSPHRASE, salt, params=_FAST)
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_derive_key_wrong_salt_size_raises_value_error(self):
        from sovereign_agent.aegis.encrypted_at_rest import derive_key
        with pytest.raises(ValueError, match="salt must be"):
            derive_key(_PASSPHRASE, b"tooshort", params=_FAST)

    def test_derive_key_non_bytes_passphrase_raises_type_error(self):
        from sovereign_agent.aegis.encrypted_at_rest import derive_key, SALT_SIZE
        salt = b"\x00" * SALT_SIZE
        with pytest.raises(TypeError, match="passphrase must be bytes"):
            derive_key("string-not-bytes", salt, params=_FAST)  # type: ignore[arg-type]


@pytest.mark.skipif(not _CRYPTO_AVAILABLE, reason="cryptography+argon2-cffi not installed")
class TestMalformedCiphertext:
    def test_blob_too_short_raises_malformed(self):
        with pytest.raises(MalformedCiphertext, match="shorter than header"):
            decrypt_bytes(b"too short", _PASSPHRASE, params=_FAST)

    def test_wrong_magic_raises_malformed(self):
        fake = b"BADMAGIC\x00" + b"\x00" * 50
        with pytest.raises(MalformedCiphertext, match="magic"):
            decrypt_bytes(fake, _PASSPHRASE, params=_FAST)

    def test_wrong_version_raises_malformed(self):
        blob = encrypt_bytes(b"version test", _PASSPHRASE, params=_FAST)
        # Patch the version byte (index = len(MAGIC) = 9)
        tampered = bytearray(blob)
        tampered[len(MAGIC)] = 99  # unsupported version
        with pytest.raises(MalformedCiphertext, match="version"):
            decrypt_bytes(bytes(tampered), _PASSPHRASE, params=_FAST)


class TestArgon2Params:
    def test_defaults(self):
        p = Argon2Params()
        assert p.time_cost == 2
        assert p.parallelism == 1
        assert p.memory_kb > 0

    def test_from_env_reads_env_vars(self, monkeypatch):
        monkeypatch.setenv("SOV_AT_REST_TIME_COST", "3")
        monkeypatch.setenv("SOV_AT_REST_MEM_KB", "4096")
        monkeypatch.setenv("SOV_AT_REST_PARALLEL", "2")
        p = Argon2Params.from_env()
        assert p.time_cost == 3
        assert p.memory_kb == 4096
        assert p.parallelism == 2

    def test_from_env_uses_defaults_when_vars_absent(self, monkeypatch):
        monkeypatch.delenv("SOV_AT_REST_TIME_COST", raising=False)
        monkeypatch.delenv("SOV_AT_REST_MEM_KB", raising=False)
        monkeypatch.delenv("SOV_AT_REST_PARALLEL", raising=False)
        p = Argon2Params.from_env()
        assert p.time_cost == 2  # DEFAULT_TIME_COST


@pytest.mark.skipif(not _CRYPTO_AVAILABLE, reason="cryptography+argon2-cffi not installed")
class TestFileEncryption:
    def test_encrypt_file_then_decrypt_file(self, tmp_path):
        from sovereign_agent.aegis.encrypted_at_rest import encrypt_file, decrypt_file
        src = tmp_path / "plain.txt"
        original = b"file encryption test content"
        src.write_bytes(original)
        enc = tmp_path / "plain.txt.enc"
        encrypt_file(src, enc, _PASSPHRASE, params=_FAST)
        assert enc.exists()
        recovered = decrypt_file(enc, _PASSPHRASE, params=_FAST)
        assert recovered == original

    def test_encrypted_file_permissions_are_0600(self, tmp_path):
        import stat
        from sovereign_agent.aegis.encrypted_at_rest import encrypt_file
        src = tmp_path / "sensitive.txt"
        src.write_bytes(b"private data")
        enc = tmp_path / "sensitive.txt.enc"
        encrypt_file(src, enc, _PASSPHRASE, params=_FAST)
        mode = stat.S_IMODE(enc.stat().st_mode)
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_encrypt_file_is_atomic(self, tmp_path):
        """No .tmp file should remain after encrypt_file completes."""
        from sovereign_agent.aegis.encrypted_at_rest import encrypt_file
        src = tmp_path / "atom.txt"
        src.write_bytes(b"atomic write test")
        enc = tmp_path / "atom.enc"
        encrypt_file(src, enc, _PASSPHRASE, params=_FAST)
        # The tmp file is target.with_suffix(target.suffix + ".tmp") = "atom.enc.tmp"
        tmp_artifact = tmp_path / (enc.name + ".tmp")
        assert not tmp_artifact.exists()

    def test_is_encrypted_file_true_for_encrypted(self, tmp_path):
        from sovereign_agent.aegis.encrypted_at_rest import encrypt_file, is_encrypted_file
        src = tmp_path / "check.txt"
        src.write_bytes(b"probe test")
        enc = tmp_path / "check.enc"
        encrypt_file(src, enc, _PASSPHRASE, params=_FAST)
        assert is_encrypted_file(enc) is True

    def test_is_encrypted_file_false_for_plaintext(self, tmp_path):
        from sovereign_agent.aegis.encrypted_at_rest import is_encrypted_file
        plain = tmp_path / "plain.txt"
        plain.write_bytes(b"not encrypted at all")
        assert is_encrypted_file(plain) is False

    def test_is_encrypted_file_false_for_missing(self, tmp_path):
        from sovereign_agent.aegis.encrypted_at_rest import is_encrypted_file
        assert is_encrypted_file(tmp_path / "nonexistent.enc") is False

    def test_is_encrypted_file_false_on_oserror(self, tmp_path, monkeypatch):
        """OSError during path.open() → returns False, does not raise."""
        from sovereign_agent.aegis.encrypted_at_rest import is_encrypted_file
        from pathlib import Path
        import unittest.mock as mock
        plain = tmp_path / "unreadable.enc"
        plain.write_bytes(b"data")
        with mock.patch.object(Path, "open", side_effect=OSError("permission denied")):
            result = is_encrypted_file(plain)
        assert result is False


@pytest.mark.skipif(not _CRYPTO_AVAILABLE, reason="cryptography+argon2-cffi not installed")
class TestAtRestSession:
    def test_unlock_and_roundtrip(self):
        with AtRestSession.unlock(_PASSPHRASE, params=_FAST) as session:
            blob = session.encrypt_bytes(b"session test")
            recovered = session.decrypt_bytes(blob)
        assert recovered == b"session test"

    def test_session_is_closed_after_context_exit(self):
        session = AtRestSession.unlock(_PASSPHRASE, params=_FAST)
        session.close()
        with pytest.raises(AtRestError, match="closed"):
            session.encrypt_bytes(b"should fail")

    def test_session_close_is_idempotent(self):
        session = AtRestSession.unlock(_PASSPHRASE, params=_FAST)
        session.close()
        session.close()  # second close must not raise

    def test_kill_switch_blocks_unlock(self, monkeypatch):
        monkeypatch.setenv(KILL_SWITCH_ENV, "1")
        with pytest.raises(AtRestError, match="SOV_NO_AT_REST"):
            AtRestSession.unlock(_PASSPHRASE, params=_FAST)

    def test_session_encrypt_file(self, tmp_path):
        from sovereign_agent.aegis.encrypted_at_rest import is_encrypted_file
        src = tmp_path / "session_src.txt"
        src.write_bytes(b"session-level file encryption")
        enc = tmp_path / "session_src.enc"
        with AtRestSession.unlock(_PASSPHRASE, params=_FAST) as session:
            session.encrypt_file(src, enc)
        assert is_encrypted_file(enc)

    def test_session_decrypt_file(self, tmp_path):
        from sovereign_agent.aegis.encrypted_at_rest import encrypt_file
        src = tmp_path / "s.txt"
        src.write_bytes(b"roundtrip via session")
        enc = tmp_path / "s.enc"
        encrypt_file(src, enc, _PASSPHRASE, params=_FAST)
        with AtRestSession.unlock(_PASSPHRASE, params=_FAST) as session:
            result = session.decrypt_file(enc)
        assert result == b"roundtrip via session"
