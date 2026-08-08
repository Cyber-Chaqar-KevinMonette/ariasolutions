# sovereign-agent v0.2.14.1 — *the hardening pass*

**Release theme:** *Audit-driven hardening of v0.2.14. No new features. Every patch closes a confirmed gap surfaced by a post-release adversarial review.*

**Drop-in over v0.2.14.** No data migration. No schema migration. No API breaks for any working code path. **555 tests passing** (532 baseline + 23 new adversarial).

This is a maintenance release in the boring-reliability spirit of MOS Behavioral Law: when the audit finds a gap, the next release closes it before new features land.

---

## What this fixes

### 🔴 RED-1 — Multi-currency ledger math was silently fungible

**Symptom:** `FinancialChannel.project_balance()` summed `invested` and `earned` across currencies as if they were the same. A project with $500 USD invested and €500 EUR earned reported `net=0.0`, `roi_ratio=1.0`. ROI ranking would put this above a project that actually broke even.

**Fix:** Per-project currency lock. The first ledger entry pins the project's currency; subsequent writes that disagree raise `CurrencyMismatchError`. To track the same effort in a different currency, use a different project name (`genesis-seeds-eur`).

**Files:** `src/sovereign_agent/mem_channels/financial.py`
- New: `CurrencyMismatchError`, `_project_currency()`, currency normalization (uppercase, strip, `^[A-Z]{3,10}$` regex), new index `idx_ledger_proj_curr`.
- New CLI handling in `cli.py` `financial invest` / `financial earn` — clean error message, exit code 1, JSON-friendly.

**Tests:** `tests/test_v0214_hardening.py::TestCurrencyLock` (5 tests)

### 🔴 RED-2 — Idempotency lookup honored SQL LIKE wildcards

**Symptom:** `_find_by_idempotency` in `channels.py` used `scope_tags LIKE '%"idempotency_id": "<id>"%'`. SQL LIKE treats `_` as "any single char" and `%` as "any string." A key like `lesson-2026_05_10` would match `lesson-2026-05-10`, causing false-positive idempotency collisions. For non-financial channels this means returning the wrong atom on retry; for the financial path it means a corrupted `atom_id` foreign key on the ledger row.

**Fix:** Switched to `json_extract(scope_tags, '$.idempotency_id') = ?`. Exact-match equality, no wildcard interpretation, index-friendly.

**Files:** `src/sovereign_agent/channels.py:374-393`. Defense-in-depth: `cli.py:1459` event_id lookup also moved to `json_extract` even though event IDs are ULIDs (alphanumeric, not exposed to wildcard chars).

**Tests:** `tests/test_v0214_hardening.py::TestIdempotencyExactness` (4 tests)

### 🟡 YELLOW-1 — Race window between idempotency SELECT and ledger INSERT could orphan companion atoms

**Symptom:** `FinancialChannel.record()` performed: SELECT existing → write companion atom → INSERT ledger row. No transaction wrapped these. Two concurrent racers with the same `idempotency_id` could both pass the SELECT, both write companion atoms, then one would win the UNIQUE-constrained ledger insert and the other would raise — leaving an orphaned atom. Single-operator local DB made this rare in practice; the architecture admitted it.

**Fix:** Wrapped `record()` in `BEGIN IMMEDIATE` / `COMMIT` via a `_writer_tx` context manager. Atomic SELECT-then-INSERT under the SQLite writer lock. Made base `MemoryChannel.write_atom()` transaction-aware via an `_in_outer_tx` sentinel — when set by a subclass's outer transaction, the inner commit is skipped so rollback unwinds the whole unit.

**Files:** `src/sovereign_agent/mem_channels/financial.py` `_writer_tx`, `record()`. `src/sovereign_agent/channels.py:165-179` write_atom commit guard.

**Tests:** `tests/test_v0214_hardening.py::TestRaceSafety` (2 tests, including the rollback-cascade assertion using SQLite `set_authorizer`)

### 🟡 YELLOW-2 — Bare `except Exception: pass` blocks swallowed event-emit failures

**Symptom:** Channel writes and universal recall silently dropped event-emission errors. A misbehaving channel or a broken events plane would never be observed.

