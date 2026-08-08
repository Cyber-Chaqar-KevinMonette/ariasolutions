"""
╔══════════════════════════════════════════════════════════════════════════╗
║  aegis/vault.py — encrypted out-of-band snapshot store                    ║
║                                                                           ║
║  The vault is the real "lockdown and restore" mechanism. If data_dir is ║
║  destroyed, encrypted, corrupted, or compromised, the vault is the      ║
║  recovery source.                                                         ║
║                                                                           ║
║  Design                                                                   ║
║                                                                           ║
║    • Snapshots live in a SEPARATE directory from data_dir, with         ║
║      separate permissions (0700/0600).                                  ║
║    • Each snapshot is a tarball, encrypted with AES-256-GCM via the     ║
║      cryptography library. If the library isn't installed, we fall back║
║      to a hash-chained obfuscation that gives tamper-evidence WITHOUT   ║
║      confidentiality — and we warn loudly. Confidentiality requires    ║
║      the real cipher.                                                   ║
║    • The vault key lives at ~/.config/sovereign-agent/vault.key with    ║
║      mode 0600. Separate key from the conductor key, on purpose: an    ║
║      attacker who compromises one cannot use it to forge the other.   ║
║    • Snapshots are Merkle-chained: each one references the prior's    ║
║      hash. Truncation is detectable.                                   ║
║                                                                           ║
║  Lifecycle                                                               ║
║                                                                           ║
║    vault = Vault(vault_dir, key_path)                                   ║
║    vault.bootstrap()                                                     ║
║    snap = vault.snapshot(source=data_dir, label="pre-upgrade")          ║
║    ...                                                                    ║
║    # Operator-only:                                                     ║
║    vault.restore(snap.snapshot_id, target=data_dir, confirm=True)      ║
║                                                                           ║
║  Authority                                                               ║
║                                                                           ║
║    snapshot() is callable by Aegis Conductor; restore() requires       ║
║    explicit operator confirmation (confirm=True must be passed).        ║
║    There is no auto-restore. A hostile entity that compromised the     ║
║    operator's terminal could theoretically pass confirm=True, but at  ║
║    that point the attacker already has shell access and we've lost    ║
║    on a different axis. The confirm gate is for accidental misuse.    ║
║                                                                           ║
║  Kill switch: SOV_NO_VAULT=1 disables snapshot/restore. The vault dir ║
║  on disk is unaffected by the switch — existing snapshots remain     ║
║  readable; just no new ones get written and restore() refuses.        ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import secrets
import stat
import tarfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

KILL_SWITCH_ENV = "SOV_NO_VAULT"
GENESIS_HASH = hashlib.sha256(b"vault-genesis-2026").hexdigest()

# Try to import cryptography. Fall back to obfuscation mode if missing.
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False
    AESGCM = None  # type: ignore[assignment,misc]


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ─── Exceptions ──────────────────────────────────────────────────────────


class VaultKeyError(Exception):
    """Raised when the vault key is missing, wrong permissions, or wrong size."""


class VaultRestoreRefused(Exception):
    """Raised when restore() is called without confirm=True, or in disabled mode."""


# ─── VaultSnapshot ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class VaultSnapshot:
    """One snapshot's metadata. The encrypted blob lives at blob_path."""
    snapshot_id: str                          # ULID
    taken_at: str
    source_root: str
    blob_path: str                            # absolute path to the .vault file
    blob_size: int
    plaintext_sha256: str                     # hash of the tarball BEFORE encryption
    cipher_mode: str                          # 'aes-256-gcm' or 'obfuscated-warning'
    label: str
    prior_hash: str
    entry_hash: str = ""

    def computed_hash(self) -> str:
        d = asdict(self)
        d.pop("entry_hash", None)
        blob = json.dumps(d, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()


# ─── Key management ──────────────────────────────────────────────────────


def load_or_create_vault_key(key_path: Path) -> bytes:
    """32-byte AES-256 key. Same permission discipline as the conductor key."""
    if key_path.is_file():
        st = key_path.stat()
        mode = stat.S_IMODE(st.st_mode)
        if mode != 0o600:
            raise VaultKeyError(
                f"vault key {key_path} has mode {oct(mode)}; expected 0o600. "
                f"Fix: chmod 600 {key_path}"
            )
        data = key_path.read_bytes()
        if len(data) != 32:
            raise VaultKeyError(
                f"vault key has length {len(data)}; expected 32 bytes"
            )
        return data

    key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = secrets.token_bytes(32)
    old_umask = os.umask(0o077)
    try:
        key_path.write_bytes(key)
        os.chmod(key_path, 0o600)
    finally:
        os.umask(old_umask)
    return key


# ─── Manifest (the chain) ────────────────────────────────────────────────


class _VaultManifest:
    """Plain JSONL of VaultSnapshot entries. The Merkle chain lives here."""

    def __init__(self, manifest_path: Path):
        self._path = manifest_path

    def append(self, snapshot: VaultSnapshot) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(snapshot), sort_keys=True) + "\n")
            f.flush()

    def all(self) -> list[VaultSnapshot]:
        if not self._path.is_file():
            return []
        out: list[VaultSnapshot] = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(VaultSnapshot(**json.loads(line)))
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue
        return out

    def latest(self) -> Optional[VaultSnapshot]:
        records = self.all()
        return records[-1] if records else None


