#!/usr/bin/env bash
# apply_apply_menu_autoupdate.sh — Stage M85: Apply Dashboard auto-discovery
#
# What this applies:
#   1. src/sovereign_agent/cockpit/apply_screen.py (patched in-place)
#      - _extract_script_info(): parse label + description from apply script headers
#      - _is_applied(): checks backups/ dir first (reliable), then test file fallback
#      - discover_scripts(): returns label + description in each entry
#      - compose() + _select(): use auto-extracted label when not in _CATALOG
#
# Effect: any new aria-<name>/ staging module auto-appears with a meaningful
# label in the Apply Dashboard — no _CATALOG entry required.
#
# Reversibility: apply_screen.py backed up to aria-apply-menu-autoupdate/backups/
# Prerequisites: cockpit must NOT be running. Run from repo root.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-apply-menu-autoupdate"
BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TARGET="$REPO_ROOT/src/sovereign_agent/cockpit/apply_screen.py"

echo "=== M85 Apply Dashboard Auto-Discovery ==="
echo "Repo root : $REPO_ROOT"
echo "Backup dir: $BACKUP_DIR"
echo ""

# ── Guards ────────────────────────────────────────────────────────────────────

if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then
    echo "ERROR: sovereign cockpit is running. Stop it first, then re-run."
    exit 1
fi

if [[ ! -f "$VENV_PY" ]]; then
    echo "ERROR: .venv/bin/python not found."
    exit 1
fi

if [[ ! -f "$TARGET" ]]; then
    echo "ERROR: apply_screen.py not found at $TARGET (M81 must be applied first)"
    exit 1
fi

# ── Backup ────────────────────────────────────────────────────────────────────

mkdir -p "$BACKUP_DIR"
cp "$TARGET" "$BACKUP_DIR/apply_screen.py.bak"
echo "Backed up apply_screen.py → $BACKUP_DIR"

# ── Patch via Python ──────────────────────────────────────────────────────────

"$VENV_PY" - "$TARGET" <<'PYEOF'
import sys, re
from pathlib import Path

target = Path(sys.argv[1])
text = target.read_text()

GUARD = "# apply-menu-autoupdate-d"

if GUARD in text:
    print("SKIP: apply_screen.py patch already applied")
    sys.exit(0)

# ── Replace _is_applied() ─────────────────────────────────────────────────────
OLD_IS_APPLIED = '''\
def _is_applied(repo_root: Path, name: str) -> bool:
    """Heuristic: applied iff tests/test_{slug}.py exists."""
    slug = name.removeprefix("aria-").replace("-", "_")
    return (repo_root / "tests" / f"test_{slug}.py").exists()'''

NEW_IS_APPLIED = '''\
def _extract_script_info(script: Path) -> tuple[str, str]:
    """Parse (label, description) from an apply script's first header comment.  # apply-menu-autoupdate-d

    Expects a line like:
      # apply_foo.sh — Stage M99: Title here
      # apply_foo.sh — Apply M99: Title here
    Returns ("M99 · Title here", "Title here") if pattern matches,
    or (folder_name, "") as fallback.
    """
    try:
        for line in script.read_text().splitlines()[:10]:
            line = line.strip()
            if line.startswith("#") and not line.startswith("#!"):
                content = line.lstrip("#").strip()
                if "—" in content:
                    _, after = content.split("—", 1)
                    after = after.strip()
                    m = re.match(r"(?:Stage|Apply)\\s+(M\\d+):\\s*(.+)", after)
                    if m:
                        mnum, title = m.group(1), m.group(2).strip()
                        return f"{mnum} \\u00b7 {title}", title
                    return after, after
    except Exception:
        pass
    return script.parent.name, ""


def _is_applied(repo_root: Path, name: str) -> bool:
    """Heuristic: applied if backups/ dir exists (created by apply script) or test file exists."""
    if (repo_root / name / "backups").exists():
        return True
    slug = name.removeprefix("aria-").replace("-", "_")
    return (repo_root / "tests" / f"test_{slug}.py").exists()'''

if OLD_IS_APPLIED not in text:
    print("ERROR: _is_applied() body not found — apply_screen.py may have drifted", file=sys.stderr)
    sys.exit(1)

text = text.replace(OLD_IS_APPLIED, NEW_IS_APPLIED, 1)
print("Replaced _is_applied() and added _extract_script_info()")

# ── Replace discover_scripts() ────────────────────────────────────────────────
OLD_DISCOVER = '''\
def discover_scripts(repo_root: Path) -> list[dict]:
    """Return sorted list of {name, script, applied} for all staging modules."""
    results = []
    for script in sorted(repo_root.glob("aria-*/apply_*.sh")):
        module_name = script.parent.name
        results.append({
            "name": module_name,
            "script": str(script),
            "applied": _is_applied(repo_root, module_name),
        })
    return results'''

NEW_DISCOVER = '''\
def discover_scripts(repo_root: Path) -> list[dict]:
    """Return sorted list of {name, script, applied, label, description} for all staging modules."""
    results = []
    for script in sorted(repo_root.glob("aria-*/apply_*.sh")):
        module_name = script.parent.name
        label, description = _extract_script_info(script)
        results.append({
            "name": module_name,
            "script": str(script),
            "applied": _is_applied(repo_root, module_name),
            "label": label,
            "description": description,
        })
    return results'''

if OLD_DISCOVER not in text:
    print("ERROR: discover_scripts() body not found", file=sys.stderr)
    sys.exit(1)

