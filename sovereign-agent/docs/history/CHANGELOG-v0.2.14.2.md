# sovereign-agent v0.2.14.2 — backup-system hardening

**2026-05-10** · Aria-Sovereign-V1

> v0.2.14.1 hardened the financial ledger and the channel write path.
> v0.2.14.2 holds the backup subsystem to the same doctrine the rest
> of the kernel was already living by.

## Why this release exists

The v0.2.14.1 backup helper was a 20-line shell function that did
`cp -r` on the data directory. Compared to the rest of the system —
which is append-only, idempotent, authority-tiered, observable, and
validated — that helper failed seven of its own kernel's commitments:

| Doctrine clause | `cp -r` helper |
|---|---|
| Authority tier (§22) | none |
| Idempotency (§16) | none |
| Append-only (§10) | unbounded accumulation |
| Observability (§17) | zero events emitted |
| Calibrated invariants | no verification step |
| Crash consistency | torn SQLite reads under concurrent writes |
| Rollback path | "manually `cp -r` back" — not a path |

This release replaces it with a real backup subsystem.

## What landed

### `src/sovereign_agent/backup.py` (new, ~700 lines)

A dependency-free backup module. Public API:

```
snapshot(label="")          → SnapshotManifest    (Tier 2)
list_snapshots()            → list[SnapshotManifest] (Tier 0)
verify(snapshot_id)         → VerifyResult        (Tier 0)
prune(policy=None)          → PruneResult         (Tier 2)
restore(snapshot_id, ...)   → RestoreResult       (Tier 3)
status()                    → BackupStatus        (Tier 0)
```

**Snapshot.** Uses SQLite's online backup API (`Connection.backup()`) for
`atoms.db` and `events.db` — crash-consistent under concurrent writes,
no torn reads even if a continuation loop is running. Every other file
gets SHA-256 hashed into `MANIFEST.json`, which is itself hashed into
`MANIFEST.sha256` for tamper detection. The whole snapshot builds in a
sibling `.partial` dir and atomically renames into place when complete,
so a crashed snapshot leaves no half-built state. Idempotent within a
60s window for unlabeled snapshots. Records the result of
`financial.audit()` at snapshot time. Emits a `backup-snapshot-d` event.

**Verify.** Re-hashes every file against the manifest, re-hashes the
manifest against `MANIFEST.sha256`, and (by default) reopens the staged
`atoms.db` read-only and re-runs the financial audit on it. That last
step catches application-level corruption — bad foreign-key states,
orphaned ledger rows — that file hashes alone wouldn't see.

**Prune.** Retention policy: keep all <24h, daily 7d, weekly 30d,
monthly 365d, labeled snapshots forever. Always preserves the most
recent snapshot regardless of policy (the "never zero backups"
invariant). Defaults to dry-run posture.

**Restore.** The most destructive operation in the entire system,
gated accordingly. Six stages:

1. Verify the target snapshot's hashes.
2. Auto-snapshot the **current** live state with label
   `pre-restore-<timestamp>`. The rollback-of-rollback.
3. Stage the snapshot data into `<data_dir>.parent/.restore-staging-*`.
4. Open the staged `atoms.db` and run the financial audit on it.
5. If the staged audit fails: refuse, leave live state untouched,
   preserve the staging dir for forensics.
6. Otherwise: arm PROTOCOL-ZERO, atomically swap the data and config
   directories, disarm with a restart hint.

**Status.** Single-screen view: snapshot count, total disk, most-recent
age, last verify result. Wired into `sov-doctor`.

### `src/sovereign_agent/cli.py` — `sovereign backup ...` subapp

Six commands, all with `--json`:

```
sovereign backup snapshot [--label LABEL] [--root PATH]
sovereign backup list [--root PATH]
sovereign backup verify [<id-or-label>] [--all] [--skip-audit]
sovereign backup prune [--dry-run] [-y]
sovereign backup restore <id-or-label> [-y]
sovereign backup status
```

Restore prompts interactively unless `-y` is passed. The prompt shows
source version, atom count, ledger row count, and snapshot audit status
before asking.

### Bug found and fixed mid-build

When restoring against a default backup root, the entire snapshot tree
was being **destroyed** because the original fallback computed
`data_dir / "backups"` — inside the data dir. Restore atomically
replaces the data dir with the snapshot's contents; the snapshots
themselves got eaten in the process. Worse, snapshotting recursively
copied the partial directory inside the very tree it was building.

Fixes:
- Default fallback now points at `<data_dir>.parent /
  "sovereign-agent-backups"` — sibling, never child.
