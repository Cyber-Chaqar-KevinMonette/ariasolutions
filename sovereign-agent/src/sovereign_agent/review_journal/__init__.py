"""review_journal — every work session leaves a reviewable trail.

Final-sprint Round A (auto mode / transparency). Kevin's ask, verbatim:
"Everything she does in auto mode she should create a directory ... for
claude review. So everything she does she can tell you how to review it
later, or any AIs, or Human teams alike. She can work, and then tell us
what she did, how she did it, and how to inspect all of it."

For EVERY work session (auto AND manual `/work`), this writes a
self-contained review directory:

    <data>/reviews/<session_id>/
        README.md          — what she did, how she did it, how to inspect it
        plan.json          — the subtask plan + final statuses (machine)
        actions.jsonl      — every recorded action (file/command/event), ts'd
        how-to-verify.md    — concrete steps to check the work
    <data>/reviews/INDEX.md — a running, indexed list of every session

It is composed from data that already exists (SessionState via
SessionStore, and events.jsonl) — it does not duplicate storage, it
curates a human/AI-readable front door over it. Pure functions render the
text; a thin `build_review()` does the file I/O so the renderers stay
trivially testable. Accepts either a real SessionState dataclass or a
plain dict (duck-typed), so the staged module needs no hard import of
agent_session.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = [
    "build_review",
    "render_readme",
    "render_how_to_verify",
    "render_plan",
    "collect_actions",
    "update_index",
    "list_reviews",
    "reviews_root",
    "compose_recap",
]

# Event flags that represent a concrete ACTION worth surfacing in the trail.
_ACTION_HINTS = ("work-", "tool-", "file-", "write", "edit", "command", "cmd",
                 "session-", "subtask-", "scope-review")


def _safe_session_id(sid: Any) -> str:
    """Defense-in-depth: a session id is used as a directory name, so it must
    never contain path separators or `..` (which could escape reviews/).
    Real session ids from `_new_id()` are already safe; this guards against a
    malformed/hostile one, mirroring SessionStore's own path-separator refusal.
    Any unsafe character is replaced with '_'; a leading dot is neutralized."""
    s = str(sid) if sid is not None else "unknown"
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in s)
    safe = safe.replace("..", "__").lstrip(".")
    return safe or "unknown"


def _get(state: Any, field: str, default: Any = None) -> Any:
    """Read a field from a SessionState dataclass OR a dict, uniformly."""
    if isinstance(state, dict):
        return state.get(field, default)
    return getattr(state, field, default)


def _subtasks(state: Any) -> list[dict[str, Any]]:
    raw = _get(state, "subtasks", []) or []
    out: list[dict[str, Any]] = []
    for s in raw:
        out.append({
            "id": _get(s, "id", ""),
            "description": _get(s, "description", ""),
            "status": _get(s, "status", ""),
            "required_tier": _get(s, "required_tier", 1),
            "result_summary": _get(s, "result_summary", ""),
            "trace_id": _get(s, "trace_id", None),
            "error": _get(s, "error", None),
        })
    return out


def reviews_root(data_dir: Path) -> Path:
    return Path(data_dir) / "reviews"


# ── renderers (pure) ─────────────────────────────────────────────────────
def render_plan(state: Any) -> dict[str, Any]:
    subs = _subtasks(state)
    done = sum(1 for s in subs if s["status"] in ("done", "skipped"))
    return {
        "session_id": _get(state, "session_id", ""),
        "goal": _get(state, "goal", ""),
        "mode": _get(state, "mode", ""),
        "status": _get(state, "status", ""),
        "created_at": _get(state, "created_at", ""),
        "updated_at": _get(state, "updated_at", ""),
        "subtasks_total": len(subs),
        "subtasks_done": done,
        "pause_reason": _get(state, "pause_reason", None),
        "last_error": _get(state, "last_error", None),
        "subtasks": subs,
    }


def render_readme(
    state: Any, actions: list[dict[str, Any]],
    *, sentinel_warnings: list[Any] | None = None,
) -> str:
    plan = render_plan(state)
    subs = plan["subtasks"]
    lines: list[str] = []
    lines.append(f"# Review — session `{plan['session_id']}`")
    lines.append("")
    lines.append(f"> {plan['goal']}")
    lines.append("")
    lines.append(f"- **Status:** {plan['status']}"
                 + (f" ({plan['pause_reason']})" if plan['pause_reason'] else ""))
    lines.append(f"- **Mode:** {plan['mode']}")
    lines.append(f"- **Started:** {plan['created_at']}  ·  **Updated:** {plan['updated_at']}")
    lines.append(f"- **Progress:** {plan['subtasks_done']}/{plan['subtasks_total']} subtasks")
    if plan["last_error"]:
        lines.append(f"- **Error:** {plan['last_error']}")
    lines.append("")

    lines.append("## What she did")
    if not subs:
        lines.append("_No subtasks recorded._")
    for i, s in enumerate(subs, 1):
        mark = {"done": "✓", "skipped": "–", "blocked": "✗",
                "awaiting_approval": "⏸"}.get(s["status"], "·")
        lines.append(f"{i}. {mark} **{s['description']}**  "
                     f"_(tier {s['required_tier']}, {s['status']})_")
        if s["result_summary"]:
            lines.append(f"   - {s['result_summary']}")
        if s["error"]:
            lines.append(f"   - ⚠ {s['error']}")
    lines.append("")

    lines.append("## How she did it")
    lines.append(f"- {len(actions)} recorded action(s) — see `actions.jsonl` for the "
                 "full, timestamped trace (each links back to its event `trace_id`).")
    if actions:
        lines.append("- Most recent actions:")
        for a in actions[-8:]:
            lines.append(f"  - `{a.get('ts', '')}` {a.get('flag', '?')}")
    lines.append("")

    # gaps-and-hardening-d (Kevin, 2026-07-25): "Documents for review teams
    # about everything that occurred during that run... attack surfaces if
    # any was revealed... gaps, things that could use more focus and or
    # hardening." Reuses sentinel-warnings-detail-d's shared helper (Phase
    # 1) so this list can never drift from what self-report/doctor say.
    lines.append("## Gaps & hardening (sentinel state at session end)")
    if sentinel_warnings:
        for h in sentinel_warnings:
            level = getattr(h, "level", "?")
            sid = getattr(h, "sentinel_id", "?")
            summary = getattr(h, "summary", "")
            lines.append(f"- ⚠ **{sid}** ({level}) — {summary}")
    else:
        lines.append("- No sentinel warnings at session end.")
    lines.append("")

    # unverified-claims-section-d — an independent honesty check next
    # to the sentinel warnings: does a subtask's own result_summary
    # claim verification its own trace never performed? Best-effort;
    # a missing/broken module must never break the review itself.
    try:
        from sovereign_agent.unverified_claims import render_unverified_claims_section
        lines.append(render_unverified_claims_section(subs, actions))
    except Exception:  # noqa: BLE001
        pass

    lines.append("## How to inspect it")
    lines.append("- `plan.json` — the machine-readable plan + final statuses.")
    lines.append("- `actions.jsonl` — every action, in order, with trace ids.")
    lines.append("- `how-to-verify.md` — concrete steps to check this work.")
    lines.append("- Reviewers (Claude / any AI / a human team): start here, then "
                 "`how-to-verify.md`. The parent `INDEX.md` lists every session.")
    lines.append("")
    return "\n".join(lines)


def render_how_to_verify(state: Any) -> str:
    plan = render_plan(state)
    lines = [
        f"# How to verify — session `{plan['session_id']}`",
        "",
        "Concrete steps a reviewer can run to check this work:",
        "",
        "1. **See what changed on disk** (if this session wrote code/files):",
        "   ```bash",
        "   git -C <repo> status --short",
        "   git -C <repo> diff HEAD~1   # or the range covering this session",
        "   ```",
        "2. **Replay the action trace** — read `actions.jsonl` in this folder; "
        "each line has a `trace_id` you can grep in the event log:",
        "   ```bash",
        "   grep <trace_id> <data>/events/events-*.jsonl",
        "   ```",
        "3. **Re-run the affected tests** — if the work touched `src/`, run the "
        "test file(s) covering it (targeted, not the whole suite):",
        "   ```bash",
        "   .venv/bin/python -m pytest tests/test_<area>.py -q",
        "   ```",
        "4. **Check the gates still pass** — the floor + smoke gates are the "
        "standing readiness check:",
        "   ```bash",
        "   ./scripts/floor_check.sh",
        "   ```",
        "",
        f"Final status was **{plan['status']}** with "
        f"{plan['subtasks_done']}/{plan['subtasks_total']} subtasks complete.",
    ]
    if plan["last_error"]:
        lines += ["", f"⚠ This session ended with an error: `{plan['last_error']}` — "
                  "inspect the last action in `actions.jsonl` first."]
    return "\n".join(lines)


def collect_actions(
    session_state: Any, events_records: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Filter a list of event records down to this session's actions.

    Matches on (a) any subtask trace_id, or (b) the session_id appearing in
    the record's trace_id/payload, or (c) an action-shaped flag. Best-effort
    and defensive: a malformed record is skipped, never fatal.
    """
    if not events_records:
        return []
    session_id = _get(session_state, "session_id", "")
    trace_ids = {s["trace_id"] for s in _subtasks(session_state) if s["trace_id"]}
    out: list[dict[str, Any]] = []
    for rec in events_records:
        if not isinstance(rec, dict):
            continue
        tid = str(rec.get("trace_id", ""))
        flag = str(rec.get("flag", ""))
        payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
        matched = (
            (tid and tid in trace_ids)
            or (session_id and session_id in tid)
            or (session_id and session_id in json.dumps(payload, default=str))
            or any(h in flag for h in _ACTION_HINTS)
        )
        if not matched:
            continue
        out.append({
            "ts": rec.get("ts") or rec.get("time") or "",
            "flag": flag,
            "trace_id": tid,
            "plane": rec.get("plane", ""),
            "payload": payload,
        })
    return out


