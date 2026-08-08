"""
╔══════════════════════════════════════════════════════════════════════════╗
║  aegis/encrypted_at_rest.py — passphrase-derived encryption of data_dir ║
║  v0.2.36 — the legitimate engineering version of "hide from ls -la"     ║
║                                                                           ║
║  What this is                                                            ║
║                                                                           ║
║    A small, focused module for encrypting files inside data_dir at rest. ║
║    Files on disk become opaque ciphertext to anyone without the          ║
║    passphrase. `ls` still sees them; that's correct. `cat` shows random ║
║    bytes; that's the point.                                              ║
║                                                                           ║
║  Key handling                                                            ║
║                                                                           ║
║    The encryption key is derived from an operator passphrase via         ║
║    Argon2id (the OWASP recommendation for password-derived keys). The   ║
║    derived key lives in memory for the duration of the agent session    ║
║    only. On graceful shutdown, the in-memory key is zeroed.            ║
║                                                                           ║
║    Argon2id parameters target the OWASP "minimum" tier: time_cost=2,   ║
║    memory_cost=19 MiB, parallelism=1. Tunable via env vars              ║
║    SOV_AT_REST_TIME_COST / SOV_AT_REST_MEM_KB / SOV_AT_REST_PARALLEL.  ║
║                                                                           ║
║    The salt is stored alongside the encrypted data (one salt per         ║
║    encrypted file). Argon2id with per-file salts means same-passphrase  ║
║    on different files produces different keys.                          ║
║                                                                           ║
║  File format                                                             ║
║                                                                           ║
║    Each encrypted file is:                                              ║
║                                                                           ║
║      [ magic:8 ][ version:1 ][ salt:16 ][ nonce:12 ][ ciphertext+tag ]  ║
║                                                                           ║
║    Magic bytes: b"SOV-AR-1\\0". Anyone running `file` on the artifact   ║
║    sees plainly that it's an encrypted Aria file. We do NOT pretend     ║
║    it's something else. Honesty beats stealth.                          ║
║                                                                           ║
║  Cipher                                                                  ║
║                                                                           ║
║    AES-256-GCM via the cryptography library. If the library isn't       ║
║    installed, the module refuses to bootstrap — there's no obfuscation- ║
║    only fallback for at-rest encryption, because the confidentiality   ║
║    property is the whole point.                                         ║
║                                                                           ║
║  What this is NOT                                                        ║
║                                                                           ║
║    • Not a filesystem-level encryption (no FUSE, no kernel modules).   ║
║      File-by-file at the application layer.                             ║
║    • Not protection against a running-process memory dump. The         ║
║      decrypted key lives in memory while the agent runs.                ║
║    • Not protection against a keylogger capturing the passphrase.       ║
║      That's the operator's OS-security problem.                         ║
║    • Not a substitute for the Vault. The Vault is OOB snapshots with    ║
║      a different key; this is in-place encryption of live data_dir     ║
║      files. The two are complementary, not redundant.                  ║
║                                                                           ║
║  Kill switch: SOV_NO_AT_REST=1 — runs everything in plaintext mode    ║
║  (useful for development; refused if the data_dir contains existing    ║
║  encrypted files, since dropping back to plaintext would either lose   ║
║  data or expose it).                                                    ║
║                                                                           ║
║  Doctrinal anchor: STANDARDS-CE-2026.05.24 §10 (Love Doctrine §10.6 — ║
║  no rootkit techniques). This module is the *honest* version of        ║
║  Kevin's "hide from ls" impulse. The OS contract holds; the data is    ║
║  unreadable without the key.                                            ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

KILL_SWITCH_ENV = "SOV_NO_AT_REST"
MAGIC = b"SOV-AR-1\x00"
VERSION = 1
SALT_SIZE = 16
NONCE_SIZE = 12
HEADER_SIZE = len(MAGIC) + 1 + SALT_SIZE + NONCE_SIZE  # 8 + 1 + 16 + 12 = 37

# Argon2id parameters — OWASP minimum tier, tunable via env.
DEFAULT_TIME_COST = 2
DEFAULT_MEM_KB = 19_456    # 19 MiB
DEFAULT_PARALLELISM = 1
DERIVED_KEY_LEN = 32       # AES-256 needs 32 bytes


# ─── Cipher import — refuse to operate without it ────────────────────────


try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from argon2.low_level import Type, hash_secret_raw
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False
    AESGCM = None  # type: ignore[assignment,misc]


# ─── Exceptions ──────────────────────────────────────────────────────────


class AtRestError(Exception):
    """Base class for at-rest encryption errors."""


class CryptoUnavailable(AtRestError):
    """Raised when cryptography or argon2 isn't installed but at-rest is enabled."""