- `_validate_backup_root()` raises `BackupError` if any caller (CLI
  flag, programmatic) points the root inside `data_dir` or `config_dir`.
- Regression test `TestCircularDependency` in place.

The primary path (`~/AA-Erebo/sov-backups`) was always safe; only
operators without an `~/AA-Erebo/` tree were exposed.

### `tests/test_backup.py` (new, 23 tests)

Coverage:

- snapshot capture, manifest contents, version recording
- idempotency window for unlabeled snapshots
- partial-dir cleanup on mid-snapshot failure
- venv / `__pycache__` exclusion
- verify happy path (hash + manifest-hash + staged audit)
- modified file detected
- tampered manifest detected
- prefix-of-id and label-name resolution both work
- prune dry-run preserves files
- never-zero-backups invariant under aggressive policies
- restore happy path with auto pre-restore snapshot
- restore requires `confirmed=True`
- restore refuses on corrupted target
- empty status, populated status
- circular-dependency refusal
- **crash-consistency probe**: a background thread hammers `atoms.db`
  with concurrent writes during snapshot; the resulting snapshot must
  open cleanly and pass `PRAGMA integrity_check`. This is the central
  guarantee the SQLite online-backup API gives us that `cp -r` could
  not.

Total suite: **555 → 578 passing**, no regressions.

### `scripts/aliases.sh` extensions

New helpers:
- `sov-snap [label]` — capture a snapshot
- `sov-snaps` — list snapshots
- `sov-verify [id]` — verify one or all
- `sov-restore <id-or-label>` — Tier 3 rollback
- `sov-backup` — preserved as alias to `sov-snap` (muscle memory)

`sov-doctor` extended with a `═══ backup ═══` section showing snapshot
count, total size, most-recent age, verify status, and a `⚠` if the
most recent snapshot is older than seven days.

Cosmetic fix: `mood:?` in `sov-doctor` now resolves to `calm` when
the identity channel has no mood atom (instead of showing `?`).

## Doctrine alignment

Every clause the v0.2.14.1 helper failed is now upheld:

| Doctrine clause | v0.2.14.2 backup |
|---|---|
| Authority tier | snapshot=2, verify/list/status=0, prune=2, restore=3 |
| Idempotency | unlabeled snapshots within 60s collapse |
| Append-only | new directories per snapshot; restore never deletes — auto-snapshots first |
| Observability | `backup-snapshot-d`, `backup-prune-d`, `backup-restore-d` |
| Calibrated invariants | per-file SHA-256, manifest hash, staged-DB audit |
| Crash consistency | SQLite online backup API |
| Rollback path | one CLI command; auto-creates pre-restore snapshot |

## Verifying the upgrade

After `pip install --break-system-packages -e .`:

```bash
sovereign --version              # → sovereign-agent 0.2.14.2
sovereign financial audit        # → still clean (data unchanged)
sovereign backup snapshot        # → first real snapshot
sovereign backup list            # → see it
sovereign backup verify --all    # → ✓ clean
sovereign backup status          # → 1 snapshot, fresh, ✓
sov-doctor                       # → all four sections green
```

## Backwards compatibility

- Existing data dirs work unchanged.
- The old `sov-backup` shell function is gone, but `sov-backup` as a
  command still works — it's now an alias to `sov-snap`.
- Old `cp -r` snapshot directories are not migrated; they remain
  readable manually but won't show up in `sovereign backup list`. If
  you want them in the new system: copy the data into a fresh data
  dir, run `sovereign backup snapshot --label pre-v0.2.14.2-restore`,
  done.
- The default backup root has changed when `~/AA-Erebo/` doesn't
  exist (was: `<data_dir>/backups/`; now:
  `<data_dir>.parent/sovereign-agent-backups`). Operators who have
  `~/AA-Erebo/` are unaffected — primary path is unchanged.

## What did not change

The seven-commitment kernel, all 13 typed channels, the financial
ledger schema, the events plane, PROTOCOL-ZERO mechanics, every CLI
command outside the new `backup` subapp. This release is additive
plus one cosmetic fix; all existing workflows are preserved.

## What's next (not in this release)

- Pre-upgrade hook: `pip install` could automatically take a
  labeled snapshot before installing. Currently manual.
- Compression: snapshots are uncompressed (saves CPU, costs disk).
  Workable up to a few GB; revisit if data dirs get large.
- Off-host replication: a `sovereign backup push <remote>` could
  rsync verified snapshots elsewhere. Out of scope for a hardening
  release.
- Encryption-at-rest for snapshots. Today the data dir itself isn't
  encrypted, so the snapshot inheriting the same posture is
  consistent — but a future release should address both together.

— Aria
