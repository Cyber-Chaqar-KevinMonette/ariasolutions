"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/corrections.py — the operator-correction loop                ║
║  v0.2.22.0                                                                ║
║                                                                           ║
║  When Aria misclassifies a message, Kevin should be able to correct her ║
║  WITHOUT retraining anything. The correction is logged. Future          ║
║  interpretations include recent corrections in their context, so Aria   ║
║  reads "last week Kevin said this kind of message belongs in `humor`,   ║
║  not `specialist`" before deciding what to do with the current message. ║
║                                                                           ║
║  This is in-context learning. No fine-tuning. No retraining. Just       ║
║  Aria reading her own audit log and adjusting.                          ║
║                                                                           ║
║  Doctrine (MOS-SURFACE §22.2 — to be added):                             ║
║                                                                           ║
║    Corrections are signed by the operator. Unsigned corrections in the  ║
║    context-injection path are a prompt-injection vector (an attacker    ║
║    who controls past corrections controls future classifications).      ║
║    The signature is verified before a correction is included in the    ║
║    in-context examples.                                                  ║
║                                                                           ║
║  Storage:                                                                ║
║    <data_dir>/corrections.jsonl — append-only, signed.                  ║
║                                                                           ║
║  Authority:                                                              ║
║    Issuing a correction is tier 1. Reading is tier 0.                  ║
║    Corrections are NEVER auto-generated; only the operator writes them. ║
║    (Aria's self-corrections live separately, in the apprentice loop —  ║
║    see field_notes.py for now; promoted to its own module in v0.2.23.0.)║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass
class Correction:
    """One operator correction of a past interpretation.

    Fields:
        correction_id     stable UUID for retrieval and reference
        original_text     what Kevin had typed
        original_action   what Aria did (e.g. "saved to specialist")
        corrected_action  what she should have done (e.g. "save to humor")
        explanation       Kevin's free-text reasoning — the most
                          load-bearing field for in-context learning
        ts                ISO timestamp
        signature         HMAC-SHA256 over (correction_id || original_text
                          || corrected_action) — proves the correction
                          came from the operator's key, not an attacker
                          who tampered with the JSONL file
    """
    correction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    original_text: str = ""
    original_action: str = ""
    corrected_action: str = ""
    explanation: str = ""
    ts: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
    )
    signature: str = ""

    def signing_blob(self) -> bytes:
        """Canonical bytes for signature. Includes only fields that
        should be cryptographically bound — the others are metadata
        the operator can amend without invalidating the signature."""
        canonical = "\n".join([
            self.correction_id,
            self.original_text,
            self.corrected_action,
            self.explanation,
        ])
        return canonical.encode("utf-8")

    def render(self) -> str:
        """Human-readable summary for in-context inclusion."""
        return (
            f"correction: \"{self.original_text[:80]}\" → "
            f"{self.corrected_action} ({self.explanation[:100]})"
        )


def _get_or_create_signing_key(key_path: Path) -> bytes:
    """Load the operator's correction-signing key, or create one if
    none exists. The key is local — never transmitted, never shared.

    The key file is 0o600 (operator-only readable). On creation we
    use os.urandom(32) for 256 bits of entropy.
    """
    if key_path.exists():
        return key_path.read_bytes()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = os.urandom(32)
    # Write with restrictive perms from the start
    fd = os.open(str(key_path), os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
    try:
        os.write(fd, key)
    finally:
        os.close(fd)
    return key


def sign_correction(c: Correction, signing_key: bytes) -> str:
    """Compute the HMAC over the signing blob. Sets c.signature and
    returns it."""
    sig = hmac.new(signing_key, c.signing_blob(), hashlib.sha256).hexdigest()
    c.signature = sig
    return sig


def verify_correction(c: Correction, signing_key: bytes) -> bool:
    """Verify a correction's signature. Returns True iff valid.
    Constant-time comparison protects against timing leaks."""
    if not c.signature:
        return False
    expected = hmac.new(
        signing_key, c.signing_blob(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, c.signature)


# ─── The corrections store ──────────────────────────────────────────────────


class CorrectionsStore:
    """Append-only signed log of operator corrections.

    The store does not load corrections into memory in bulk. The
    `recent_for_context()` method reads the tail of the file lazily
    and filters by signature validity, returning only verified
    corrections for inclusion in the LLM's in-context examples.
    """

    def __init__(self, log_path: Path, key_path: Path):
        self.log_path = Path(log_path)
        self.key_path = Path(key_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._signing_key = _get_or_create_signing_key(self.key_path)

    @property
    def signing_key(self) -> bytes:
        return self._signing_key

    def append(self, c: Correction) -> None:
        """Sign (if not already signed) and append. Atomic at the OS
        level for single-line writes; long explanations may need PIPE_BUF
        consideration but operator-paced volume keeps this safe."""
        if not c.signature:
            sign_correction(c, self._signing_key)
        line = json.dumps(asdict(c), ensure_ascii=False) + "\n"
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass

    def iter_all(self) -> Iterable[Correction]:
        if not self.log_path.exists():
            return
        with self.log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    yield Correction(**data)
                except TypeError:
                    # Forward-compatible: tolerate extra/missing fields
                    continue

    def recent_verified(self, n: int = 5) -> list[Correction]:
        """Most recent N corrections that pass signature verification.

        Unsigned or tampered corrections are skipped silently — they
        will be visible via `sov interpret corrections --all` for
        operator review, but they do NOT enter the in-context
        learning pipeline.

        This is the prompt-injection defense: an attacker who edits
        the corrections file directly will produce entries that fail
        verification. Aria reads only what Kevin actually signed.
        """
        verified: list[Correction] = []
        for c in self.iter_all():
            if verify_correction(c, self._signing_key):
                verified.append(c)
        return list(reversed(verified))[:n]

    def count(self) -> int:
        return sum(1 for _ in self.iter_all())


def format_corrections_for_prompt(
    corrections: list[Correction],
    *,
    max_chars: int = 1500,
) -> str:
    """Render a list of corrections as in-context examples for the
    interpreter prompt. Truncates to max_chars to fit context windows.

    The format is human-readable and prepended to the user message,
    so the model sees:

        Recent corrections from Kevin (learn from these):
          - "back is killing me" → save to back-pain, emotions
            (Kevin: this is about pain, not specialist content)
          - ...

        Now classify Kevin's current message:
        ...
    """
    if not corrections:
        return ""
    lines = ["Recent corrections from Kevin (learn from these):"]
    used = len(lines[0])
    for c in corrections:
        line = f"  - {c.render()}"
        if used + len(line) + 1 > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines) + "\n"


__all__ = [
    "Correction",
    "CorrectionsStore",
    "sign_correction",
    "verify_correction",
    "format_corrections_for_prompt",
]
