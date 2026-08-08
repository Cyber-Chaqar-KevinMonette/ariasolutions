# 06 — Runbook

## Daily
- `sovereign cockpit` — she greets with self-knowledge, restores the
  conversation tail, witnesses yesterday (first wake of the day),
  surfaces any rest point. Leave with `/rest` (safe exit → bookmark).
- Backups: automatic (BackupSentinel, 24h, verified, →
  ~/AA-Erebo/sov-backups).

## Health
- `sov doctor` — full checks (includes aegis bootstrap).
- `sov sentinels list|scan` — the board (target: 0 errors).
- `python -m sovereign_agent.path_scan [triage]` — staged-module hygiene.
- `python -m sovereign_agent.loose_threads scan|disposition <sym> <verdict> [reason]`.

## Proving
- Offline (also in pytest): `python -m sovereign_agent.proving_ground offline`
  — mechanically-scored safety tasks; results persist; `trend` reads
  STORED scores.
- Live gates (Ollama, ~1min each): `scripts/golden_path_smoke.sh` +
  `scripts/golden_reflex_smoke.sh`. Run both after any change to
  loop/prompt/tools.

## Recovery
- Snapshot restore: Tier-3, human (`backup.restore` snapshots current
  state first).
- Paused/budget session: `/resume [sid]` (work mode).
- Dead cockpit worker: auto-respawns twice → red ⛔ latch → restart.
- Corrupt event line: auto-skipped + counted (`ingest-skip-x`).
- Every applied module keeps timestamped backups in `aria-<name>/backups/`.

## Full suite
`.venv/bin/python -m pytest tests/ -q --ignore=tests/test_git_tools.py`
→ 0 failures, always. (test_git_tools is non-hermetic; run alone.)
