"""patcher.py — Workstream Gym #7: aria-path-scan-triage.

Status-aware path scanning. Two anchored, idempotent patches:

  1. path_scan/scanner.py::scan_repo — classifies each module via the new
     triage.py (payload file) and downgrades block findings inside
     `applied` modules to warn-severity `historical/*` kinds. The fleet
     view stops crying wolf about already-landed history; **scan_one — the
     safe_apply step-0 gate on the module actually being applied — is
     deliberately untouched** (full block semantics where it matters).
  2. path_scan/__main__.py — a `triage` subcommand printing the
     operator-facing applied/pending/unknown catalog.

An honest, documented limitation: full-file-replacement modules (payload
contains a copy of a common live file like cockpit/app.py) trivially
classify `applied` because the live path exists. The fleet view may
therefore under-warn about such a stale module — acceptable ONLY because
the apply-time gate (scan_one) keeps full strength; it is also exactly why
the dangerous stale full-file modules (aria-safe-glyphs, aria-inbox-*)
get explicit SUPERSEDED.md notes as part of this same workstream.
"""
from __future__ import annotations

MARK = "path-scan-triage-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ═══════════════════════════════════════════════════════════════════════
# scanner.py — status-aware scan_repo
# ═══════════════════════════════════════════════════════════════════════

SCAN_REPO_ANCHOR = (
    "def scan_repo(repo_root: Path | None = None) -> ScanResult:\n"
    '    """Scan every staged aria-<name>/ module under repo_root."""\n'
    "    repo = Path(repo_root) if repo_root else _default_repo_root()\n"
    "    result = ScanResult()\n"
    '    for mod_dir in sorted(repo.glob("aria-*")):\n'
    "        if not mod_dir.is_dir():\n"
    "            continue\n"
    "        result.modules_scanned += 1\n"
    "        result.files_scanned += _count_payload_files(mod_dir)\n"
    "        result.findings += scan_module(mod_dir)\n"
    "    return result\n"
)
SCAN_REPO_NEW = (
    f"def _historicize(f: Finding) -> Finding:  # {MARK}\n"
    '    """Downgrade a finding inside an already-applied module: block →\n'
    "    warn, kind prefixed historical/. The module landed; its stale\n"
    '    staged copy is provenance, not pending danger."""\n'
    '    if f.severity != "block":\n'
    "        return f\n"
    "    return Finding(\n"
    '        severity="warn", kind=f"historical/{f.kind}", module=f.module,\n'
    "        path=f.path, line=f.line,\n"
    '        message=f"[applied module] {f.message}", excerpt=f.excerpt,\n'
    "    )\n"
    "\n"
    "\n"
    "def scan_repo(repo_root: Path | None = None, *,\n"
    f"              status_aware: bool = True) -> ScanResult:  # {MARK}\n"
    '    """Scan every staged aria-<name>/ module under repo_root.\n'
    "\n"
    "    status_aware=True (default) classifies each module via triage.py and\n"
    "    downgrades blocks inside applied modules to historical/* warns.\n"
    "    scan_one (the apply-time gate) never goes through this path —\n"
    '    full block semantics are preserved where they matter."""\n'
    "    repo = Path(repo_root) if repo_root else _default_repo_root()\n"
    "    result = ScanResult()\n"
    "    index = None\n"
    "    if status_aware:\n"
    "        try:\n"
    "            from .triage import SrcIndex, classify_module\n"
    "\n"
    '            index = SrcIndex.build(repo / "src" / "sovereign_agent")\n'
    "        except Exception:  # noqa: BLE001 — triage is an enhancement, never a blocker\n"
    "            index = None\n"
    '    for mod_dir in sorted(repo.glob("aria-*")):\n'
    "        if not mod_dir.is_dir():\n"
    "            continue\n"
    "        result.modules_scanned += 1\n"
    "        result.files_scanned += _count_payload_files(mod_dir)\n"
    "        findings = scan_module(mod_dir)\n"
    "        if index is not None:\n"
    "            try:\n"
    '                if classify_module(mod_dir, index) == "applied":\n'
    "                    findings = [_historicize(f) for f in findings]\n"
    "            except Exception:  # noqa: BLE001\n"
    "                pass\n"
    "        result.findings += findings\n"
    "    return result\n"
)


def patch_scanner(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, SCAN_REPO_ANCHOR, SCAN_REPO_NEW, label="scanner scan_repo anchor")
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# __main__.py — triage subcommand
# ═══════════════════════════════════════════════════════════════════════

MAIN_ANCHOR = (
    "    result = scan_one(None, positional[0]) if positional else scan_repo(None)\n"
)
MAIN_NEW = (
    f"    if positional and positional[0] == \"triage\":  # {MARK}\n"
    "        from .scanner import _default_repo_root\n"
    "        from .triage import triage_report\n"
    "\n"
    "        report = triage_report(_default_repo_root())\n"
    "        if as_json:\n"
    "            print(json.dumps(report, indent=2))\n"
    "        else:\n"
    "            c = report[\"counts\"]\n"
    "            print(f\"triage: {c['applied']} applied · {c['pending']} pending · \"\n"
    "                  f\"{c['unknown']} unknown\")\n"
    "            for status in (\"pending\", \"unknown\"):\n"
    "                for name in report[status]:\n"
    "                    print(f\"  {status:8s} {name}\")\n"
    "        return 0\n"
    "\n"
    "    result = scan_one(None, positional[0]) if positional else scan_repo(None)\n"
)


def patch_main(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, MAIN_ANCHOR, MAIN_NEW, label="__main__ triage anchor")
    return text, True