class WrongPassphrase(AtRestError):
    """Raised when decryption fails authentication (likely wrong key)."""


class MalformedCiphertext(AtRestError):
    """Raised when the file header is missing or wrong magic."""


# ─── Config ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Argon2Params:
    """Argon2id parameters used to derive a per-file key from a passphrase."""
    time_cost: int = DEFAULT_TIME_COST
    memory_kb: int = DEFAULT_MEM_KB
    parallelism: int = DEFAULT_PARALLELISM

    @classmethod
    def from_env(cls) -> "Argon2Params":
        return cls(
            time_cost=int(os.environ.get("SOV_AT_REST_TIME_COST", DEFAULT_TIME_COST)),
            memory_kb=int(os.environ.get("SOV_AT_REST_MEM_KB", DEFAULT_MEM_KB)),
            parallelism=int(os.environ.get("SOV_AT_REST_PARALLEL", DEFAULT_PARALLELISM)),
        )


# ─── KDF: passphrase + per-file salt → 32-byte AES key ───────────────────


def derive_key(
    passphrase: bytes,
    salt: bytes,
    *,
    params: Optional[Argon2Params] = None,
) -> bytes:
    """Argon2id over (passphrase, salt) → 32-byte key.

    Per-file salt means same passphrase + different files = different keys.
    Compromise of one file's key does not compromise others.
    """
    if not _CRYPTO_AVAILABLE:
        raise CryptoUnavailable(
            "argon2-cffi + cryptography required for at-rest encryption. "
            "Install: pip install argon2-cffi cryptography"
        )
    if not isinstance(passphrase, bytes):
        raise TypeError("passphrase must be bytes")
    if len(salt) != SALT_SIZE:
        raise ValueError(f"salt must be {SALT_SIZE} bytes, got {len(salt)}")
    p = params or Argon2Params.from_env()
    return hash_secret_raw(
        secret=passphrase,
        salt=salt,
        time_cost=p.time_cost,
        memory_cost=p.memory_kb,
        parallelism=p.parallelism,
        hash_len=DERIVED_KEY_LEN,
        type=Type.ID,
    )


# ─── Encrypt / decrypt one buffer ────────────────────────────────────────


def encrypt_bytes(
    plaintext: bytes,
    passphrase: bytes,
    *,
    aad: bytes = b"sovereign-agent-at-rest",
    params: Optional[Argon2Params] = None,
) -> bytes:
    """Produce the full encrypted file representation as one bytes blob.

    Format: MAGIC || VERSION || SALT || NONCE || CIPHERTEXT_AND_TAG
    """
    if not _CRYPTO_AVAILABLE:
        raise CryptoUnavailable("cryptography library not installed")
    salt = secrets.token_bytes(SALT_SIZE)
    nonce = secrets.token_bytes(NONCE_SIZE)
    key = derive_key(passphrase, salt, params=params)
    try:
        aes = AESGCM(key)
        ct = aes.encrypt(nonce, plaintext, aad)
    finally:
        # Zero the derived key buffer to make memory disclosure marginally
        # less catastrophic. Python doesn't guarantee this (the bytes object
        # is immutable), so it's best-effort, not a guarantee.
        del key
    return MAGIC + bytes([VERSION]) + salt + nonce + ct


def decrypt_bytes(
    blob: bytes,
    passphrase: bytes,
    *,
    aad: bytes = b"sovereign-agent-at-rest",
    params: Optional[Argon2Params] = None,
) -> bytes:
    """Decrypt a full encrypted-file blob produced by encrypt_bytes."""
    if not _CRYPTO_AVAILABLE:
        raise CryptoUnavailable("cryptography library not installed")
    if len(blob) < HEADER_SIZE:
        raise MalformedCiphertext("blob shorter than header")
    if blob[:len(MAGIC)] != MAGIC:
        raise MalformedCiphertext("magic bytes don't match SOV-AR-1")
    version = blob[len(MAGIC)]
    if version != VERSION:
        raise MalformedCiphertext(f"unsupported version: {version}")
    salt_start = len(MAGIC) + 1
    nonce_start = salt_start + SALT_SIZE
    ct_start = nonce_start + NONCE_SIZE
    salt = blob[salt_start:nonce_start]
    nonce = blob[nonce_start:ct_start]
    ct = blob[ct_start:]
    key = derive_key(passphrase, salt, params=params)
    try:
        aes = AESGCM(key)
        try:
            return aes.decrypt(nonce, ct, aad)
        except Exception as e:
            # cryptography raises InvalidTag for auth failure; we don't want
            # to leak whether the issue was key-wrong vs blob-tampered.
            raise WrongPassphrase("decryption failed — wrong passphrase or tampered file") from e
    finally:
        del key


