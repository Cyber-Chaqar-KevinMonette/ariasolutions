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
