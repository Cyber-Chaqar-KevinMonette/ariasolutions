"""
╔══════════════════════════════════════════════════════════════════════════╗
║  charter.py — Sovereign System Design Charter loader + validator         ║
║                                                                           ║
║  The Charter (SIGNAL.md) is the constitution of this tree. It binds      ║
║  not by goodwill but by mechanism: a content hash in the file header,    ║
║  a machine-readable YAML block at the end, and a kill switch in the       ║
║  CLI callback that refuses to dispatch when integrity is violated.       ║
║                                                                           ║
║  This module is responsible for:                                         ║
║    1. Locating SIGNAL.md in the source tree                              ║
║    2. Computing the canonical content hash (excluding the hash line      ║
║       itself, which is the chicken-and-egg sidestep)                     ║
║    3. Parsing the YAML block at the bottom                                ║
║    4. Cross-validating prose <-> YAML (article count, mode lattice, etc.)║
║    5. Returning a CharterIntegrity verdict that the doctor and the CLI   ║
║       callback both consult                                              ║
║                                                                           ║
║  The contract is one-directional: code reads the charter and conforms.   ║
║  Code does not edit the charter. The only sanctioned write path is       ║
║  `sov charter amend`, which produces a charter_amendment event before    ║
║  rewriting the hash header.                                              ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

# YAML is a runtime dependency of this module. PyYAML is already in the
# transitive deps (via several existing packages), so this import does not
# add a new top-level dep. If it were missing, the charter would still
# resolve as "unparseable YAML" rather than crashing.
try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    yaml = None  # type: ignore[assignment]
    _YAML_AVAILABLE = False


CHARTER_FILENAME = "SIGNAL.md"
CHARTER_HASH_HEADER_RE = re.compile(
    r"^(?P<prefix>\s*charter-hash:\s*sha256:)(?P<hash>[A-Fa-f0-9]+|PENDING)\s*$",
    re.MULTILINE,
)
CHARTER_VERSION_HEADER_RE = re.compile(
    r"^\s*charter-version:\s*(?P<version>[0-9]+\.[0-9]+\.[0-9]+)\s*$",
    re.MULTILINE,
)
YAML_BLOCK_FENCE_RE = re.compile(r"```yaml\s*\n(?P<body>.*?)\n```", re.DOTALL)

IntegrityLevel = Literal["ok", "warning", "error"]


@dataclass(frozen=True)
class CharterIntegrity:
    """The verdict the doctor and the CLI callback both consult.

    `kill_switch_active=True` means: refuse to dispatch anything except
    the charter-management subcommands. This is Article V made mechanical.
    """
    level: IntegrityLevel
    summary: str
    detail: str = ""
    kill_switch_active: bool = False
    version: str | None = None
    expected_hash: str | None = None
    recorded_hash: str | None = None
    charter_path: Path | None = None


@dataclass
class CharterContents:
    """Parsed charter — only populated when integrity passes."""
    version: str
    content_hash: str
    yaml_block: dict[str, Any] = field(default_factory=dict)
    article_count: int = 0
    max_articles: int = 7


# ─── Locating the charter ─────────────────────────────────────────────────


def find_charter_path() -> Path | None:
    """Walk up from this module's location looking for SIGNAL.md.

    Editable installs: the file is at the source-tree root, alongside
    pyproject.toml and ARIA.md.
    Non-editable installs: the file is not bundled into the wheel by default
    (we don't list it as package data), so this returns None and the doctor
    reports the absent-charter warning path.
    """
    candidates = [
        Path(__file__).parent.parent.parent / CHARTER_FILENAME,
        Path.cwd() / CHARTER_FILENAME,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


# ─── Hashing ──────────────────────────────────────────────────────────────


def _strip_hash_line_for_hashing(text: str) -> str:
    """Remove the `charter-hash:` line so the hash is over content-excluding-itself.

    Sidesteps the chicken-and-egg: the hash header records the hash of
    everything EXCEPT the hash header. Replacement, not removal, keeps
    line numbers stable for diffs.
    """
    return CHARTER_HASH_HEADER_RE.sub(
        lambda m: f"{m.group('prefix')}<EXCLUDED-FROM-HASH>",
        text,
        count=1,
    )


def compute_content_hash(text: str) -> str:
    """Canonical hash. Lowercase hex sha256 over (text - hash line)."""
    canonical = _strip_hash_line_for_hashing(text).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def extract_recorded_hash(text: str) -> str | None:
    """Return the hex hash recorded in the header, or None if missing/PENDING."""
    m = CHARTER_HASH_HEADER_RE.search(text)
    if m is None:
        return None
    h = m.group("hash")
    if h == "PENDING":
        return None
    return h.lower()


def extract_version(text: str) -> str | None:
    m = CHARTER_VERSION_HEADER_RE.search(text)
    return m.group("version") if m else None


def rewrite_hash_in_text(text: str, new_hash: str) -> str:
    """Used only by `sov charter amend`. Replaces the hash in place."""
    return CHARTER_HASH_HEADER_RE.sub(
        lambda m: f"{m.group('prefix')}{new_hash}",
        text,
        count=1,
    )


# ─── YAML parsing + cross-validation ──────────────────────────────────────


def extract_yaml_block(text: str) -> str | None:
    matches = YAML_BLOCK_FENCE_RE.findall(text)
    # The charter's machine-readable block is the LAST yaml fence in the file
    # (the prose may reference yaml syntax in earlier examples).
    return matches[-1] if matches else None


def parse_yaml_block(block: str) -> dict[str, Any] | None:
    if not _YAML_AVAILABLE or yaml is None:
        return None
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def count_articles_in_prose(text: str) -> int:
    """Count level-2 headings that look like 'I.', 'II.', etc.

    Roman numerals up to VII for now; higher will be caught by max_articles
    enforcement.
    """
    pattern = re.compile(r"^##\s+(I|II|III|IV|V|VI|VII|VIII|IX|X)\.\s+", re.MULTILINE)
    return len(pattern.findall(text))


# ─── The verdict ──────────────────────────────────────────────────────────


def check_integrity() -> CharterIntegrity:
    """The single function the doctor and CLI callback both call.

    Levels:
      - ok       : charter file present, hash matches, YAML matches prose
      - warning  : charter file ABSENT (migration window; commands proceed)
      - error    : charter present but tampered with (kill switch fires)

    The kill switch fires ONLY on `error`, never on `warning`. Operators
    upgrading from a pre-charter release won't have SIGNAL.md and must
    not be stranded.
    """
    path = find_charter_path()
    if path is None:
        return CharterIntegrity(
            level="warning",
            summary="charter absent (SIGNAL.md not in source tree)",
            detail=(
                "Article-zero check: the charter file itself was not found.\n"
                "  This is the pre-charter migration warning; commands continue.\n"
                "  Per Article IV, this state is 'unknown' — strictly worse than\n"
                "  'degraded', but the kill switch defers until a charter is present\n"
                "  in the operator's tree."
            ),
            kill_switch_active=False,
        )

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return CharterIntegrity(
            level="error",
            summary=f"charter unreadable: {e}",
            kill_switch_active=True,
            charter_path=path,
        )

    version = extract_version(text)
    recorded = extract_recorded_hash(text)
    expected = compute_content_hash(text)

    if recorded is None:
        return CharterIntegrity(
            level="error",
            summary="charter hash header missing or PENDING",
            detail=(
                "Article V violation: SIGNAL.md has no recorded hash, or its hash\n"
                "  is still the placeholder PENDING. Run `sov charter amend\n"
                "  --rationale 'initial ratification'` to seal the charter."
            ),
            kill_switch_active=True,
            version=version,
            expected_hash=expected,
            charter_path=path,
        )

    if recorded != expected:
        return CharterIntegrity(
            level="error",
            summary="charter hash MISMATCH — file has been edited without amendment",
            detail=(
                f"Article V violation: charter file was edited without a\n"
                f"  corresponding `sov charter amend` event.\n"
                f"  recorded: sha256:{recorded}\n"
                f"  computed: sha256:{expected}\n"
                f"  Repair: either revert the edit, or run\n"
                f"    sov charter amend --rationale '<why>'"
            ),
            kill_switch_active=True,
            version=version,
            expected_hash=expected,
            recorded_hash=recorded,
            charter_path=path,
        )

    yaml_block = extract_yaml_block(text)
    if yaml_block is None:
        return CharterIntegrity(
            level="error",
            summary="charter YAML block missing",
            kill_switch_active=True,
            version=version,
            expected_hash=expected,
            recorded_hash=recorded,
            charter_path=path,
        )

    parsed = parse_yaml_block(yaml_block)
    if parsed is None:
        return CharterIntegrity(
            level="error",
            summary="charter YAML block does not parse",
            detail="The machine-readable bindings at the end of SIGNAL.md must be valid YAML.",
            kill_switch_active=True,
            version=version,
            expected_hash=expected,
            recorded_hash=recorded,
            charter_path=path,
        )

    # Cross-validation: prose article count vs. YAML article list length vs. max_articles.
    prose_count = count_articles_in_prose(text)
    charter_section = parsed.get("charter", {}) if isinstance(parsed.get("charter"), dict) else {}
    yaml_articles = charter_section.get("articles") if isinstance(charter_section, dict) else None
    yaml_count = len(yaml_articles) if isinstance(yaml_articles, list) else 0
    max_articles = charter_section.get("max_articles", 7) if isinstance(charter_section, dict) else 7

    if prose_count != yaml_count:
        return CharterIntegrity(
            level="error",
            summary=f"prose ↔ YAML article mismatch (prose={prose_count}, yaml={yaml_count})",
            detail=(
                "The prose articles and the YAML article list disagree.\n"
                "  This is Article I's 'no silent degradation' applied to the charter\n"
                "  itself: the document is not allowed to lie to its own code."
            ),
            kill_switch_active=True,
            version=version,
            expected_hash=expected,
            recorded_hash=recorded,
            charter_path=path,
        )

    if prose_count > max_articles:
        return CharterIntegrity(
            level="error",
            summary=f"article count ({prose_count}) exceeds max_articles ({max_articles})",
            detail=(
                f"CHARTER INFLATION: the charter must contain no more than\n"
                f"  {max_articles} articles. Found {prose_count}.\n"
                f"  Resolution: either remove an article, or raise the cap via\n"
                f"  a deliberate amendment (and explain why in the rationale)."
            ),
            kill_switch_active=True,
            version=version,
            expected_hash=expected,
            recorded_hash=recorded,
            charter_path=path,
        )

    return CharterIntegrity(
        level="ok",
        summary=f"charter v{version} · {prose_count}/{max_articles} articles · hash verified",
        detail=f"path: {path}",
        kill_switch_active=False,
        version=version,
        expected_hash=expected,
        recorded_hash=recorded,
        charter_path=path,
    )


# ─── Public ───────────────────────────────────────────────────────────────


__all__ = [
    "CharterIntegrity",
    "CharterContents",
    "CHARTER_FILENAME",
    "check_integrity",
    "find_charter_path",
    "compute_content_hash",
    "extract_recorded_hash",
    "extract_version",
    "extract_yaml_block",
    "parse_yaml_block",
    "rewrite_hash_in_text",
    "count_articles_in_prose",
]