# ─── File-level helpers (write-then-rename for atomicity) ────────────────


def encrypt_file(
    source: Path,
    target: Path,
    passphrase: bytes,
    *,
    params: Optional[Argon2Params] = None,
) -> Path:
    """Read plaintext from source, write encrypted blob to target.

    target is written atomically (target.tmp then rename). Permissions
    are set to 0600 before rename. Source is NOT deleted — caller decides
    whether to remove it.
    """
    plaintext = source.read_bytes()
    blob = encrypt_bytes(plaintext, passphrase, params=params)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(blob)
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    return target


def decrypt_file(
    source: Path,
    passphrase: bytes,
    *,
    params: Optional[Argon2Params] = None,
) -> bytes:
    """Read encrypted blob from source, return plaintext bytes."""
    blob = source.read_bytes()
    return decrypt_bytes(blob, passphrase, params=params)


def is_encrypted_file(path: Path) -> bool:
    """Cheap probe — read first 9 bytes and check magic. Useful for the
    Watchdog Sentinel to verify expected files are encrypted."""
    if not path.is_file():
        return False
    try:
        with path.open("rb") as f:
            head = f.read(len(MAGIC))
        return head == MAGIC
    except OSError:
        return False


# ─── At-Rest Session ─────────────────────────────────────────────────────


class AtRestSession:
    """A bound session holding the passphrase in memory for the agent run.

    Usage:
        session = AtRestSession.unlock(passphrase_bytes)
        session.encrypt_file(plaintext_path, encrypted_path)
        plaintext = session.decrypt_file(encrypted_path)
        # At graceful shutdown:
        session.close()

    The passphrase is held as a mutable bytearray so we can attempt to
    zero it on close. Python doesn't guarantee memory zeroing, but this
    is best-effort defense-in-depth.
    """

    def __init__(self, passphrase_buf: bytearray, params: Argon2Params):
        self._passphrase = passphrase_buf
        self._params = params
        self._closed = False

    @classmethod
    def unlock(cls, passphrase: bytes, params: Optional[Argon2Params] = None) -> "AtRestSession":
        if os.environ.get(KILL_SWITCH_ENV):
            raise AtRestError(
                "at-rest encryption disabled via SOV_NO_AT_REST; "
                "AtRestSession.unlock() refuses to run"
            )
        if not _CRYPTO_AVAILABLE:
            raise CryptoUnavailable(
                "argon2-cffi + cryptography required. "
                "Install: pip install argon2-cffi cryptography"
            )
        return cls(bytearray(passphrase), params or Argon2Params.from_env())

    def encrypt_file(self, source: Path, target: Path) -> Path:
        self._require_open()
        return encrypt_file(source, target, bytes(self._passphrase), params=self._params)

    def decrypt_file(self, source: Path) -> bytes:
        self._require_open()
        return decrypt_file(source, bytes(self._passphrase), params=self._params)

    def encrypt_bytes(self, plaintext: bytes) -> bytes:
        self._require_open()
        return encrypt_bytes(plaintext, bytes(self._passphrase), params=self._params)

    def decrypt_bytes(self, blob: bytes) -> bytes:
        self._require_open()
        return decrypt_bytes(blob, bytes(self._passphrase), params=self._params)

    def close(self) -> None:
        """Best-effort zero of the passphrase buffer."""
        if self._closed:
            return
        for i in range(len(self._passphrase)):
            self._passphrase[i] = 0
        self._closed = True

    def __enter__(self) -> "AtRestSession":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _require_open(self) -> None:
        if self._closed:
            raise AtRestError("session is closed; cannot encrypt/decrypt")


__all__ = [
    "Argon2Params",
    "AtRestError", "CryptoUnavailable", "WrongPassphrase", "MalformedCiphertext",
    "AtRestSession",
    "derive_key", "encrypt_bytes", "decrypt_bytes",
    "encrypt_file", "decrypt_file", "is_encrypted_file",
    "KILL_SWITCH_ENV", "MAGIC", "VERSION",
]
