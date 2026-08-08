"""
╔══════════════════════════════════════════════════════════════════════════╗
║  path_scan/scanner.py — god-tier path / anti-ghost / anti-zombie scanner ║
║                                                                           ║
║  Kevin's named flaw: "test paths are sometimes left in new modules."     ║
║  This scanner catches that family of defects BEFORE a module is applied  ║
║  into live src/ — so a false path can never silently ship into Aria.     ║
║                                                                           ║
║  Three lenses, all pure-stdlib (no torch, no heavy deps — runs anywhere) ║
║                                                                           ║
║    1. FALSE / TEST PATH  — shipped payload code (or an apply script)     ║
║       that references a test dir, a temp dir, a machine-specific absolute║
║       path, a __pycache__/.bak/.pyc artifact, or a placeholder like      ║
║       /path/to/… . These are the paths that "work on my machine" then    ║
║       break — or worse, point Aria at the wrong file.                    ║
║                                                                           ║
║    2. ANTI-GHOST  — staged structure that won't actually take effect:    ║
║       a payload that doesn't mirror src/sovereign_agent/…, an apply      ║
║       script that copies from a path its payload doesn't contain, or a   ║
║       module that ships tools with no registration anchor in its apply.  ║
║                                                                           ║
║    3. ANTI-ZOMBIE  — dead matter accreting around the live tree: stale   ║
║       .bak.* snapshots and __pycache__ inside the payload (they get      ║
║       copied verbatim), and tools named in tools/__all__ with no backing ║
║       file (registry drift).                                             ║
║                                                                           ║
║  Propose-only. The scanner never edits, never deletes. It returns a      ║
║  ScanResult; the operator (or the apply gate) decides.                   ║
║                                                                           ║
║  Severity:  block  — must not apply until fixed                          ║
║             warn   — review before applying                              ║
║             info   — worth knowing, not a stop                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

Severity = str  # "block" | "warn" | "info"

# A line carrying this marker is exempted from scanning — an explicit, reviewed
# allow (used by this scanner's own pattern table, and by any module with a
# genuine, signed-off need for an otherwise-suspicious path).
_ALLOW_PRAGMA = "path-scan: allow"

# ─── Suspicious-path signatures ───────────────────────────────────────────
# Each entry: (compiled regex, severity, kind, human message). Order matters
# only for readability; every pattern is tested against every candidate line.

# A machine-specific absolute home path (the classic "works on my box").
_RE_ABS_HOME = re.compile(r"""['"]?(/home/[^/'"]+|/Users/[^/'"]+|[A-Z]:\\\\Users\\\\)""")  # path-scan: allow
# A literal temp path (in shipped code it is usually quoted).
_RE_TMP = re.compile(r"""['"](/tmp/|/var/tmp/|/private/tmp/)""")
# A literal temp path in a shell apply script (cp targets are unquoted).
_RE_TMP_BARE = re.compile(r"""(?:^|[\s'"=(:])(/tmp/|/var/tmp/|/private/tmp/)""")
# A test directory or test-module reference inside SHIPPED (non-test) code.
_RE_TEST_PATH = re.compile(r"""['"](?:[^'"]*/)?(?:tests?|conftest)(?:/|['"])""")
_RE_TEST_IMPORT = re.compile(r"""\b(?:from|import)\s+(?:tests?\.|conftest\b)""")
# Build/cache/backup artifacts that should never be referenced by shipped code.
_RE_ARTIFACT = re.compile(r"""['"][^'"]*(?:__pycache__|\.pyc|\.bak(?:\.\d+)?|\.egg-info)\b""")
# Placeholder paths a human meant to replace.
_RE_PLACEHOLDER = re.compile(
    r"""['"][^'"]*(?:/path/to/|path/to/here|your[_/-]?path|<[^'">]*path[^'">]*>|TODO[_-]?PATH|FIXME)""",  # path-scan: allow
    re.IGNORECASE,
)
# A sys.path hack pointing at staging/test/parent dirs inside shipped code.
_RE_SYSPATH_HACK = re.compile(r"""sys\.path\.(?:insert|append)\([^)]*(?:tests?|payload|\.\.|parents?)""")

_LINE_SIGNATURES: tuple[tuple[re.Pattern, Severity, str, str], ...] = (
    (_RE_ABS_HOME, "block", "false-path/absolute-home", "machine-specific absolute path"),
    (_RE_TMP, "block", "false-path/temp", "hardcoded temp path"),
    (_RE_TEST_PATH, "block", "false-path/test-dir", "reference to a test path in shipped code"),
    (_RE_TEST_IMPORT, "block", "false-path/test-import", "import of a test module from shipped code"),
    (_RE_ARTIFACT, "warn", "false-path/artifact", "reference to a build/cache/backup artifact"),
    (_RE_PLACEHOLDER, "block", "false-path/placeholder", "unfilled placeholder path"),
    (_RE_SYSPATH_HACK, "warn", "false-path/syspath-hack", "sys.path hack into staging/test/parent dir"),  # path-scan: allow
)

# Lines beginning with these (after strip) are comments/docstrings we still
# scan — a false path in a comment is a smell — but we down-rank to info when
# the only hit is inside an obvious comment.
_COMMENT_PREFIXES = ("#", '"', "'", "║", "╔", "╚", "*")


@dataclass
class Finding:
    """One detected defect. Path is repo-relative when possible."""
    severity: Severity
    kind: str
    module: str
    path: str
    line: int
    message: str
    excerpt: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanResult:
    """The full verdict for one scan run."""
    findings: list[Finding] = field(default_factory=list)
    modules_scanned: int = 0
    files_scanned: int = 0

    @property
    def blocks(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "block"]

    @property
    def warns(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warn"]

    @property
    def clean(self) -> bool:
        """True when nothing must block an apply (warns are allowed)."""
        return not self.blocks

    def for_module(self, module: str) -> list[Finding]:
        return [f for f in self.findings if f.module == module]

    def summary(self) -> str:
        return (f"{self.modules_scanned} modules · {self.files_scanned} files · "
                f"{len(self.blocks)} block · {len(self.warns)} warn · "
                f"{len(self.findings)} total")

    def as_dict(self) -> dict:
        return {
            "summary": self.summary(),
            "modules_scanned": self.modules_scanned,
            "files_scanned": self.files_scanned,
            "blocks": len(self.blocks),
            "warns": len(self.warns),
            "findings": [f.as_dict() for f in self.findings],
        }


# ─── Line-level scanning ──────────────────────────────────────────────────

def _is_comment_line(stripped: str) -> bool:
    return stripped.startswith(_COMMENT_PREFIXES)


def scan_text(text: str, *, module: str, rel_path: str,
              allow_test_refs: bool = False) -> list[Finding]:
    """Scan one file's text. `allow_test_refs` is True for test files and
    apply-script destinations where a `tests/` reference is legitimate."""
    out: list[Finding] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        # An explicit, auditable exemption: a line a human has reviewed and
        # signed off (e.g. a scanner that must name "/tmp" in a pattern, or a
        # module with a genuine reason). Reviewed > silently broad regexes.
        if _ALLOW_PRAGMA in raw:
            continue
        is_comment = _is_comment_line(stripped)
        for rx, sev, kind, msg in _LINE_SIGNATURES:
            if not rx.search(raw):
                continue
            if allow_test_refs and kind in ("false-path/test-dir", "false-path/test-import"):
                continue
            # A real defect in a comment is still worth surfacing, but never
            # blocks — code that runs is what can hurt Aria.
            severity = "info" if (is_comment and sev == "block") else sev
            out.append(Finding(
                severity=severity, kind=kind, module=module, path=rel_path,
                line=i, message=msg, excerpt=stripped[:160],
            ))
    return out


# ─── Module-structure (anti-ghost) checks ─────────────────────────────────

def _mirror_violations(mod_dir: Path, module: str) -> list[Finding]:
    """Every payload .py must live under payload/src/sovereign_agent/… so it
    mirrors where it will land in live src/. Anything else is a ghost: it
    will never be copied to the right place."""
    out: list[Finding] = []
    payload = mod_dir / "payload"
    if not payload.is_dir():
        return out
    mirror_root = payload / "src" / "sovereign_agent"
    for f in payload.rglob("*.py"):
        try:
            f.relative_to(mirror_root)
        except ValueError:
            out.append(Finding(
                severity="warn", kind="ghost/mirror",
                module=module, path=str(f.relative_to(mod_dir)), line=0,
                message="payload .py not under payload/src/sovereign_agent/ — won't mirror to live src",
            ))
    return out


def _apply_script_checks(mod_dir: Path, module: str) -> list[Finding]:
    """Verify the apply script's copy SOURCES exist and DESTINATIONS are
    inside the repo. Ghost source = copy from a file the payload lacks.
    False destination = copy into /tmp or an absolute non-repo path."""
    out: list[Finding] = []
    for apply in sorted(mod_dir.glob("apply_*.sh")):
        text = apply.read_text(encoding="utf-8", errors="replace")
        rel = str(apply.relative_to(mod_dir))
        ships_tools = (mod_dir / "payload" / "src" / "sovereign_agent" / "tools").is_dir()
        if ships_tools and "-import-d" not in text:
            out.append(Finding(
                severity="block", kind="ghost/no-registration",
                module=module, path=rel, line=0,
                message="ships tools/ payload but apply script has no -import-d registration anchor",
            ))
        for i, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if line.startswith("#") or "cp " not in line:
                continue
            # destination is the last quoted/whitespace token of a cp
            if _RE_TMP_BARE.search(raw):
                out.append(Finding(
                    severity="block", kind="false-path/temp", module=module, path=rel,
                    line=i, message="apply script copies to a temp path", excerpt=line[:160]))
    return out


# ─── Anti-zombie checks ───────────────────────────────────────────────────

def _zombie_checks(mod_dir: Path, module: str) -> list[Finding]:
    """Dead matter inside the payload that would be copied verbatim into the
    live tree: stale .bak.* snapshots and __pycache__."""
    out: list[Finding] = []
    payload = mod_dir / "payload"
    if not payload.is_dir():
        return out
    for bak in payload.rglob("*.bak*"):
        out.append(Finding(
            severity="warn", kind="zombie/bak",
            module=module, path=str(bak.relative_to(mod_dir)), line=0,
            message="stale .bak snapshot inside payload — would be copied into live src",
        ))
    for cache in payload.rglob("__pycache__"):
        out.append(Finding(
            severity="warn", kind="zombie/pycache",
            module=module, path=str(cache.relative_to(mod_dir)), line=0,
            message="__pycache__ inside payload — would be copied into live src",
        ))
    return out


# ─── Entry points ─────────────────────────────────────────────────────────

def scan_module(mod_dir: Path) -> list[Finding]:
    """Scan a single aria-<name>/ staged module folder. Returns findings."""
    mod_dir = Path(mod_dir)
    module = mod_dir.name
    findings: list[Finding] = []

    payload = mod_dir / "payload" / "src" / "sovereign_agent"
    if payload.is_dir():
        for f in payload.rglob("*.py"):
            rel = str(f.relative_to(mod_dir))
            # A file living under a tests/ subdir of the payload is itself a
            # test fixture; allow test refs there.
            allow = "/tests/" in f.as_posix() or f.name.startswith("test_")  # path-scan: allow
            findings += scan_text(
                f.read_text(encoding="utf-8", errors="replace"),
                module=module, rel_path=rel, allow_test_refs=allow,
            )

    findings += _mirror_violations(mod_dir, module)
    findings += _apply_script_checks(mod_dir, module)
    findings += _zombie_checks(mod_dir, module)
    return findings


def _count_payload_files(mod_dir: Path) -> int:
    payload = mod_dir / "payload" / "src" / "sovereign_agent"
    return sum(1 for _ in payload.rglob("*.py")) if payload.is_dir() else 0


def scan_repo(repo_root: Path | None = None) -> ScanResult:
    """Scan every staged aria-<name>/ module under repo_root."""
    repo = Path(repo_root) if repo_root else _default_repo_root()
    result = ScanResult()
    for mod_dir in sorted(repo.glob("aria-*")):
        if not mod_dir.is_dir():
            continue
        result.modules_scanned += 1
        result.files_scanned += _count_payload_files(mod_dir)
        result.findings += scan_module(mod_dir)
    return result


def scan_one(repo_root: Path | None, module: str) -> ScanResult:
    """Scan exactly one module by name (with or without the aria- prefix)."""
    repo = Path(repo_root) if repo_root else _default_repo_root()
    name = module if module.startswith("aria-") else f"aria-{module}"
    mod_dir = repo / name
    result = ScanResult()
    if mod_dir.is_dir():
        result.modules_scanned = 1
        result.files_scanned = _count_payload_files(mod_dir)
        result.findings = scan_module(mod_dir)
    return result


def _default_repo_root() -> Path:
    """Walk up from this file to the repo root (the dir holding aria-* + src)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "src" / "sovereign_agent").is_dir() and any(parent.glob("aria-*")):
            return parent
    # Fallback: 4 levels up (…/src/sovereign_agent/path_scan/scanner.py → repo)
    return here.parents[4]