text = text.replace(OLD_DISCOVER, NEW_DISCOVER, 1)
print("Replaced discover_scripts() to include label + description")

# ── Add `import re` if missing ────────────────────────────────────────────────
if "import re" not in text:
    text = text.replace("import subprocess\n", "import re\nimport subprocess\n", 1)
    print("Added `import re`")
else:
    print("SKIP: `import re` already present")

# ── Update compose() label fallbacks (pending list) ───────────────────────────
OLD_PENDING_LABEL = '''\
                            info = _CATALOG.get(s["name"])
                            btn_label = info.label if info else s["name"]
                            yield Button(
                                f"\\u25cb  {btn_label}",
                                id=safe_id,
                                name=s["name"],
                                classes="script-btn pending-btn",
                            )'''

NEW_PENDING_LABEL = '''\
                            info = _CATALOG.get(s["name"])
                            btn_label = info.label if info else s.get("label") or s["name"]
                            yield Button(
                                f"\\u25cb  {btn_label}",
                                id=safe_id,
                                name=s["name"],
                                classes="script-btn pending-btn",
                            )'''

if OLD_PENDING_LABEL in text:
    text = text.replace(OLD_PENDING_LABEL, NEW_PENDING_LABEL, 1)
    print("Updated pending button label fallback")
else:
    print("WARNING: pending button label pattern not matched — skipping (may already be updated)")

# ── Update compose() label fallbacks (applied list) ───────────────────────────
OLD_APPLIED_LABEL = '''\
                            info = _CATALOG.get(s["name"])
                            btn_label = info.label if info else s["name"]
                            yield Button(
                                f"\\u2713  {btn_label}",
                                id=safe_id,
                                name=s["name"],
                                classes="script-btn applied-btn",
                            )'''

NEW_APPLIED_LABEL = '''\
                            info = _CATALOG.get(s["name"])
                            btn_label = info.label if info else s.get("label") or s["name"]
                            yield Button(
                                f"\\u2713  {btn_label}",
                                id=safe_id,
                                name=s["name"],
                                classes="script-btn applied-btn",
                            )'''

if OLD_APPLIED_LABEL in text:
    text = text.replace(OLD_APPLIED_LABEL, NEW_APPLIED_LABEL, 1)
    print("Updated applied button label fallback")
else:
    print("WARNING: applied button label pattern not matched — skipping (may already be updated)")

# ── Update catalog view: show auto-extracted description for uncatalogued modules ─
OLD_CATALOG_FALLBACK = '''\
                    else:
                        yield Static(
                            "  [dim]No catalog entry — see the apply script for details.[/dim]",
                            classes="catalog-desc",
                        )'''

NEW_CATALOG_FALLBACK = '''\
                    else:
                        _auto_desc = s.get("description") or ""
                        _fallback = (
                            f"  [dim]{_auto_desc}[/dim]"
                            if _auto_desc
                            else "  [dim]No catalog entry — see the apply script for details.[/dim]"
                        )
                        yield Static(_fallback, classes="catalog-desc")'''

if OLD_CATALOG_FALLBACK in text:
    text = text.replace(OLD_CATALOG_FALLBACK, NEW_CATALOG_FALLBACK, 1)
    print("Updated catalog fallback description")
else:
    print("WARNING: catalog fallback pattern not matched — skipping")

# ── Update _select() label fallback ───────────────────────────────────────────
OLD_SELECT_LABEL = '''\
        info = _CATALOG.get(name)
        run_btn = self.query_one("#apply-run", Button)
        run_btn.disabled = False
        label = info.label if info else name'''

NEW_SELECT_LABEL = '''\
        info = _CATALOG.get(name)
        run_btn = self.query_one("#apply-run", Button)
        run_btn.disabled = False
        label = info.label if info else (entry.get("label") or name)'''

if OLD_SELECT_LABEL in text:
    text = text.replace(OLD_SELECT_LABEL, NEW_SELECT_LABEL, 1)
    print("Updated _select() label fallback")
else:
    print("WARNING: _select() label pattern not matched — skipping")

# ── Update catalog view loop to have access to `s` ───────────────────────────
# The catalog loop already iterates `for s in scripts:` and uses s["name"] and s["applied"]
# We just need to make sure it also has access to s.get("label") and s.get("description")
# Check that `label = info.label if info else name` is now `label = info.label if info else s.get("label") or name`
OLD_CATALOG_LABEL = '''\
                    label = info.label if info else name'''
NEW_CATALOG_LABEL = '''\
                    label = info.label if info else s.get("label") or name'''

if OLD_CATALOG_LABEL in text:
    text = text.replace(OLD_CATALOG_LABEL, NEW_CATALOG_LABEL, 1)
    print("Updated catalog module header label fallback")
else:
    print("WARNING: catalog module header label pattern not matched — skipping")

target.write_text(text)
print(f"\nWrote patched apply_screen.py → {target}")
PYEOF

# ── Compile check ─────────────────────────────────────────────────────────────

echo ""
echo "→ Compile check..."
"$VENV_PY" -m py_compile "$TARGET"
echo "  ✓ apply_screen.py compiles cleanly"

# ── Tests ─────────────────────────────────────────────────────────────────────

echo ""
echo "Running apply menu auto-update tests..."
"$VENV_PY" -m pytest aria-apply-menu-autoupdate/tests/test_apply_menu_autoupdate.py -v

echo ""
echo "=== M85 Apply Dashboard Auto-Discovery applied successfully ==="
echo "Restart sovereign cockpit. New aria-<name>/ modules now auto-appear with labels."