# ─── The Vault ───────────────────────────────────────────────────────────


class Vault:
    """Encrypted out-of-band snapshot store.

    Default layout:
        vault_dir/
            manifest.jsonl          — chain of VaultSnapshot records
            blobs/                  — encrypted snapshot files (one per snapshot)
            (vault.key lives ELSEWHERE — separate dir, separate perms)
    """

    def __init__(self, vault_dir: Path, key_path: Path):
        self._vault_dir = vault_dir
        self._blobs_dir = vault_dir / "blobs"
        self._manifest_path = vault_dir / "manifest.jsonl"
        self._key_path = key_path
        self._manifest = _VaultManifest(self._manifest_path)
        self._key: Optional[bytes] = None

    @property
    def is_disabled(self) -> bool:
        return bool(os.environ.get(KILL_SWITCH_ENV))

    # ─── Bootstrap ──────────────────────────────────────────────────────

    def bootstrap(self) -> None:
        if self.is_disabled:
            logger.info("Vault disabled via %s", KILL_SWITCH_ENV)
            return
        self._vault_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._blobs_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._key = load_or_create_vault_key(self._key_path)
        if not _CRYPTO_AVAILABLE:
            logger.warning(
                "Vault: cryptography library not installed. "
                "Snapshots will use OBFUSCATION mode (tamper-evident only, "
                "NOT confidential). Install `cryptography` for AES-256-GCM."
            )

    # ─── Snapshot ───────────────────────────────────────────────────────

    def snapshot(
        self,
        *,
        snapshot_id: str,
        source: Path,
        label: str = "",
        excluded: Optional[list[str]] = None,
    ) -> VaultSnapshot:
        """Tar+encrypt the source tree to a new blob; append manifest entry."""
        if self.is_disabled:
            raise VaultRestoreRefused("vault is disabled via SOV_NO_VAULT")
        if self._key is None:
            self.bootstrap()
        assert self._key is not None

        excluded_set = set(excluded or ["__pycache__", ".venv", "node_modules"])

        # 1. Tar to in-memory buffer.
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for entry in source.rglob("*"):
                if any(part in excluded_set for part in entry.parts):
                    continue
                try:
                    arcname = entry.relative_to(source)
                    tar.add(entry, arcname=str(arcname), recursive=False)
                except (PermissionError, OSError):
                    continue
        plaintext = buf.getvalue()
        pt_hash = hashlib.sha256(plaintext).hexdigest()

        # 2. Encrypt (or fall back to obfuscation).
        blob_path = self._blobs_dir / f"{snapshot_id}.vault"
        if _CRYPTO_AVAILABLE:
            aesgcm = AESGCM(self._key)
            nonce = secrets.token_bytes(12)
            ciphertext = aesgcm.encrypt(nonce, plaintext, b"sovereign-agent-vault")
            blob_path.write_bytes(nonce + ciphertext)
            cipher_mode = "aes-256-gcm"
        else:
            # Obfuscation-only: XOR with key bytes and hash-stamp. NOT secure
            # against an attacker who reads the key (key + blob = plaintext).
            # Provides tamper-evidence via the manifest's Merkle chain only.
            obf = bytes(b ^ self._key[i % len(self._key)]
                        for i, b in enumerate(plaintext))
            tag = hashlib.sha256(self._key + plaintext).digest()
            blob_path.write_bytes(tag + obf)
            cipher_mode = "obfuscated-warning"
        os.chmod(blob_path, 0o600)

        # 3. Append manifest entry with Merkle link.
        latest = self._manifest.latest()
        prior_hash = latest.entry_hash if latest else GENESIS_HASH
        unsigned = VaultSnapshot(
            snapshot_id=snapshot_id,
            taken_at=_iso_now(),
            source_root=str(source),
            blob_path=str(blob_path),
            blob_size=blob_path.stat().st_size,
            plaintext_sha256=pt_hash,
            cipher_mode=cipher_mode,
            label=label,
            prior_hash=prior_hash,
            entry_hash="",
        )
        h = unsigned.computed_hash()
        sealed = VaultSnapshot(
            snapshot_id=unsigned.snapshot_id,
            taken_at=unsigned.taken_at,
            source_root=unsigned.source_root,
            blob_path=unsigned.blob_path,
            blob_size=unsigned.blob_size,
            plaintext_sha256=unsigned.plaintext_sha256,
            cipher_mode=unsigned.cipher_mode,
            label=unsigned.label,
            prior_hash=unsigned.prior_hash,
            entry_hash=h,
        )
        self._manifest.append(sealed)
        return sealed

    # ─── Restore (operator-only) ────────────────────────────────────────

    def restore(
        self,
        *,
        snapshot_id: str,
        target: Path,
        confirm: bool = False,
    ) -> Path:
        """Decrypt + un-tar the given snapshot to target dir.

        REQUIRES confirm=True. This is the operator's explicit
        acknowledgment that they understand what they're about to do.
        Without confirm=True, raises VaultRestoreRefused.
        """
        if self.is_disabled:
            raise VaultRestoreRefused("vault is disabled via SOV_NO_VAULT")
        if not confirm:
            raise VaultRestoreRefused(
                "restore() requires confirm=True — pass it ONLY after you "
                "understand the target dir will be overwritten"
            )
        if self._key is None:
            self.bootstrap()
        assert self._key is not None

        # Find the snapshot in the manifest.
        snap = next(
            (s for s in self._manifest.all() if s.snapshot_id == snapshot_id),
            None,
        )
        if snap is None:
            raise FileNotFoundError(f"snapshot {snapshot_id} not in manifest")

        blob = Path(snap.blob_path).read_bytes()
        if snap.cipher_mode == "aes-256-gcm":
            assert _CRYPTO_AVAILABLE
            aesgcm = AESGCM(self._key)
            nonce, ciphertext = blob[:12], blob[12:]
            plaintext = aesgcm.decrypt(nonce, ciphertext, b"sovereign-agent-vault")
        elif snap.cipher_mode == "obfuscated-warning":
            tag, obf = blob[:32], blob[32:]
            plaintext = bytes(b ^ self._key[i % len(self._key)]
                              for i, b in enumerate(obf))
            expected_tag = hashlib.sha256(self._key + plaintext).digest()
            if tag != expected_tag:
                raise ValueError("obfuscation tag mismatch — snapshot tampered")
        else:
            raise ValueError(f"unknown cipher_mode: {snap.cipher_mode}")

        if hashlib.sha256(plaintext).hexdigest() != snap.plaintext_sha256:
            raise ValueError("plaintext hash mismatch — snapshot tampered or corrupted")

        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(plaintext), mode="r") as tar:
            tar.extractall(target)
        return target

    # ─── Introspection ──────────────────────────────────────────────────

    def list_snapshots(self) -> list[VaultSnapshot]:
        return self._manifest.all()

    def verify_chain(self) -> Optional[str]:
        """Walk the manifest's Merkle chain. Return the snapshot_id of the
        first broken link, or None if intact."""
        prev = GENESIS_HASH
        for snap in self._manifest.all():
            if snap.prior_hash != prev:
                return snap.snapshot_id
            if snap.entry_hash != snap.computed_hash():
                return snap.snapshot_id
            prev = snap.entry_hash
        return None


__all__ = [
    "Vault", "VaultSnapshot",
    "VaultKeyError", "VaultRestoreRefused",
    "load_or_create_vault_key",
    "KILL_SWITCH_ENV", "GENESIS_HASH",
]
