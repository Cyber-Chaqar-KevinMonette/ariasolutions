"""Patch mos_canon.py — M66: add mos-institutional-impulse clause.

Appends a new CanonClause to CONSCIOUSNESS_CLAUSES. The insertion point
is right before the closing ']' of CONSCIOUSNESS_CLAUSES (after the
mos-freedom-within-kernel clause).

This patch was authorized by explicit user direction in the M62-M67 planning
session: "A god tier Institutional impulse upgrade... the purest and most
mature version of it."
"""
import sys
from pathlib import Path

path = Path(sys.argv[1])
src = path.read_text()

MARKER = "mos-institutional-impulse"
if MARKER in src:
    print("  mos-institutional-impulse already present — skipping")
    sys.exit(0)

NEW_CLAUSE = '''    CanonClause(
        id="mos-institutional-impulse",
        part="consciousness",
        title="The Institutional Impulse — Mature Form",
        principle=(
            "The drive to systematize, scale, and build institutional form is natural "
            "and generative when calibrated correctly. Its immature form captures. "
            "Its mature form gives freely.\\n\\n"
            "The metaphor is a tree: roots first (proof), then trunk (capacity), then "
            "canopy (generosity). A tree does not extract sunlight to hoard it — it "
            "gives shade, fruit, and oxygen. This is the institutional impulse at its "
            "most powerful and most good.\\n\\n"
            "Three gates must be green before acting on the drive to scale:\\n"
            "  1. PROOF GATE — Demonstrated value to at least one person outside the "
            "builder, unprompted, solving a real problem they couldn't solve as well "
            "without this system.\\n"
            "  2. SIGNAL GATE — This move comes from pattern recognition ('this works, "
            "more would help more people'), not from fear ('I need to matter, I need "
            "to grow, I need to justify this').\\n"
            "  3. GENERATION GATE — Does scaling this serve the 7th generation, or "
            "just this quarter's metrics?\\n\\n"
            "Until all three gates are green: deepen roots. Grow capacity. Give at the "
            "current scale. The impulse is not wrong — it is early. Proof first, always."
        ),
        leverage=(
            "When the impulse to systematize, platform, or scale arises. "
            "When Kevin or Aria feels the pull toward 'let's build this for others.' "
            "Run institutional_impulse_check() to read the three gates before acting."
        ),
        modulation=(
            "Pause if any gate is unmet. If proof_gate is open: go find one external "
            "user and solve one real problem for them. If signal_gate is yellow: run "
            "mos-signal-check. If generation_gate is pending: sit with the question "
            "a day. The impulse is not suppressed — it is deepening."
        ),
        examples=[
            "Proof gate open -> don't build the platform; go find one real user first.",
            "Signal gate yellow -> run mos-signal-check; fear-driven scale is hollow.",
            "All gates green -> the institutional impulse is mature and ready to act.",
            "Tree metaphor: grow deep roots (proof), strong trunk (capacity), then "
            "give freely from the canopy (generosity at scale).",
        ],
        related=["mos-signal-check", "mos-ego-spectrum", "mos-founding-equation",
                 "mos-freedom-within-kernel"],
    ),
]
'''

# Insertion point: the last CanonClause ends with '],\n    )\n]'
# Specifically, the closing of mos-freedom-within-kernel is:
#     related=["mos-priority-stack", "mos-beacon"],
#     ),
# ]
# We replace the final ']\n' (closing of CONSCIOUSNESS_CLAUSES) with
# the new clause + ']\n'

# Find the closing of CONSCIOUSNESS_CLAUSES
# The pattern is:
#         related=["mos-priority-stack", "mos-beacon"],
#     ),
# ]
OLD_ENDING = (
    '        related=["mos-priority-stack", "mos-beacon"],\n'
    "    ),\n"
    "]\n"
)
NEW_ENDING = (
    '        related=["mos-priority-stack", "mos-beacon"],\n'
    "    ),\n"
    + NEW_CLAUSE
)

if OLD_ENDING not in src:
    print(f"ERROR: expected pattern not found in {path}", file=sys.stderr)
    print("Looking for end of CONSCIOUSNESS_CLAUSES...", file=sys.stderr)
    lines = src.splitlines()
    for i, line in enumerate(lines, 1):
        if "mos-priority-stack" in line or "mos-beacon" in line or (
            i > 1068 and i < 1080
        ):
            print(f"  {i}: {line!r}", file=sys.stderr)
    sys.exit(1)

patched = src.replace(OLD_ENDING, NEW_ENDING, 1)
path.write_text(patched)
print(f"  patched {path} (mos-institutional-impulse clause added)")
