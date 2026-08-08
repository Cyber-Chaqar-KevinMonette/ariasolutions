#!/usr/bin/env bash
# apply_src_hygiene.sh — Stage M87: quarantine stray *.bak files out of src/
#
# What this does:
#   Moves every *.bak* file under src/ into aria-src-hygiene/quarantine/,
#   preserving the relative path, and writes a manifest for exact reversal.
#   These backup files clutter the source tree, can confuse tooling/search,
#   and bloat the installed package. NONE are sealed/charter files (verified:
#   no SIGNAL.md/charter backups present).
#
#   This is a MOVE, never a delete — fully reversible via restore_src_hygiene.sh.
#
# Prerequisites: cockpit must NOT be running. Run from repo root.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

STAGING="$REPO_ROOT/aria-src-hygiene"
QUARANTINE="$STAGING/quarantine"
MANIFEST="$STAGING/manifest.txt"
VENV_PY="$REPO_ROOT/.venv/bin/python"

echo "=== M87 src/ Hygiene — quarantine .bak files ==="
echo "Repo root  : $REPO_ROOT"
echo "Quarantine : $QUARANTINE"
echo ""

if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then
    echo "ERROR: sovereign cockpit is running. Stop it first, then re-run."
    exit 1
fi

# Safety guard: refuse to move any backup of a sealed/charter file.
if find src -name "*.bak*" -type f | grep -iE "signal|charter" > /dev/null 2>&1; then
    echo "ERROR: a sealed/charter-file backup was found under src/. Aborting — review manually."
    exit 1
fi

mkdir -p "$QUARANTINE"
: > "$MANIFEST"

count=0
while IFS= read -r f; do
    rel="${f#src/}"
    dest="$QUARANTINE/$rel"
    mkdir -p "$(dirname "$dest")"
    mv "$f" "$dest"
    echo "$f" >> "$MANIFEST"
    count=$((count + 1))
done < <(find src -name "*.bak*" -type f | sort)

echo "Moved $count .bak file(s) into quarantine."
echo "Manifest written → $MANIFEST"

# ── Write the reversal script ─────────────────────────────────────────────────
cat > "$STAGING/restore_src_hygiene.sh" <<'RESTORE'
#!/usr/bin/env bash
# restore_src_hygiene.sh — move quarantined .bak files back into src/ exactly.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-src-hygiene"
while IFS= read -r orig; do
    rel="${orig#src/}"
    src_file="$STAGING/quarantine/$rel"
    if [[ -f "$src_file" ]]; then
        mkdir -p "$(dirname "$orig")"
        mv "$src_file" "$orig"
        echo "restored $orig"
    fi
done < "$STAGING/manifest.txt"
echo "Restore complete."
RESTORE
chmod +x "$STAGING/restore_src_hygiene.sh"
echo "Reversal script written → $STAGING/restore_src_hygiene.sh"

echo ""
echo "Running src hygiene test..."
"$VENV_PY" -m pytest aria-src-hygiene/tests/test_src_hygiene.py -v

echo ""
echo "=== M87 src/ Hygiene applied successfully ==="
echo "src/ now holds zero .bak files. Reverse anytime with restore_src_hygiene.sh."
