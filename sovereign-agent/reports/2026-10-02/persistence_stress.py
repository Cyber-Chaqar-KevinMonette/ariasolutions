"""Persistence stress test for Aria — events log, atoms DB, seals, backups, migrations.

Reproduce (from sovereign-agent/, uses a throwaway data dir, never your real one):
    .venv/bin/python reports/2026-10-02/persistence_stress.py
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = str(REPO / ".venv" / "bin" / "python")
CLI = str(REPO / ".venv" / "bin" / "sovereign")
RESULTS: list[tuple[str, bool, str]] = []


def fresh_env() -> dict[str, str]:
    root = Path(tempfile.mkdtemp(prefix="aria-persist-"))
    env = dict(os.environ, XDG_DATA_HOME=str(root / "data"), XDG_CONFIG_HOME=str(root / "config"),
               NO_COLOR="1", COLUMNS="120")
    subprocess.run([CLI, "init"], env=env, capture_output=True, text=True, timeout=120)
    return env


def py(env: dict[str, str], code: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-c", textwrap.dedent(code)], env=env, capture_output=True, text=True,
                          timeout=timeout)


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)


EVENTS_PATH = "from sovereign_agent.config import SETTINGS; p = SETTINGS.paths.events_jsonl"


def read_events(env) -> tuple[int, int, int, bool]:
    """(lines, valid_json, unique_ids, ends_with_newline)"""
    out = py(env, f"""
        import json; {EVENTS_PATH}
        raw = p.read_bytes() if p.exists() else b""
        lines = [l for l in raw.split(b"\\n") if l.strip()]
        ok = [];
        for l in lines:
            try: ok.append(json.loads(l)["event_id"])
            except Exception: pass
        print(json.dumps([len(lines), len(ok), len(set(ok)), raw.endswith(b"\\n") or not raw]))
    """)
    return tuple(json.loads(out.stdout.strip().splitlines()[-1]))


# 1. Concurrent writers: 8 processes x 400 events, appended to one events.jsonl
def test_concurrent_events():
    env = fresh_env()
    base = read_events(env)[0]
    writer = f"""
        from sovereign_agent.events import emit_event
        for i in range(400):
            emit_event("stress.concurrent", plane="data", trace_id="stress", payload={{"i": i, "pad": "x" * 200}})
    """
    procs = [subprocess.Popen([PY, "-c", textwrap.dedent(writer)], env=env, stderr=subprocess.PIPE)
             for _ in range(8)]
    errs = [p.communicate(timeout=600)[1].decode()[-300:] for p in procs]
    lines, valid, unique, nl = read_events(env)
    added = lines - base
    record("events: 8 concurrent writers x 400", added == 3200 and valid == lines and unique == valid and nl,
           f"{added}/3200 new lines, {valid}/{lines} valid JSON, {unique} unique ids"
           + (f"; stderr: {[e for e in errs if e.strip()][:1]}" if any(e.strip() for e in errs) else ""))


# 2. Hard crash: SIGKILL a writer mid-stream, then keep writing and ingest
def test_crash_mid_write():
    env = fresh_env()
    writer = """
        from sovereign_agent.events import emit_event
        i = 0
        while True:
            emit_event("stress.crash", plane="data", trace_id="crash", payload={"i": i, "pad": "y" * 1500}); i += 1
    """
    p = subprocess.Popen([PY, "-c", textwrap.dedent(writer)], env=env)
    time.sleep(4)
    p.send_signal(signal.SIGKILL); p.wait()
    lines1, valid1, _, nl1 = read_events(env)
    post = py(env, """
        from sovereign_agent.events import emit_event, init_events_db, tail_to_sqlite
        for i in range(50): emit_event("stress.after_crash", plane="data", trace_id="crash", payload={"i": i})
        conn = init_events_db(); n = tail_to_sqlite(conn)
        total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        print(n, total)
    """)
    lines2, valid2, _, nl2 = read_events(env)
    ingested = post.stdout.strip().split()
    record("events: SIGKILL mid-write, then resume",
           valid1 == lines1 and valid2 == lines2 and nl2 and post.returncode == 0,
           f"after kill: {valid1}/{lines1} valid (clean tail={nl1}); after resume: {valid2}/{lines2} valid; "
           f"ingested to SQLite: {ingested or post.stderr[-200:]}")


# 3. Atoms DB: 6 processes x 300 inserts with WAL + busy_timeout
def test_concurrent_atoms():
    env = fresh_env()
    writer = """
        import os, sqlite3
        from sovereign_agent.db import open_atoms_db
        conn = open_atoms_db(); errors = 0
        for i in range(300):
            try:
                conn.execute("INSERT INTO atoms (atom_id, type, summary, content_ref, claims, parents, confidence, created_at, created_by) "
                             "VALUES (?, 'experience', 'stress', '{}', '[]', '[]', 0.9, '2026-10-02T00:00:00Z', '{}')",
                             (f"S{os.getpid()}-{i:04d}",))
            except sqlite3.OperationalError as exc:
                errors += 1
        print("errors", errors)
    """
    procs = [subprocess.Popen([PY, "-c", textwrap.dedent(writer)], env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) for _ in range(6)]
    outs = [p.communicate(timeout=600) for p in procs]
    errors = sum(int(o.split()[-1]) for o, _ in outs if o.strip().startswith("errors"))
    crashed = [e[-200:] for o, e in outs if not o.strip()]
    count = py(env, """
        from sovereign_agent.db import open_atoms_db
        c = open_atoms_db()
        print(c.execute("SELECT COUNT(*) FROM atoms WHERE summary='stress'").fetchone()[0],
              c.execute("PRAGMA integrity_check").fetchone()[0])
    """).stdout.split()
    record("atoms DB: 6 concurrent writers x 300", count[:2] == ["1800", "ok"] and errors == 0 and not crashed,
           f"rows={count[0] if count else '?'}/1800, integrity={count[1] if len(count) > 1 else '?'}, "
           f"locked errors={errors}" + (f", crashed: {crashed[:1]}" if crashed else ""))


# 4. Seal + tamper detection
def test_seal_tamper():
    env = fresh_env()
    out = py(env, f"""
        import json
        from datetime import date, timedelta, datetime, timezone
        import sovereign_agent.events as ev
        y = date.today() - timedelta(days=1)
        ev._utc_now_rfc3339 = lambda: datetime(y.year, y.month, y.day, 12, 0, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        for i in range(25): ev.emit_event("stress.seal", plane="data", trace_id="seal", payload={{"i": i}})
        from sovereign_agent import seal
        from sovereign_agent.config import SETTINGS
        today_file = SETTINGS.paths.events_jsonl          # emit_event wrote to today's rotated file
        seal._events_jsonl_for_date(y).write_bytes(today_file.read_bytes())
        seal.seal_yesterday()
        ok_before = seal.verify_seal(y)
        p = seal._events_jsonl_for_date(y)
        lines = p.read_text().splitlines()
        target = next(i for i, l in enumerate(lines) if '"stress.seal"' in l and '"i":3}}' in l)
        original = p.read_bytes()
        lines[target] = lines[target].replace('"i":3}}', '"i":9}}')   # a one-character edit
        p.write_text("\\n".join(lines) + "\\n")
        assert p.read_bytes() != original, "tamper did not change the file"
        ok_after = seal.verify_seal(y)
        print(json.dumps([ok_before, ok_after]))
    """)
    try:
        before, after = json.loads(out.stdout.strip().splitlines()[-1])
        record("seal: verifies clean log, catches a 1-character edit", before[0] and not after[0],
               f"before: {before[1]}; after tamper: {after[1]}")
    except Exception:  # noqa: BLE001
        record("seal: verifies clean log, catches a 1-character edit", False, (out.stderr or out.stdout)[-300:])


# 5. Backup snapshot -> change -> verify -> restore
def test_backup_restore():
    env = fresh_env()
    seed = """
        from sovereign_agent.db import open_atoms_db
        c = open_atoms_db()
        c.execute("INSERT INTO atoms (atom_id, type, summary, content_ref, claims, parents, confidence, created_at, created_by) VALUES (?, 'experience', ?, '{}', '[]', '[]', 0.9, '2026-10-02T00:00:00Z', '{}')", ("{id}", "{label}"))
    """
    count = """
        from sovereign_agent.db import open_atoms_db
        print(open_atoms_db().execute("SELECT COUNT(*) FROM atoms WHERE summary IN ('before','after')").fetchone()[0])
    """
    py(env, seed.replace("{id}", "B1").replace("{label}", "before"))
    snap = subprocess.run([CLI, "backup", "snapshot"], env=env, capture_output=True, text=True, timeout=300)
    py(env, seed.replace("{id}", "A1").replace("{label}", "after"))
    n_changed = py(env, count).stdout.strip()
    lst = subprocess.run([CLI, "--json", "backup", "list"], env=env, capture_output=True, text=True, timeout=120)
    record("backup: snapshot command", snap.returncode == 0,
           f"rc={snap.returncode}; {(snap.stdout + snap.stderr).strip().splitlines()[-1][:160] if (snap.stdout + snap.stderr).strip() else ''}")
    record("backup: list --json is valid JSON", _is_json(lst.stdout), f"rc={lst.returncode}; {lst.stdout[:120]!r}")
    snap_id = json.loads(lst.stdout)["snapshots"][0]["snapshot_id"] if _is_json(lst.stdout) else ""
    verify = subprocess.run([CLI, "backup", "verify", snap_id], env=env, capture_output=True, text=True, timeout=300)
    record("backup: verify snapshot", verify.returncode == 0,
           f"rc={verify.returncode}; {' '.join((verify.stdout + verify.stderr).split())[:160]}")
    restore = subprocess.run([CLI, "backup", "restore", snap_id, "--yes"], env=env, capture_output=True,
                             text=True, timeout=300)
    n_restored = py(env, count).stdout.strip()
    after = subprocess.run([CLI, "--json", "backup", "list"], env=env, capture_output=True, text=True, timeout=120)
    labels = [s.get("label") or "" for s in json.loads(after.stdout).get("snapshots", [])] if _is_json(after.stdout) else []
    record("backup: restore rolls back a change, keeps a pre-restore snapshot",
           restore.returncode == 0 and n_changed == "2" and n_restored == "1"
           and any(lbl.startswith("pre-restore") for lbl in labels),
           f"rows: before snapshot 1, after change {n_changed}, after restore {n_restored}; "
           f"pre-restore snapshot kept: {any(lbl.startswith('pre-restore') for lbl in labels)}; rc={restore.returncode} "
           f"{' '.join((restore.stdout + restore.stderr).split())[-160:]}")


def _is_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except ValueError:
        return False


# 6. Migrations are idempotent
def test_migrations_idempotent():
    env = fresh_env()
    runs = [subprocess.run([CLI, "migrations", "apply"], env=env, capture_output=True, text=True, timeout=120)
            for _ in range(2)]
    status = subprocess.run([CLI, "migrations", "status"], env=env, capture_output=True, text=True, timeout=120)
    record("migrations: apply twice is safe", all(r.returncode == 0 for r in runs) and status.returncode == 0,
           f"rc={[r.returncode for r in runs]}, status rc={status.returncode}; "
           f"{' '.join((runs[1].stdout + runs[1].stderr).split())[:140]}")


if __name__ == "__main__":
    for t in (test_concurrent_events, test_crash_mid_write, test_concurrent_atoms, test_seal_tamper,
              test_backup_restore, test_migrations_idempotent):
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            record(t.__name__, False, f"harness error: {exc!r}"[:300])
    passed = sum(ok for _, ok, _ in RESULTS)
    print(f"\n{passed}/{len(RESULTS)} persistence checks passed")
