"""cc_bridge.py — 🤝 Claude Code inside the cockpit (Kevin, 2026-07-18).

Kevin's wonder, verified and built: "run Claude Code inside of the
cockpit… Claude Code and Aria work together to grow and co-evolve."
Claude Code ships a headless mode (`claude -p`) and an Agent SDK made
for exactly this — programmatic use is supported and intended.

The safe SHAPE (this is the design, not a limitation):
  • Kevin TYPES `/cc <prompt>` — the typed command is the consent.
  • The subprocess runs in headless print mode with NORMAL permissions —
    never `--dangerously-skip-permissions`. In headless mode a tool call
    that would need a permission prompt simply isn't granted, so Claude
    Code answers with text, plans, and diffs: propose-don't-act by
    construction. Anything it drafts lands as a proposal Kevin applies.
  • argv-list execution (no shell interpolation), bounded timeout,
    repo-root cwd (so it sees CLAUDE.md + the codebase), every exchange
    ledgered to `<data>/cc/ledger.ndjson`.
  • What stays off (DEFERRED_UNSAFE): wiring this into any unattended
    loop that edits Aria's own code. Human gate, always.

Pure + injectable: `run_cc(prompt, runner=...)` never touches a real
subprocess in tests.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

__all__ = ["CCResult", "run_cc", "render_result", "cc_ledger_path"]

TIMEOUT_S = 240.0
MAX_PROMPT = 8000


@dataclass(frozen=True)
class CCResult:
    ok: bool
    text: str            # the reply (or the honest failure reason)
    duration_s: float
    cost_usd: float = 0.0
    session_id: str = ""


def cc_ledger_path(data_dir: Path) -> Path:
    return Path(data_dir) / "cc" / "ledger.ndjson"


def _default_runner(argv: list[str], cwd: str,
                    timeout: float) -> tuple[int, str, str]:
    """argv-only (no shell), bounded; never raises past the boundary."""
    import subprocess
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout:.0f}s"
    except FileNotFoundError:
        return 127, "", "claude CLI not found on PATH"
    except Exception as exc:  # noqa: BLE001
        return 1, "", type(exc).__name__


def _parse(stdout: str) -> tuple[str, float, str]:
    """headless --output-format json → (result text, cost, session id).
    Unparseable output degrades to the raw text — never a crash."""
    try:
        d = json.loads(stdout)
        if isinstance(d, dict):
            return (str(d.get("result", "") or "").strip(),
                    float(d.get("total_cost_usd", 0) or 0),
                    str(d.get("session_id", "") or ""))
    except Exception:  # noqa: BLE001
        pass
    return stdout.strip(), 0.0, ""


def _ledger(data_dir: Path | None, entry: dict) -> None:
    if data_dir is None:
        return
    try:
        p = cc_ledger_path(data_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def run_cc(prompt: str, *, runner=None, cwd: str | None = None,
           data_dir: Path | None = None,
           timeout: float = TIMEOUT_S) -> CCResult:
    """One headless Claude Code exchange. Safe by construction: normal
    permissions (no bypass flag, ever), argv list, bounded, ledgered."""
    prompt = (prompt or "").strip()
    if not prompt:
        return CCResult(False, "usage: /cc <prompt> — e.g. "
                        "/cc review sovereign-agent/src/… for bugs", 0.0)
    prompt = prompt[:MAX_PROMPT]
    runner = runner or _default_runner
    if cwd is None:
        cwd = str(Path(__file__).resolve().parents[2])   # the repo root
    argv = ["claude", "-p", "--output-format", "json", "--", prompt]
    t0 = time.monotonic()
    rc, out, err = runner(argv, cwd, timeout)
    dt = time.monotonic() - t0
    if rc != 0:
        detail = (err or out or f"exit {rc}").strip()[:400]
        res = CCResult(False, f"Claude Code couldn't answer: {detail}", dt)
    else:
        text, cost, sid = _parse(out)
        res = CCResult(bool(text), text or "(empty reply)", dt, cost, sid)
    _ledger(data_dir, {"ts": time.time(), "prompt": prompt[:400],
                       "ok": res.ok, "duration_s": round(dt, 1),
                       "cost_usd": res.cost_usd,
                       "session_id": res.session_id,
                       "reply_head": res.text[:400]})
    return res


def render_result(res: CCResult) -> str:
    head = ("🤝 Claude Code" if res.ok
            else "🤝 Claude Code (no answer)")
    meta = f"{res.duration_s:.0f}s"
    if res.cost_usd:
        meta += f" · ${res.cost_usd:.2f}"
    return f"{head} — {meta}\n{res.text}"
