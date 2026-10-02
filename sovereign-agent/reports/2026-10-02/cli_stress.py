"""CLI stress test for Aria's `sovereign` / `sov` command — against habits of modern CLIs
(gh, git, cargo, uv, kubectl). Uses a throwaway data dir, never your real one.

Reproduce (from sovereign-agent/):
    .venv/bin/python reports/2026-10-02/cli_stress.py
"""
from __future__ import annotations

import json
import os
import re
import signal
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = str(REPO / ".venv" / "bin" / "sovereign")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
ROOT = Path(tempfile.mkdtemp(prefix="aria-cli-"))
ENV = dict(os.environ, XDG_DATA_HOME=str(ROOT / "data"), XDG_CONFIG_HOME=str(ROOT / "config"),
           COLUMNS="120", TERM="xterm-256color")
ENV.pop("NO_COLOR", None)
RESULTS: list[tuple[str, bool, str]] = []

# Read-only commands safe to run with no arguments in an empty data dir.
READ_ONLY = ["status", "doctor", "info", "health", "capabilities", "truth", "gaps", "requests",
             "sentinels", "personas", "channels", "glyphs", "map", "proposals", "approvals", "backlog",
             "insights", "lessons", "reviews", "heartbeat", "constitution", "charter", "cadence", "vram",
             "models", "keys", "home", "profile", "reward", "commitments", "relationships", "people"]


def run(args: list[str], env: dict | None = None, timeout: int = 60, stdin: str | None = None):
    t0 = time.perf_counter()
    try:
        p = subprocess.run([CLI, *args], env=env or ENV, capture_output=True, text=True, timeout=timeout,
                           input=stdin)
        return p.returncode, p.stdout, p.stderr, time.perf_counter() - t0
    except subprocess.TimeoutExpired as exc:
        return "TIMEOUT", exc.stdout or "", exc.stderr or "", timeout


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)


def has_traceback(*texts) -> bool:
    return any("Traceback (most recent call last)" in (t or "") for t in texts)


def commands() -> list[str]:
    _, out, _, _ = run(["--help"], env=dict(ENV, COLUMNS="200"))
    body = out.split("Commands", 1)[-1]
    return re.findall(r"^│ ([a-z][a-z0-9-]+) ", body, flags=re.M)


