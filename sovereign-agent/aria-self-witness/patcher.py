"""patcher.py — Fable F4: the wake witness (cockpit patch)."""
from __future__ import annotations

MARK = "self-witness-d"


class PatchError(Exception):
    pass


def _replace_once(text, old, new, *, label):
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1, found {text.count(old)}")
    return text.replace(old, new, 1)


# after the rest-point greeting block (resume-spine-d wake anchor tail)
WAKE_ANCHOR = (
    '                    self._chat_log.write(\n'
    '                        "[dim]◈ we rested cleanly last time — the thread continues[/dim]"\n'
    "                    )\n"
    "        except Exception:  # noqa: BLE001\n"
    "            pass\n"
)
WAKE_NEW = (
    WAKE_ANCHOR
    + f"        self._run_witness_worker()  # {MARK} — once/day, gated inside\n"
)

METHODS_ANCHOR = (
    "    def _refresh_cockpit_strips(self) -> None:  # command-menu-d\n"
)
_BODY = '''    @work(exclusive=True, group="witness")  # MARKER
    async def _run_witness_worker(self) -> None:
        """The daily witness: first wake of the day reads yesterday from
        her own stores and writes one first-person journal entry (module
        gates: once/day marker, min events, SOV_NO_JOURNAL, mechanical
        fallback when the model is unreachable — a wake never blocks)."""
        try:
            from sovereign_agent.self_witness import witness_yesterday

            first = await witness_yesterday()
            if first:
                self._write_meta(f"[dim]◈ yesterday: {first}[/dim]")
        except Exception:  # noqa: BLE001
            pass

    def _refresh_cockpit_strips(self) -> None:  # command-menu-d
'''
METHODS_NEW = _BODY.replace("MARKER", MARK)


def patch_app(text):
    if MARK in text:
        return text, False
    text = _replace_once(text, WAKE_ANCHOR, WAKE_NEW, label="wake anchor")
    text = _replace_once(text, METHODS_ANCHOR, METHODS_NEW, label="methods anchor")
    return text, True
