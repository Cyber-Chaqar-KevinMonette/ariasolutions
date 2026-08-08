"""realestate-geo patches — wire sale-date urgency into the live poll loop.

pre-foreclosure-d (Kevin, 2026-08-03). Idempotent + anchored: safe to run
twice, and it refuses to guess if the anchor it expects isn't found.
"""
from __future__ import annotations

import sys
from pathlib import Path

MARKER = "pre-foreclosure-d"

# anchor: the end of the existing real-estate buy-box gate in poll_once()
ANCHOR = """                    if not should_post:
                        report.filtered += 1
                        continue
"""

INSERT = '''
                # pre-foreclosure-d (Kevin, 2026-08-03): a county sale
                # date in the PAST is not a lead — that sale already
                # happened. Measured live 2026-08-03: 10 of the 13
                # listings the county pages were serving were for a sale
                # a week gone, so 77% of this feed was noise. The whole
                # no-capital play is reaching an owner who STILL owns
                # the house before their deadline, so the countdown is
                # the signal, not a decoration.
                #
                # Fails OPEN on an unparseable date — an undated listing
                # still reaches a human. Silently swallowing a real lead
                # is the worse failure (see the 23 verticals that read
                # "healthy" while posting nothing).
                if proj_name.startswith("scout-realestate-"):
                    from sovereign_agent.real_estate_sale_urgency import (
                        is_live_lead, label)
                    if not is_live_lead(item.text):
                        report.filtered += 1
                        report.expired_filtered += 1
                        continue
                    _urg = label(item.text)
                    re_strategy_note = (f"{_urg} · {re_strategy_note}"
                                        if re_strategy_note else _urg)
'''

# the honest counter, alongside the existing ones
FIELD_ANCHOR = "    no_signal_filtered: int = 0\n"
FIELD_INSERT = ("    # pre-foreclosure-d: county listings whose sale date "
                "already passed\n    expired_filtered: int = 0\n")

SUMMARY_ANCHOR = """        if self.no_signal_filtered:
            base += f", {self.no_signal_filtered} no-link/no-location"
"""
SUMMARY_INSERT = """        if self.expired_filtered:
            base += f", {self.expired_filtered} expired (sale date passed)"
"""


def patch_runtime(path: Path) -> str:
    text = path.read_text()
    if MARKER in text:
        return "already patched"

    for name, anchor in (("gate", ANCHOR), ("field", FIELD_ANCHOR),
                         ("summary", SUMMARY_ANCHOR)):
        if anchor not in text:
            raise ValueError(
                f"anchor '{name}' not found in {path.name} — refusing to "
                f"guess. The file changed; re-check before applying.")

    text = text.replace(FIELD_ANCHOR, FIELD_ANCHOR + FIELD_INSERT, 1)
    text = text.replace(SUMMARY_ANCHOR, SUMMARY_ANCHOR + SUMMARY_INSERT, 1)
    text = text.replace(ANCHOR, ANCHOR + INSERT, 1)
    path.write_text(text)
    return "patched"


if __name__ == "__main__":
    src = Path(sys.argv[1])
    try:
        print(f"runtime.py: {patch_runtime(src / 'discord_runtime' / 'runtime.py')}")
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