def main() -> None:
    run(["init"], timeout=120)

    # 1. Startup speed
    times = [run(["--help"])[3] for _ in range(5)]
    med = statistics.median(times)
    record("startup: `--help` median of 5", med < 1.0, f"{med * 1000:.0f} ms (modern CLIs: well under 300 ms)")
    vt = [run(["--version"])[3] for _ in range(5)]
    rc, out, err, _ = run(["--version"])
    record("`--version`", rc == 0 and bool(out.strip()), f"rc={rc}, {out.strip()[:40]!r}, median {statistics.median(vt) * 1000:.0f} ms")

    # 2. Every command has working help
    cmds = commands()
    bad, slow, tb, undocumented = [], [], [], []
    help_times = []
    for c in cmds:
        rc, out, err, dt = run([c, "--help"])
        help_times.append(dt)
        if rc != 0:
            bad.append(f"{c}(rc={rc})")
        if has_traceback(out, err):
            tb.append(c)
        if dt > 2.0:
            slow.append(f"{c}({dt:.1f}s)")
        desc = out.split("Usage:", 1)[-1].split("\n", 3)
        if len(" ".join(desc[1:3]).strip()) < 5:
            undocumented.append(c)
    record(f"help for all {len(cmds)} commands", not bad and not tb,
           f"failures={bad[:8]}, tracebacks={tb[:8]}, max {max(help_times):.2f}s, slow(>2s)={slow[:5]}")
    record("every command has a description", not undocumented, f"missing: {undocumented[:10]}")

    # 3. Mistakes: unknown command, typo, bad option, missing argument
    rc, out, err, _ = run(["statsu"])
    record("unknown command → non-zero exit, error on stderr", rc not in (0, "TIMEOUT") and bool(err.strip()) and not out.strip(),
           f"rc={rc}, stderr={' '.join(err.split())[:120]!r}")
    record("typo suggests the right command (`statsu` → status)", "status" in err,
           "suggested" if "status" in err else "no 'did you mean' suggestion")
    rc, out, err, _ = run(["status", "--bogus-flag"])
    record("unknown option → clean error, no traceback", rc not in (0, "TIMEOUT") and not has_traceback(out, err),
           f"rc={rc}, {' '.join(err.split())[:100]!r}")
    rc, out, err, _ = run(["verify"])
    record("missing required argument → clean error", rc not in (0, "TIMEOUT") and not has_traceback(out, err),
           f"rc={rc}, {' '.join(err.split())[:100]!r}")
    rc, out, err, _ = run(["verify", "not-a-date"])
    record("invalid argument value → clean error, no traceback", rc not in (0, "TIMEOUT") and not has_traceback(out, err),
           f"rc={rc}, {' '.join((err or out).split())[:120]!r}")

    # 4. Read-only commands on a fresh install
    ro_fail, ro_tb, ro_slow = [], [], []
    for c in [c for c in READ_ONLY if c in cmds]:
        rc, out, err, dt = run([c], timeout=60)
        if has_traceback(out, err):
            ro_tb.append(c)
        elif rc not in (0, 1, 2):
            ro_fail.append(f"{c}(rc={rc})")
        if dt > 5:
            ro_slow.append(f"{c}({dt:.1f}s)" if rc != "TIMEOUT" else f"{c}(TIMEOUT)")
    record("read-only commands on a fresh install: no crashes", not ro_tb and not ro_fail,
           f"tracebacks={ro_tb}, odd exits={ro_fail}, slow(>5s)={ro_slow}")

    # 5. Scripting: --json, piping, NO_COLOR
    json_ok, json_bad = [], []
    for c in ["status", "doctor", "info", "health check", "capabilities", "requests", "approvals"]:
        if c not in cmds:
            continue
        rc, out, err, _ = run(["--json", *c.split()])
        try:
            json.loads(out)
            json_ok.append(c)
        except ValueError:
            json_bad.append(c)
    record("`--json` gives valid JSON on read commands", not json_bad, f"valid: {json_ok}; not JSON: {json_bad}")
    rc, out, err, _ = run(["status"])
    record("piped output has no color codes", not ANSI.search(out), "clean" if not ANSI.search(out) else "ANSI codes in piped stdout")
    rc, out, err, _ = run(["status"], env=dict(ENV, NO_COLOR="1"))
    record("NO_COLOR respected", not ANSI.search(out + err), "clean" if not ANSI.search(out + err) else "ANSI codes despite NO_COLOR")

    # 6. Shell completion
    rc, out, err, _ = run(["--show-completion", "bash"], env=dict(ENV, SHELL="/bin/bash"))
    record("shell completion script", rc == 0 and "complete" in out, f"rc={rc}, {len(out)} bytes")

    # 7. Ctrl-C on a long-running command
    p = subprocess.Popen([CLI, "tail"], env=ENV, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(3)
    p.send_signal(signal.SIGINT)
    try:
        out, err = p.communicate(timeout=10)
        record("Ctrl-C exits cleanly (no traceback)", not has_traceback(out, err),
               f"rc={p.returncode}{' (still running before signal? check)' if p.returncode is None else ''}")
    except subprocess.TimeoutExpired:
        p.kill()
        record("Ctrl-C exits cleanly (no traceback)", False, "did not exit within 10 s of SIGINT")

    # 8. Hostile input: very long and unicode text never crashes
    if "recall" in cmds:
        rc, out, err, _ = run(["recall", "🌙" * 2000 + "'; DROP TABLE atoms; --"], timeout=60)
        record("hostile input (8 KB unicode + SQL) → no traceback", not has_traceback(out, err), f"rc={rc}")

    passed = sum(ok for _, ok, _ in RESULTS)
    print(f"\n{passed}/{len(RESULTS)} CLI checks passed · {len(cmds)} commands")


if __name__ == "__main__":
    main()
