"""
╔══════════════════════════════════════════════════════════════════════════╗
║  vault.py — owner-controlled encryption at rest  🔐                        ║
║                                                                            ║
║  Encrypts designated files so that, without the owner's passphrase, their  ║
║  contents are ciphertext — unreadable to anyone who copies the files. The  ║
║  owner (the human) holds the passphrase; the key is derived from it and    ║
║  never stored. Rotation lets the owner change the passphrase without       ║
║  losing data.                                                              ║
║                                                                            ║
║  ── Threat model (read this; honesty matters more than reassurance) ──     ║
║  PROTECTS against: someone who obtains the encrypted files but NOT the     ║
║    passphrase. They see authenticated ciphertext (AES via Fernet); they    ║
║    cannot read or silently alter it.                                       ║
║  Does NOT protect against: someone who has the passphrase, or who can      ║
║    read the running process's memory while it's unlocked. This is          ║
║    encryption at rest, not DRM, and not a loyalty mechanism. It cannot     ║
║    make software "obey" anyone — it only controls who can read files.      ║
║  There is deliberately NO backdoor: lose the passphrase and the data is    ║
║    gone. Keep a backup of the passphrase somewhere safe. Use `rotate` to   ║
║    change it. The owner is the human — not this program, and not the       ║
║    model that helped write it (which holds nothing and persists nothing).  ║
║                                                                            ║
║  v0.2.36.0                                                                 ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# scrypt work factors — solid for an interactive passphrase on a laptop.
_KDF = {"n": 2 ** 15, "r": 8, "p": 1, "dklen": 32}
_VERIFIER_MSG = b"sovereign-owner-v1"
_CRED_VERSION = 1


class VaultError(Exception):
    """Base for vault problems."""


class VaultUnavailable(VaultError):
    """The `cryptography` library isn't installed."""


class VaultLocked(VaultError):
    """Wrong or missing passphrase."""


def _have_crypto() -> bool:
    try:
        import cryptography  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _derive(passphrase: str, salt: bytes) -> bytes:
    """Derive a 32-byte key from a passphrase via scrypt."""
    # OpenSSL's default maxmem (32 MiB) is just under what N=2**15 needs
    # (~128*N*r bytes ≈ 33 MiB), so raise the ceiling explicitly.
    return hashlib.scrypt(passphrase.encode("utf-8"), salt=salt,
                          n=_KDF["n"], r=_KDF["r"], p=_KDF["p"],
                          maxmem=128 * 1024 * 1024, dklen=_KDF["dklen"])


def _fernet_key(raw: bytes) -> bytes:
    return base64.urlsafe_b64encode(raw)


def _verifier(key: bytes) -> str:
    return hmac.new(key, _VERIFIER_MSG, hashlib.sha256).hexdigest()