# ── file I/O (thin) ──────────────────────────────────────────────────────
def update_index(data_dir: Path, state: Any) -> Path:
    """Append/refresh this session's line in reviews/INDEX.md (idempotent
    by session id — an existing line for the id is replaced, not duplicated)."""
    root = reviews_root(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    index = root / "INDEX.md"
    plan = render_plan(state)
    sid = _safe_session_id(plan["session_id"])
    line = (f"- [`{sid}`]({sid}/README.md) — {plan['status']} · "
            f"{plan['subtasks_done']}/{plan['subtasks_total']} · "
            f"{plan['updated_at']} · {plan['goal'][:80]}")
    header = "# Review Index — every work session, newest first\n\n"
    existing: list[str] = []
    if index.is_file():
        for ln in index.read_text(encoding="utf-8").splitlines():
            if ln.startswith("- [`") and f"`{sid}`" in ln:
                continue  # drop the stale line for this id
            if ln.startswith("- [`"):
                existing.append(ln)
    existing.insert(0, line)
    index.write_text(header + "\n".join(existing) + "\n", encoding="utf-8")
    return index


def build_review(
    session_state: Any,
    *,
    data_dir: Path,
    events_records: list[dict[str, Any]] | None = None,
) -> Path:
    """Write the full review directory for a session and update the index.
    Returns the session's review directory path. Renders whatever state it
    has; never raises on a partial state."""
    sid = _safe_session_id(_get(session_state, "session_id", "unknown"))
    session_dir = reviews_root(data_dir) / sid
    session_dir.mkdir(parents=True, exist_ok=True)

    actions = collect_actions(session_state, events_records)

    # gaps-and-hardening-d — best-effort; a sentinel-registry hiccup must
    # never break the review itself.
    sentinel_warnings: list[Any] = []
    try:
        from sovereign_agent.stewardship.registry import list_sentinel_warnings
        sentinel_warnings = list_sentinel_warnings(data_dir)
    except Exception:  # noqa: BLE001
        pass

    (session_dir / "plan.json").write_text(
        json.dumps(render_plan(session_state), indent=2, default=str), encoding="utf-8")
    (session_dir / "README.md").write_text(
        render_readme(session_state, actions, sentinel_warnings=sentinel_warnings),
        encoding="utf-8")
    (session_dir / "how-to-verify.md").write_text(
        render_how_to_verify(session_state), encoding="utf-8")
    with open(session_dir / "actions.jsonl", "w", encoding="utf-8") as fh:
        for a in actions:
            fh.write(json.dumps(a, default=str) + "\n")

    update_index(data_dir, session_state)
    return session_dir


def list_reviews(data_dir: Path) -> list[str]:
    """Session ids that have a review directory, newest-first by mtime."""
    root = reviews_root(data_dir)
    if not root.is_dir():
        return []
    dirs = [p for p in root.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in dirs]


def compose_recap(data_dir: Path, *, n: int = 3) -> str:  # recap-command-d
    """recap-command-d (Kevin, 2026-07-25): "Maybe we can add recap last
    work session(s) events." A short, scannable summary of the last N
    sessions -- reuses each session's already-written plan.json rather
    than re-deriving anything. Never raises; a missing/corrupt plan.json
    for one session just gets skipped, not fatal to the whole recap."""
    root = reviews_root(data_dir)
    ids = list_reviews(data_dir)[:max(1, n)]
    if not ids:
        return "No sessions recorded yet."

    lines = [f"# Recap — last {len(ids)} session(s)", ""]
    for sid in ids:
        try:
            plan = json.loads((root / sid / "plan.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        mark = {"complete": "✓", "paused": "⏸", "budget": "⏱",
                "error": "✗"}.get(plan.get("status", ""), "·")
        tail = f" — {plan['pause_reason']}" if plan.get("pause_reason") else ""
        lines.append(
            f"{mark} **{plan.get('goal', '(no goal)')[:90]}**{tail}"
        )
        lines.append(
            f"   {plan.get('status', '?')} · "
            f"{plan.get('subtasks_done', 0)}/{plan.get('subtasks_total', 0)} subtasks · "
            f"`{sid}`"
        )
        if plan.get("last_error"):
            lines.append(f"   ⚠ {plan['last_error']}")
        lines.append("")
    return "\n".join(lines)
