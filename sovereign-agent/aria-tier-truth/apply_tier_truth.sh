#!/usr/bin/env bash
# apply_tier_truth.sh — make authority tiers and autonomy-duration trust tiers unambiguous.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$REPO/aria-tier-truth"

if pgrep -f '(^|[[:space:]])(sov|sovereign)[[:space:]]+cockpit([[:space:]]|$)' >/dev/null; then
    echo "Refusing to apply while the Sovereign cockpit is running. Stop it, review this module, then retry." >&2
    exit 1
fi

cp "$STAGE/payload/src/sovereign_agent/tools/mode_tools.py" \
   "$REPO/src/sovereign_agent/tools/mode_tools.py"

REPO="$REPO" python3 - <<'PYEOF'
import os
import sys
from pathlib import Path

repo = Path(os.environ["REPO"])
loop = repo / "src/sovereign_agent/loop.py"
src = loop.read_text()

replacements = [
    (
        "Tier ceiling: {tier_ceiling}. Tools above this tier are not in your tool\nlist and cannot be invoked. The matrix is not advisory — it is enforced at\ndispatch.",
        "Authority-tool ceiling: {tier_ceiling}. Tools above this authority tier are not in your\ntool list and cannot be invoked. The matrix is not advisory — it is enforced at\ndispatch. This is separate from the autonomy-duration trust tier: a valid trust\ntier extends only a timed session's duration; it never increases this tool ceiling.",
    ),
    (
        "  Tier 1 (default): max 1hr  |  Tier 2: max 2hr  |  Tier 3: max 4hr  |  Tier 4: max 8hr",
        "  Autonomy-duration trust tier 1 (default): max 1hr  |  Tier 2: max 2hr  |  Tier 3: max 4hr  |  Tier 4: max 12hr",
    ),
    (
        "Autonomous switches: BUSY↔TIMED only (both have Tier 3 ceiling in practice,\nbut BUSY is where you drain background work silently).",
        "Autonomous switches: BUSY↔TIMED only. BUSY has an authority-tool ceiling of Tier 1;\nTIMED has a ceiling of Tier 3. Report these as authority ceilings, never as the\nseparate autonomy-duration trust tier.",
    ),
]
for old, new in replacements:
    if new in src:
        continue
    if old not in src:
        print(f"Anchor missing: {old[:70]!r}", file=sys.stderr)
        raise SystemExit(1)
    src = src.replace(old, new, 1)
loop.write_text(src)
PYEOF

cp "$STAGE/tests/test_tier_truth.py" "$REPO/tests/test_tier_truth.py"
echo "Applied aria-tier-truth. Verify with: .venv/bin/python -m pytest tests/test_tier_truth.py tests/test_mode_master.py -q"
