"""
╔══════════════════════════════════════════════════════════════════════════╗
║  validators.py — Pre-atomize syntax & indentation guards                 ║
║  v0.2.13                                                                  ║
║                                                                           ║
║  Before atomize commits the cycle's output to atoms.db, every file goes  ║
║  through type-appropriate validation. Files that fail are quarantined    ║
║  (moved to <cycle_dir>/quarantine/) with a companion .errors.json that   ║
║  details what went wrong. Quarantined files are NOT atomized — they      ║
║  must not influence future cycles by sitting in memory_search results.   ║
║                                                                           ║
║  WHY THIS MATTERS:                                                       ║
║                                                                           ║
║  LLMs writing code routinely produce "almost-valid" output:              ║
║    • Python with mixed tabs and spaces (looks fine, fails at runtime)    ║
║    • JSON missing a closing brace                                        ║
║    • YAML with mis-indented children                                     ║
║    • Markdown with null bytes from a bad encoding round-trip             ║
║                                                                           ║
║  Without this validation, broken code propagates: it gets atomized,      ║
║  becomes part of the agent's working memory, and the next cycle's       ║
║  ideate/architect step might "remember" the broken pattern as if it      ║
║  were a successful one. THIS MODULE IS THE IMMUNE RESPONSE.             ║
║                                                                           ║
║  Validators are lenient on intent (we don't enforce style) and strict   ║
║  on correctness (the file must run / parse / load).                      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import ast
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ValidationResult:
    """Result of validating one file.

    Attributes:
        ok: True iff the file passed all checks.
        path: relative path within the validated tree, for reporting.
        kind: detected file kind (python/json/yaml/markdown/text/binary).
        errors: list of human-readable error strings (empty if ok).
        warnings: non-fatal observations (file was checked, no quarantine).
    """
    ok: bool
    path: str
    kind: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "path": self.path, "kind": self.kind,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


# Public limit constants — kept sane and easily auditable.
MAX_PYTHON_FILE_LINES = 5_000
MAX_JSON_DEPTH = 32


# ─── Per-kind validators ────────────────────────────────────────────────────


def validate_python_source(text: str, *, path: str = "") -> ValidationResult:
    """Validate Python source. Catches syntax + tab/space mixing.

    Order of checks (cheapest first):
      1. Non-empty.
      2. AST parses.
      3. No mixed tab/space indentation in the same logical block.
      4. File length under MAX_PYTHON_FILE_LINES (warning only).

    Returns a ValidationResult; does NOT raise.
    """
    res = ValidationResult(ok=True, path=path, kind="python")

    if not text or not text.strip():
        res.ok = False
        res.errors.append("empty file")
        return res

    if "\x00" in text:
        res.ok = False
        res.errors.append("null bytes present (encoding error?)")
        return res

    # AST parse — the gold-standard syntax check.
    try:
        ast.parse(text)
    except SyntaxError as e:
        res.ok = False
        res.errors.append(
            f"SyntaxError at line {e.lineno} col {e.offset}: {e.msg}"
        )
        return res

    # Tab/space mixing detection. We classify each non-blank line by its
    # leading whitespace style. A SINGLE file with both styles is the
    # smoking gun. (Some valid files have e.g. tabs in docstrings; we
    # look only at LEADING whitespace.)
    tabs_seen = False
    spaces_seen = False
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        # Skip lines that don't start with whitespace.
        stripped_lstripped = line.lstrip(" \t")
        if line == stripped_lstripped:
            continue
        leading = line[: len(line) - len(stripped_lstripped)]
        if "\t" in leading:
            tabs_seen = True
        if " " in leading:
            spaces_seen = True
        if tabs_seen and spaces_seen:
            res.ok = False
            res.errors.append(
                f"mixed tabs and spaces in indentation (first detected near "
                f"line {i})"
            )
            return res

    # File-length warning (does not fail).
    n_lines = text.count("\n") + 1
    if n_lines > MAX_PYTHON_FILE_LINES:
        res.warnings.append(
            f"file is {n_lines} lines (over MAX_PYTHON_FILE_LINES="
            f"{MAX_PYTHON_FILE_LINES}); consider splitting"
        )

    return res


def validate_json(text: str, *, path: str = "") -> ValidationResult:
    """Validate JSON. Catches parse errors and excessive nesting depth."""
    res = ValidationResult(ok=True, path=path, kind="json")

    if not text or not text.strip():
        res.ok = False
        res.errors.append("empty file")
        return res

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        res.ok = False
        res.errors.append(
            f"JSONDecodeError at line {e.lineno} col {e.colno}: {e.msg}"
        )
        return res

    depth = _json_depth(parsed)
    if depth > MAX_JSON_DEPTH:
        res.warnings.append(
            f"nesting depth {depth} exceeds MAX_JSON_DEPTH={MAX_JSON_DEPTH}"
        )

    return res


def _json_depth(obj: Any, current: int = 0) -> int:
    """Compute max nesting depth of a parsed JSON object."""
    if isinstance(obj, dict):
        if not obj:
            return current + 1
        return max(_json_depth(v, current + 1) for v in obj.values())
    if isinstance(obj, list):
        if not obj:
            return current + 1
        return max(_json_depth(v, current + 1) for v in obj)
    return current


def validate_yaml(text: str, *, path: str = "") -> ValidationResult:
    """Validate YAML using yaml.safe_load. Catches syntax issues."""
    res = ValidationResult(ok=True, path=path, kind="yaml")

    if not text or not text.strip():
        res.ok = False
        res.errors.append("empty file")
        return res

    try:
        import yaml  # local — only required for YAML files
    except ImportError:
        res.warnings.append("PyYAML not installed; skipping YAML validation")
        return res

    try:
        yaml.safe_load(text)
    except yaml.YAMLError as e:
        res.ok = False
        res.errors.append(f"YAMLError: {e}")
        return res

    return res


def validate_markdown(text: str, *, path: str = "") -> ValidationResult:
    """Validate Markdown. Soft checks — markdown is forgiving by design."""
    res = ValidationResult(ok=True, path=path, kind="markdown")

    if not text or not text.strip():
        res.ok = False
        res.errors.append("empty file")
        return res

    if "\x00" in text:
        res.ok = False
        res.errors.append("null bytes present (encoding error?)")
        return res

    # Soft: warn if document has zero headers and no paragraph structure.
    if "# " not in text and "## " not in text and "\n\n" not in text:
        res.warnings.append(
            "no headers and no paragraph breaks detected; suspicious for "
            "a structured document"
        )

    return res


def validate_text(text: str, *, path: str = "") -> ValidationResult:
    """Generic text-file check. Just non-empty and not binary-shaped."""
    res = ValidationResult(ok=True, path=path, kind="text")

    if not text:
        res.ok = False
        res.errors.append("empty file")
        return res

    if "\x00" in text:
        res.ok = False
        res.errors.append("null bytes present (likely binary content)")
        return res

    return res


# ─── Dispatcher ─────────────────────────────────────────────────────────────


_EXT_TO_VALIDATOR = {
    ".py": validate_python_source,
    ".json": validate_json,
    ".yaml": validate_yaml,
    ".yml": validate_yaml,
    ".md": validate_markdown,
    ".markdown": validate_markdown,
    ".txt": validate_text,
    ".rst": validate_text,
}


def validate_file(file_path: Path, *, base: Path | None = None) -> ValidationResult:
    """Read a file and route it to the right validator by extension.

    Files with extensions we don't know are validated as text. Binary
    files (gif/png/jar/...) are flagged for skipping by callers — we
    return ok=False with a 'binary' kind.
    """
    if base is not None:
        try:
            rel = str(file_path.relative_to(base))
        except ValueError:
            rel = file_path.name
    else:
        rel = file_path.name

    ext = file_path.suffix.lower()

    # Binary-ish extensions: we just skip rather than try to validate.
    BINARY_EXTS = {
        ".gif", ".png", ".jpg", ".jpeg", ".webp", ".pdf",
        ".zip", ".tar", ".gz", ".bz2", ".xz", ".jar", ".so",
        ".dll", ".exe", ".o", ".a", ".pyc", ".pyo", ".class",
        ".db", ".sqlite", ".sqlite3", ".bin", ".dat",
    }
    if ext in BINARY_EXTS:
        return ValidationResult(
            ok=True, path=rel, kind="binary",
            warnings=[f"binary extension {ext}; not validated"],
        )

    try:
        text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        return ValidationResult(
            ok=False, path=rel, kind="unknown",
            errors=[f"UTF-8 decode error: {e}"],
        )
    except OSError as e:
        return ValidationResult(
            ok=False, path=rel, kind="unknown",
            errors=[f"could not read file: {e}"],
        )

    validator = _EXT_TO_VALIDATOR.get(ext, validate_text)
    return validator(text, path=rel)


def quarantine_file(
    file_path: Path, *, cycle_dir: Path, result: ValidationResult,
) -> Path:
    """Move a failing file to <cycle_dir>/quarantine/ with a .errors.json.

    Returns the new path of the quarantined file. Writing the companion
    .errors.json next to it documents the failure for the operator.

    Idempotent: if the quarantine target already exists (resume after
    crash), we suffix with '-N'.
    """
    qdir = cycle_dir / "quarantine"
    qdir.mkdir(parents=True, exist_ok=True)

    try:
        rel = file_path.relative_to(cycle_dir)
    except ValueError:
        rel = Path(file_path.name)

    target = qdir / rel
    target.parent.mkdir(parents=True, exist_ok=True)

    final = target
    n = 1
    while final.exists():
        final = target.with_name(f"{target.stem}-{n}{target.suffix}")
        n += 1

    shutil.move(str(file_path), str(final))
    errors_companion = final.with_suffix(final.suffix + ".errors.json")
    errors_companion.write_text(
        json.dumps(result.to_dict(), indent=2), encoding="utf-8",
    )

    # Emit telemetry — this is exactly the kind of edge case our registry
    # was designed for.
    try:
        from . import edge_cases
        if result.kind == "python":
            ec_id = (
                "EC-VAL-002" if any("mixed tabs" in e for e in result.errors)
                else "EC-VAL-001"
            )
        elif result.kind == "json":
            ec_id = "EC-VAL-003"
        else:
            ec_id = "EC-VAL-001"
        edge_cases.track(ec_id, payload={
            "file": str(final), "errors": result.errors,
        })
    except Exception:  # noqa: BLE001
        pass

    return final


def validate_tree(
    root: Path, *, exclude_dirs: tuple[str, ...] = ("quarantine", ".git"),
) -> list[ValidationResult]:
    """Validate every file under ``root`` (recursive).

    Skips directories named in exclude_dirs. Returns a list of
    ValidationResult, one per file. Caller decides what to do on
    failures (typically: quarantine + skip atomize).
    """
    results: list[ValidationResult] = []
    if not root.exists():
        return results
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        # Skip anything in an excluded subtree.
        rel_parts = p.relative_to(root).parts
        if any(part in exclude_dirs for part in rel_parts):
            continue
        results.append(validate_file(p, base=root))
    return results


def quarantine_failures(
    results: list[ValidationResult],
    *,
    cycle_dir: Path,
) -> tuple[int, int]:
    """Quarantine every file in ``results`` whose ok is False.

    Returns ``(quarantined_count, skipped_count)`` — quarantined is files
    moved, skipped is files we couldn't move (already gone, etc).
    """
    quarantined = 0
    skipped = 0
    for r in results:
        if r.ok:
            continue
        # The path inside ValidationResult is relative; reconstruct
        # against cycle_dir.
        full = cycle_dir / r.path
        if not full.exists():
            skipped += 1
            continue
        try:
            quarantine_file(full, cycle_dir=cycle_dir, result=r)
            quarantined += 1
        except OSError:
            skipped += 1
    return quarantined, skipped


__all__ = [
    "MAX_JSON_DEPTH",
    "MAX_PYTHON_FILE_LINES",
    "ValidationResult",
    "quarantine_failures",
    "quarantine_file",
    "validate_file",
    "validate_json",
    "validate_markdown",
    "validate_python_source",
    "validate_text",
    "validate_tree",
    "validate_yaml",
]
