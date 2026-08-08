"""Flip RISK-004, RISK-008, RISK-011 from OPEN → MITIGATING in the risk register.

Idempotent: checks each entry before modifying.
Appends a changelog comment after each flipped status line.
"""
import sys
from pathlib import Path
from datetime import date

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
today = date.today().isoformat()

TARGETS = [
    {
        "id": "RISK-004",
        "old": "`Category: Product/Validation · Confidence: Observed · Status: OPEN · Owner: Kevin`",
        "new": "`Category: Product/Validation · Confidence: Observed · Status: MITIGATING · Owner: Kevin`",
    },
    {
        "id": "RISK-008",
        "old": "`Category: Ops · Confidence: Flagged · Status: OPEN · Owner: Kevin+Claude`",
        "new": "`Category: Ops · Confidence: Flagged · Status: MITIGATING · Owner: Kevin+Claude`",
    },
    {
        "id": "RISK-011",
        "old": "`Category: Collaborator · Confidence: Observed · Status: OPEN · Owner: Kevin+Claude`",
        "new": "`Category: Collaborator · Confidence: Observed · Status: MITIGATING · Owner: Kevin+Claude`",
    },
]

changed = []
for t in TARGETS:
    if t["old"] in text:
        text = text.replace(t["old"], t["new"])
        changed.append(t["id"])
        print(f"  ✓ {t['id']}: OPEN → MITIGATING")
    elif t["new"] in text:
        print(f"  ✓ {t['id']}: already MITIGATING (skipped)")
    else:
        print(f"  ⚠ {t['id']}: status line not found — check format", file=sys.stderr)

if changed:
    # Append changelog at end of file
    changelog_line = (
        f"\n---\n"
        f"<!-- M57 {today}: {', '.join(changed)} flipped OPEN → MITIGATING "
        f"(eval-crown M49, atoms-compact M54, session-briefs M48 deployed) -->\n"
    )
    text += changelog_line
    path.write_text(text, encoding="utf-8")
    print(f"  Changelog appended for {len(changed)} updated entries.")
else:
    print("  No changes made.")