@dataclass
class OwnerCredential:
    version: int
    salt_b64: str
    verifier: str
    created_at: str
    kdf: dict

    def to_json(self) -> str:
        return json.dumps({
            "version": self.version, "salt_b64": self.salt_b64,
            "verifier": self.verifier, "created_at": self.created_at,
            "kdf": self.kdf,
        }, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "OwnerCredential":
        d = json.loads(text)
        return cls(version=d["version"], salt_b64=d["salt_b64"],
                   verifier=d["verifier"], created_at=d["created_at"],
                   kdf=d.get("kdf", _KDF))


class Vault:
    """Owner-controlled encryption. The owner credential lives in `root`."""

    def __init__(self, root: Path):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._cred_path = self._root / "owner.cred"

    # ── status ───────────────────────────────────────────────────────────
    @property
    def is_initialized(self) -> bool:
        return self._cred_path.exists()

    def status(self) -> dict[str, Any]:
        st: dict[str, Any] = {
            "initialized": self.is_initialized,
            "crypto_available": _have_crypto(),
            "credential_path": str(self._cred_path),
        }
        if self.is_initialized:
            cred = self._load_cred()
            st["created_at"] = cred.created_at
            st["kdf"] = cred.kdf
        return st

    # ── owner credential ──────────────────────────────────────────────────
    def _load_cred(self) -> OwnerCredential:
        return OwnerCredential.from_json(self._cred_path.read_text("utf-8"))

    def init_owner(self, passphrase: str) -> None:
        """Create the owner credential. Refuses to clobber an existing one
        (use rotate to change the passphrase)."""
        if not passphrase or len(passphrase) < 8:
            raise VaultError("passphrase must be at least 8 characters")
        if self.is_initialized:
            raise VaultError("owner already set — use rotate to change it")
        salt = os.urandom(16)
        key = _derive(passphrase, salt)
        cred = OwnerCredential(
            version=_CRED_VERSION, salt_b64=base64.b64encode(salt).decode(),
            verifier=_verifier(key), created_at=_now(), kdf=dict(_KDF))
        self._cred_path.write_text(cred.to_json(), encoding="utf-8")
        os.chmod(self._cred_path, 0o600)

    def verify_owner(self, passphrase: str) -> bool:
        """True iff the passphrase matches the owner credential."""
        if not self.is_initialized:
            return False
        cred = self._load_cred()
        salt = base64.b64decode(cred.salt_b64)
        key = _derive(passphrase, salt)
        return hmac.compare_digest(_verifier(key), cred.verifier)

    def _key_for(self, passphrase: str) -> bytes:
        """Return the Fernet key for a verified passphrase, or raise."""
        if not self.is_initialized:
            raise VaultError("vault not initialized — run `sov vault init`")
        if not self.verify_owner(passphrase):
            raise VaultLocked("passphrase does not match the owner credential")
        cred = self._load_cred()
        salt = base64.b64decode(cred.salt_b64)
        return _fernet_key(_derive(passphrase, salt))

    # ── encryption ─────────────────────────────────────────────────────────
    def _fernet(self, passphrase: str):
        if not _have_crypto():
            raise VaultUnavailable(
                "the 'cryptography' package is required — pip install cryptography")
        from cryptography.fernet import Fernet
        return Fernet(self._key_for(passphrase))

    def encrypt_bytes(self, data: bytes, passphrase: str) -> bytes:
        return self._fernet(passphrase).encrypt(data)

    def decrypt_bytes(self, token: bytes, passphrase: str) -> bytes:
        from cryptography.fernet import InvalidToken
        try:
            return self._fernet(passphrase).decrypt(token)
        except InvalidToken as exc:
            raise VaultLocked("could not decrypt — wrong passphrase or tampered data") from exc

    def encrypt_file(self, path: Path, passphrase: str, *,
                     dest: Optional[Path] = None,
                     remove_plaintext: bool = False) -> Path:
        path = Path(path)
        if not path.exists():
            raise VaultError(f"no such file: {path}")
        dest = Path(dest) if dest else path.with_suffix(path.suffix + ".enc")
        token = self.encrypt_bytes(path.read_bytes(), passphrase)
        dest.write_bytes(token)
        os.chmod(dest, 0o600)
        if remove_plaintext:
            path.unlink()
        return dest

    def decrypt_file(self, enc_path: Path, passphrase: str, *,
                     dest: Optional[Path] = None) -> Path:
        enc_path = Path(enc_path)
        if not enc_path.exists():
            raise VaultError(f"no such file: {enc_path}")
        if dest is None:
            dest = (enc_path.with_suffix("") if enc_path.suffix == ".enc"
                    else enc_path.with_suffix(enc_path.suffix + ".dec"))
        data = self.decrypt_bytes(enc_path.read_bytes(), passphrase)
        Path(dest).write_bytes(data)
        return Path(dest)

    # ── rotation (change passphrase; re-encrypt named files) ────────────────
    def rotate(self, old_passphrase: str, new_passphrase: str, *,
               files: tuple[Path, ...] = ()) -> list[Path]:
        """Change the owner passphrase. Any `files` (encrypted under the old
        key) are decrypted and re-encrypted under the new one. Returns the
        list of re-encrypted files."""
        if not self.verify_owner(old_passphrase):
            raise VaultLocked("current passphrase does not match")
        if not new_passphrase or len(new_passphrase) < 8:
            raise VaultError("new passphrase must be at least 8 characters")

        # decrypt all targets under the old key FIRST (fail before we re-key)
        plaintexts: list[tuple[Path, bytes]] = []
        for f in files:
            f = Path(f)
            plaintexts.append((f, self.decrypt_bytes(f.read_bytes(), old_passphrase)))

        # write the new credential
        salt = os.urandom(16)
        key = _derive(new_passphrase, salt)
        cred = OwnerCredential(
            version=_CRED_VERSION, salt_b64=base64.b64encode(salt).decode(),
            verifier=_verifier(key), created_at=_now(), kdf=dict(_KDF))
        self._cred_path.write_text(cred.to_json(), encoding="utf-8")
        os.chmod(self._cred_path, 0o600)

        # re-encrypt targets under the new key
        rewritten: list[Path] = []
        for f, data in plaintexts:
            f.write_bytes(self.encrypt_bytes(data, new_passphrase))
            os.chmod(f, 0o600)
            rewritten.append(f)
        return rewritten


__all__ = ["Vault", "OwnerCredential", "VaultError", "VaultLocked",
           "VaultUnavailable"]