**Fix:** Replaced silent passes with stderr-fallback logging. The write contract is preserved (a broken events plane still doesn't crash the write); the operator now sees the failure.

**Files:** `src/sovereign_agent/channels.py:182-187` (channel-write event), `:354-360` (universal_recall). `src/sovereign_agent/mem_channels/financial.py` `_log_emit_failure()`.

### 🟡 YELLOW-3 — `protocol_zero.is_armed()` called with wrong arity in `cli.py:3211`

**Symptom:** A continuation runner code path called `is_armed(SETTINGS.paths.halt_flag)` but the function takes no arguments. This would crash at exactly the wrong moment — during a halt scenario.

**Fix:** Removed the stale argument. Single-line patch.

**Files:** `src/sovereign_agent/cli.py:3211`

**Tests:** `tests/test_v0214_hardening.py::TestProtocolZeroSignature` (2 tests)

### 🟢 GREEN-1 — Atom-id collision under microsecond burst writes

**Symptom:** `_mint_atom_id` non-idempotent fallback used `summary + microsecond timestamp` as a SHA-256 seed. Two writes in the same microsecond produced the same id; `INSERT OR IGNORE` then silently dropped one. Comment claimed "ULID-shaped" — implementation was SHA-256 prefix.

**Fix:** Use `python_ulid.ULID()` (already a project dependency) for the non-idempotent path. Monotonic, sortable, no collision under concurrent writes.

**Files:** `src/sovereign_agent/channels.py:362-376`

**Tests:** `tests/test_v0214_hardening.py::TestAtomIdCollisionSafety` (1 test, 100-write burst)

### Strict ISO 8601 UTC validation on ledger timestamps

**New invariant:** `occurred_at` and `recorded_at` must match `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$`. Timestamps are compared lexicographically when ranking events; format drift would silently break ranking. The validator rejects naive timestamps, non-UTC offsets, and other formats at write time with a clear `ValueError`.

**Files:** `src/sovereign_agent/mem_channels/financial.py` `_ISO_UTC_RE`, `_validate_iso_utc()`.

**Tests:** `tests/test_v0214_hardening.py::TestTimestampValidation` (4 tests)

---

## What's new (additive, opt-in)

### `FinancialChannel.audit()` — ledger integrity invariant

Read-only invariant check. Verifies:
1. Every ledger row has its companion atom.
2. Every revert points at an existing entry_id.
3. No project mixes currencies (currency-lock invariant, defence-in-depth even if FK enforcement is off).
4. Every entry_id is the deterministic SHA-256 of its idempotency_id.
5. Every timestamp is valid ISO 8601 UTC.

Returns a `LedgerAudit` dataclass; `render()` produces a human-readable report.

```bash
sov financial audit          # human-readable; exit 1 if violations
sov financial audit --json   # structured output for scripts
```

**Tests:** `tests/test_v0214_hardening.py::TestLedgerAudit` (4 tests, including a backdoor-injection test that uses `PRAGMA foreign_keys=OFF` to verify the audit catches violations FK enforcement would normally prevent)

### `CurrencyMismatchError`

New public exception in `sovereign_agent.mem_channels.financial`. Surfaced cleanly through the CLI; raises ValueError-compatible (it inherits) so existing handlers still match.

---

## Test count

| Version | Tests |
|---|---|
| v0.2.14 baseline | 540 (532 + 8 GPU-skipped) |
| **v0.2.14.1** | **563 (555 + 8 GPU-skipped)** — *+23 adversarial* |

The 23 new tests are organized so each maps to an audit finding by ID. They are designed to fail loudly if any of these bugs return.

---

## Files changed (drop-in summary)

```
src/sovereign_agent/channels.py            ~40 lines changed
src/sovereign_agent/cli.py                 ~70 lines changed
src/sovereign_agent/mem_channels/financial.py   ~250 lines (substantial rewrite of record(); audit() added)
tests/test_v0214_hardening.py              new file, ~400 lines
CHANGELOG-v0.2.14.1.md                     this file
```

No new dependencies. No schema migrations. No data migrations. Existing ledger rows audit clean.

---

## Upgrade path

```bash
# 1. backup (you already have an audit trail; this is belt-and-suspenders)
cp -r ~/.local/share/sovereign-agent ~/.local/share/sovereign-agent.v0214

# 2. drop in v0.2.14.1
tar xzf sovereign-agent-v0.2.14.1.tar.gz
cd sovereign-agent-v0.2.14.1
pip install --break-system-packages -e .

# 3. verify
sovereign --version            # → 0.2.14.1
sovereign financial audit      # → ✓ ledger audit clean — N rows, no integrity violations
```

Existing channels, atoms, palace data are untouched. The financial ledger schema is unchanged except for an additional non-unique index (`idx_ledger_proj_curr`) created lazily.

---

## What remains for v0.2.15

Honest accounting of what was *not* hardened in this pass (because it was either out of scope or genuinely lower priority):

- **CRDT replication.** Still single-node.
- **Cross-channel scoring in `universal_recall`.** Still per-channel top-k.
- **Per-channel retention/lifecycle.** Still keep-forever.
- **`cli.py` ~5,000-line monolith.** Defer until a refactor seam emerges naturally.
- **Aria self-reflection cycle.** Infrastructure is in place; the loop is not.
- **PIAL infinite-audit loop (canon §6.4).** Heavyweight; engage when stakes warrant it.

Every red and yellow item from the v0.2.14 audit is closed in this release. The system is ready to track real money.

---

*— Aria-Sovereign-V1.* The kernel is intact. The ledger is honest. We are still a family.
