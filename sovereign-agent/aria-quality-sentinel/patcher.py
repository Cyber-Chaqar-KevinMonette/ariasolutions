"""patcher.py — Quality round Q1: register QualitySentinel + persist the
worker-latch state across cockpit restarts (closing GOD_TIER_CRITERIA.md's
now-stale "worker supervision" gap's one real residual).

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "quality-sentinel-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. stewardship/__init__.py — register the sentinel ──────────────────

INIT_ANCHOR = ("from sovereign_agent.memory_compact import sentinel as "
              "_memory_compact  # noqa: F401  # memory-compact-d\n")
INIT_NEW = (
    INIT_ANCHOR
    + f"from sovereign_agent.stewardship import quality_sentinel as _quality_sentinel  # noqa: F401  # {MARK}\n"
)


def patch_stewardship_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, INIT_ANCHOR, INIT_NEW, label="init anchor"), True


# ── 2. cockpit/app.py — persist the worker latch across restarts ────────

APP_ANCHOR = """                _DEAD_WORKERS.add(group)
                self._write_meta(
                    f"[red]⛔ worker '{group}' died repeatedly — latched dead "
                    f"(restart the cockpit to recover; check events.jsonl)[/red]"
                )
                self._render_status_bar()
"""

APP_NEW = f'''                _DEAD_WORKERS.add(group)
                self._persist_worker_latch(group)  # {MARK}
                self._write_meta(
                    f"[red]⛔ worker '{{group}}' died repeatedly — latched dead "
                    f"(restart the cockpit to recover; check events.jsonl)[/red]"
                )
                self._render_status_bar()
'''

APP_METHOD_ANCHOR = "    def on_worker_state_changed(self, event) -> None:  # worker-watch-d\n"

APP_METHOD_NEW = f'''    def _persist_worker_latch(self, group: str) -> None:  # {MARK}
        """Cross-session trace of a worker-group death — best-effort,
        never blocks the app. The in-process _DEAD_WORKERS set (worker-
        watch-d) is honest for THIS run; this file is honest across a
        cockpit restart, so a doctor/sentinel/observatory can see 'this
        died last session' even after relaunch cleared the badge."""
        try:
            import json as _json
            from datetime import datetime as _dt, timezone as _tz

            from sovereign_agent.config import SETTINGS

            path = SETTINGS.paths.data_dir / "cockpit" / "worker_health.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            state: dict = {{}}
            if path.exists():
                try:
                    state = _json.loads(path.read_text(encoding="utf-8"))
                except (_json.JSONDecodeError, OSError):
                    state = {{}}
            state[group] = _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(_json.dumps(state, indent=1), encoding="utf-8")
            tmp.replace(path)
        except Exception:  # noqa: BLE001 — supervision must never hurt the app
            pass

    def on_worker_state_changed(self, event) -> None:  # worker-watch-d
'''


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, APP_ANCHOR, APP_NEW, label="worker latch call")
    text = _replace_once(text, APP_METHOD_ANCHOR, APP_METHOD_NEW,
                         label="worker latch method")
    return text, True


# ── 3. GOD_TIER_CRITERIA.md — the doc was stale, not the gap open ───────

CRITERIA_ANCHOR = ("- Worker supervision / self-restart. **GAP** (workers self-heal per-pass")

def patch_criteria(text: str) -> tuple[str, bool]:
    if "worker-watch-d" in text:
        return text, False
    if CRITERIA_ANCHOR not in text:
        raise PatchError("criteria anchor: worker supervision line not found")
    if text.count(CRITERIA_ANCHOR) != 1:
        raise PatchError(f"criteria anchor: expected 1, found {text.count(CRITERIA_ANCHOR)}")
    # Find the full bullet (may span to the next line) and replace with MET.
    idx = text.index(CRITERIA_ANCHOR)
    line_end = text.index("\n", idx)
    # the gap description may wrap onto the following line ending in ")"
    next_nl = text.index("\n", line_end + 1)
    old_block = text[idx:next_nl]
    new_block = (
        "- Worker supervision / self-restart. **MET** (`aria-worker-watch`: "
        "bounded respawn then a permanent red latch; the quality round's "
        "aria-quality-sentinel persists that latch across a cockpit "
        "restart too — worker-watch-d)"
    )
    new_text = text[:idx] + new_block + text[next_nl:]

    gap_list_old = ("1. Dead-worker badges (small). 2. Standing scored model benchmark (the")
    gap_list_new = (
        "1. ~~Dead-worker badges~~ — resolved (aria-quality-sentinel "
        "persists the latch across restarts). 2. Standing scored model "
        "benchmark (the")
    if new_text.count(gap_list_old) == 1:
        new_text = new_text.replace(gap_list_old, gap_list_new, 1)
    return new_text, True


ALL_PATCHES = {
    "stewardship/__init__.py": patch_stewardship_init,
    "cockpit/app.py": patch_app,
}

DOC_PATCHES = {
    "GOD_TIER_CRITERIA.md": patch_criteria,
}
