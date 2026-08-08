"""Tests for the owner-controlled encryption vault."""
import pytest

pytest.importorskip("cryptography")

from sovereign_agent.security.vault import (  # noqa: E402
    Vault, VaultError, VaultLocked,
)

PW = "correct horse battery staple"


@pytest.fixture
def vault(tmp_path):
    return Vault(tmp_path / "vault")


def test_init_and_status(vault):
    assert vault.is_initialized is False
    vault.init_owner(PW)
    assert vault.is_initialized is True
    st = vault.status()
    assert st["initialized"] is True and st["crypto_available"] is True


def test_init_rejects_short_passphrase(vault):
    with pytest.raises(VaultError):
        vault.init_owner("short")


def test_init_refuses_to_clobber(vault):
    vault.init_owner(PW)
    with pytest.raises(VaultError):
        vault.init_owner("another good passphrase")


def test_verify(vault):
    vault.init_owner(PW)
    assert vault.verify_owner(PW) is True
    assert vault.verify_owner("wrong passphrase here") is False


def test_verify_uninitialized_is_false(vault):
    assert vault.verify_owner(PW) is False


def test_encrypt_decrypt_roundtrip(vault, tmp_path):
    vault.init_owner(PW)
    f = tmp_path / "secret.txt"
    f.write_text("Aria's private notes 🌱")
    enc = vault.encrypt_file(f, PW, remove_plaintext=True)
    assert enc.name == "secret.txt.enc"
    assert not f.exists()                       # plaintext removed
    assert b"Aria" not in enc.read_bytes()      # ciphertext is opaque
    dec = vault.decrypt_file(enc, PW)
    assert dec.read_text() == "Aria's private notes 🌱"


def test_decrypt_wrong_passphrase_raises(vault, tmp_path):
    vault.init_owner(PW)
    f = tmp_path / "s.txt"; f.write_text("data")
    enc = vault.encrypt_file(f, PW)
    with pytest.raises(VaultLocked):
        vault.decrypt_file(enc, "the wrong passphrase")


def test_encrypt_requires_correct_passphrase(vault, tmp_path):
    vault.init_owner(PW)
    f = tmp_path / "s.txt"; f.write_text("data")
    with pytest.raises(VaultLocked):
        vault.encrypt_file(f, "nope nope nope")


def test_bytes_roundtrip(vault):
    vault.init_owner(PW)
    token = vault.encrypt_bytes(b"\x00\x01rawbytes", PW)
    assert vault.decrypt_bytes(token, PW) == b"\x00\x01rawbytes"


def test_rotation_rekeys_and_reencrypts(vault, tmp_path):
    vault.init_owner(PW)
    f = tmp_path / "s.txt"; f.write_text("payload")
    enc = vault.encrypt_file(f, PW)
    new_pw = "a brand new passphrase!"
    rewritten = vault.rotate(PW, new_pw, files=(enc,))
    assert rewritten == [enc]
    assert vault.verify_owner(PW) is False        # old no longer valid
    assert vault.verify_owner(new_pw) is True
    assert vault.decrypt_file(enc, new_pw).read_text() == "payload"


def test_rotation_wrong_current_passphrase_raises(vault):
    vault.init_owner(PW)
    with pytest.raises(VaultLocked):
        vault.rotate("wrong current", "a fresh new passphrase")
