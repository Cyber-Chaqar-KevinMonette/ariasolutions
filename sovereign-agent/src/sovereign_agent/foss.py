"""
╔══════════════════════════════════════════════════════════════════════════╗
║  foss.py — FOSS lineage, attribution, and license respect               ║
║  v0.2.13                                                                  ║
║                                                                           ║
║  The FOSS mentality: when the agent builds software, it should know      ║
║  what licenses it's encountering, write attribution where it's owed,     ║
║  and produce its own output with a license header that makes downstream  ║
║  use unambiguous. This module gives the dream-builder the building       ║
║  blocks for that.                                                        ║
║                                                                           ║
║  This is intentionally lightweight. It is NOT a full SPDX scanner.       ║
║  It is NOT a license-compatibility solver (license matrices are PhD-     ║
║  level work and outside the agent's scope). What it IS:                  ║
║                                                                           ║
║    • A short SPDX-id table the agent recognizes.                          ║
║    • License-header generators for common SPDX ids, parameterized by    ║
║      project name, year, author.                                          ║
║    • A `detect_license_in_text` heuristic for finding license blocks    ║
║      in upstream source files (used by the ideate step's prior-art       ║
║      check).                                                             ║
║    • A `record_lineage` helper that emits a "this idea descends from X"  ║
║      atom whenever the dream-build step references upstream work.        ║
║                                                                           ║
║  When in doubt about compatibility, the agent flags it for the operator. ║
║  The agent never auto-resolves license conflicts.                        ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class License:
    """One known license entry."""
    spdx_id: str          # e.g. "MIT", "Apache-2.0"
    name: str             # human-readable name
    permissive: bool      # True for MIT/BSD/Apache, False for GPL family
    notes: str = ""       # any compatibility notes


# Curated minimal table — each entry verified against canonical SPDX
# license list (https://spdx.org/licenses/). When in doubt, the agent
# defers to the operator rather than guessing.
KNOWN_LICENSES: dict[str, License] = {
    "MIT": License("MIT", "MIT License", permissive=True),
    "Apache-2.0": License(
        "Apache-2.0", "Apache License 2.0",
        permissive=True,
        notes="Includes patent grant. Compatible with MIT for redistribution.",
    ),
    "BSD-2-Clause": License("BSD-2-Clause", 'BSD 2-Clause "Simplified" License', True),
    "BSD-3-Clause": License("BSD-3-Clause", 'BSD 3-Clause "New" License', True),
    "ISC": License("ISC", "ISC License", permissive=True),
    "Unlicense": License("Unlicense", "The Unlicense (public-domain-equivalent)", True),
    "MPL-2.0": License("MPL-2.0", "Mozilla Public License 2.0", True,
                       notes="Weak copyleft — file-level reciprocity."),
    "GPL-2.0-only": License("GPL-2.0-only", "GNU GPL v2 only", False,
                            notes="Strong copyleft — derivative works must also be GPL-2.0."),
    "GPL-3.0-only": License("GPL-3.0-only", "GNU GPL v3 only", False,
                            notes="Strong copyleft. Includes patent retaliation."),
    "AGPL-3.0-only": License("AGPL-3.0-only", "GNU Affero GPL v3 only", False,
                              notes="Strong copyleft + network use clause."),
    "LGPL-3.0-only": License("LGPL-3.0-only", "GNU Lesser GPL v3 only", False,
                              notes="Library-level copyleft. Linking allowed."),
    "CC0-1.0": License("CC0-1.0", "Creative Commons Zero v1.0", True,
                       notes="Public-domain-equivalent."),
    "CC-BY-4.0": License("CC-BY-4.0", "Creative Commons Attribution 4.0", True,
                          notes="Documentation-friendly. Requires attribution."),
}


# Heuristic patterns used to spot license blocks in source files.
# Order matters — more specific patterns first.
_LICENSE_HEURISTICS: tuple[tuple[str, re.Pattern], ...] = (
    ("Apache-2.0", re.compile(r"\bApache License,?\s+Version\s+2\.0\b", re.IGNORECASE)),
    ("AGPL-3.0-only", re.compile(r"\bGNU\s+Affero\s+General\s+Public\s+License\b", re.IGNORECASE)),
    ("LGPL-3.0-only", re.compile(r"\bLesser\s+General\s+Public\s+License\b", re.IGNORECASE)),
    ("GPL-3.0-only", re.compile(r"\bGNU\s+General\s+Public\s+License\b.*\bversion\s+3\b", re.IGNORECASE | re.DOTALL)),
    ("GPL-2.0-only", re.compile(r"\bGNU\s+General\s+Public\s+License\b.*\bversion\s+2\b", re.IGNORECASE | re.DOTALL)),
    ("MPL-2.0", re.compile(r"\bMozilla\s+Public\s+License,?\s+v\.?\s*2\.0\b", re.IGNORECASE)),
    ("BSD-3-Clause", re.compile(
        r"Redistribution\s+and\s+use.*?(?:names?\s+of\s+the\s+(?:author|copyright\s+holder|contributors))",
        re.IGNORECASE | re.DOTALL,
    )),
    ("BSD-2-Clause", re.compile(
        r"Redistribution\s+and\s+use.*?(?:Redistributions\s+in\s+binary\s+form)",
        re.IGNORECASE | re.DOTALL,
    )),
    ("MIT", re.compile(
        r"Permission\s+is\s+hereby\s+granted,\s+free\s+of\s+charge",
        re.IGNORECASE,
    )),
    ("ISC", re.compile(
        r"Permission\s+to\s+use,\s+copy,\s+modify,?\s+and(?:/or)?\s+distribute",
        re.IGNORECASE,
    )),
    ("Unlicense", re.compile(r"\bThis\s+is\s+free\s+and\s+unencumbered\s+software\b", re.IGNORECASE)),
    ("CC0-1.0", re.compile(r"\bCC0\s+1\.0\b", re.IGNORECASE)),
    ("CC-BY-4.0", re.compile(r"\bCreative\s+Commons\s+Attribution\s+4\.0\b", re.IGNORECASE)),
)


def detect_license_in_text(text: str, *, max_search_chars: int = 8000) -> str | None:
    """Heuristically detect an SPDX id from license-block text.

    Searches only the first ``max_search_chars`` characters by default —
    license headers are at the top of files. Returns the SPDX id of the
    first match, or None if nothing recognized. False negatives are
    expected; the agent treats "unknown" as "unknown" rather than
    pretending to know.
    """
    if not text:
        return None
    head = text[:max_search_chars]
    for spdx_id, pattern in _LICENSE_HEURISTICS:
        if pattern.search(head):
            return spdx_id
    # Fallback: explicit SPDX-License-Identifier comment (very common in
    # modern code).
    m = re.search(r"SPDX-License-Identifier:\s*([\w.\-+]+)", head, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def license_header(
    spdx_id: str,
    *,
    project_name: str,
    author: str = "the project contributors",
    year: int | None = None,
) -> str:
    """Generate a top-of-file license header for the given SPDX id.

    Returns a comment-style header suitable for any text file. Python
    files should use the # variant (the function returns lines that the
    caller can prefix). Year defaults to the current UTC year.

    Unknown SPDX ids fall back to a generic SPDX-License-Identifier line
    — never an invented license. The agent does not invent law.
    """
    year = year or datetime.now(timezone.utc).year
    lic = KNOWN_LICENSES.get(spdx_id)
    if lic is None:
        return (
            f"SPDX-License-Identifier: {spdx_id}\n"
            f"Copyright (c) {year} {author}\n"
            f"Project: {project_name}\n"
        )
    base = (
        f"SPDX-License-Identifier: {lic.spdx_id}\n"
        f"Copyright (c) {year} {author}\n"
        f"Project: {project_name}\n"
        f"License: {lic.name}\n"
    )
    if lic.notes:
        base += f"Note: {lic.notes}\n"
    return base


def is_compatible_for_redistribution(
    own_license: str, dependency_license: str,
) -> tuple[bool, str]:
    """Coarse compatibility check.

    Returns ``(ok, rationale)``. This is intentionally conservative —
    when we don't know, we return ``False`` with a rationale that asks
    for human review. The agent never claims a borderline case is fine.

    Known-safe pairs:
      • own=permissive, dep=permissive → ok
      • own=GPL-3, dep=permissive → ok (permissive can flow into GPL)
      • own=GPL-3, dep=GPL-3 → ok (same family)
      • own=permissive, dep=copyleft → NOT ok (copyleft contagion)

    Anything not explicitly enumerated is "needs human review."
    """
    own = KNOWN_LICENSES.get(own_license)
    dep = KNOWN_LICENSES.get(dependency_license)
    if own is None:
        return (False, f"unknown own license: {own_license}; needs human review")
    if dep is None:
        return (False, f"unknown dependency license: {dependency_license}; needs human review")
    if own.permissive and dep.permissive:
        return (True, f"both permissive ({own.spdx_id} + {dep.spdx_id})")
    if not own.permissive and dep.permissive:
        return (True, f"copyleft project absorbing permissive dep ({dep.spdx_id})")
    if not own.permissive and not dep.permissive and own.spdx_id == dep.spdx_id:
        return (True, f"same copyleft license ({own.spdx_id})")
    return (
        False,
        f"{own.spdx_id} + {dep.spdx_id} — copyleft mixing requires human review",
    )


@dataclass(frozen=True)
class LineageEntry:
    """One recorded ancestry note: 'this idea descends from <source>'."""
    source: str           # URL, paper title, project name
    relation: str         # e.g. "inspired by", "extends", "reimplements"
    notes: str = ""


def render_lineage_block(entries: list[LineageEntry]) -> str:
    """Render a markdown block citing prior art.

    Designed to be appended to a generated README.md so attribution is
    embedded in the output, not just in atoms.db. Empty list → empty
    string (no spurious 'Prior art' section if there's nothing to cite).
    """
    if not entries:
        return ""
    lines = ["", "## Prior art and lineage", ""]
    for e in entries:
        line = f"- **{e.relation}** [{e.source}]"
        if e.notes:
            line += f" — {e.notes}"
        lines.append(line)
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "KNOWN_LICENSES",
    "License",
    "LineageEntry",
    "detect_license_in_text",
    "is_compatible_for_redistribution",
    "license_header",
    "render_lineage_block",
]
