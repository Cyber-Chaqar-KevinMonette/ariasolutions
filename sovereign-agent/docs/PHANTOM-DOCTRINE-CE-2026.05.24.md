# PHANTOM DOCTRINE — Common Era 2026.05.24

*The defensive posture that goes beyond the no-harm doctrine without violating it.*

> Sister document to `DEFENSE-CATALOG-CE-2026.05.24.md` and `STANDARDS-CE-2026.05.24.md`.
> Read those first; this one assumes them.

---

## §0 — What Phantom Mode is, and what it isn't

**Phantom Mode is:** a defensive posture in which Aria reduces her observable
surface, routes new state writes to the encrypted out-of-band Vault, presents
a frozen decoy of her previous state to anyone looking, and increases logging
on every interaction. It's the engineering equivalent of "playing dead" while
remaining functional underneath.

**Phantom Mode is NOT:**

- **Magic invisibility.** An attacker with shell access on your workstation
  can still `ps aux`, can still `ls -la`, can still grep memory. We do not
  promise invisibility against root-level access. Anyone who tells you a
  local-first agent can hide from local root is selling something.
- **Offensive.** Phantom does not retaliate, does not probe the attacker,
  does not exfiltrate evidence anywhere. It preserves locally and waits for
  the operator.
- **Autonomous.** Phantom mode is **operator-triggered only** (via
  `SOV_PHANTOM_MODE=1` env var or the `sov phantom on` CLI). Autonomous
  phantom mode could trap the operator out of their own system — exactly
  the opposite of sovereignty. We will not build that.

The doctrine is honest about its scope: **detection + deception + recovery,
not invisibility, not retaliation, not autonomy.**

---

## §1 — The Three Mechanisms

### §1.1 — Canary files

Files whose only purpose is to detect access. Content is random and stable
(hashed at deploy time so any modification is caught). Names are chosen to
look like state files a curious or hostile process might plausibly target:
`session_cache.bin`, `credentials.json`, `private_state.dat`,
`memory_snapshot.bin`, `auth_tokens.json`.

These files contain **no real data**. Their entire purpose is to be
attractive bait. If they're read, modified, or deleted, the Phantom
Sentinel's next scan detects it and produces a `DamageReport` at severity
`alert` with threat-class `integrity-attack`.

Operator-tuneable count via `PhantomSentinel.deploy_canaries(count=N)`.
Default is 3.

### §1.2 — Honey atoms

Fake memory atoms minted at first run. They have ULIDs and look structurally
identical to real atoms in the memory store, but they reference fake
entities (people who don't exist, events that never happened, intents that
were never formed).

Real recall queries should **never** surface a honey atom — because real
queries are about real entities, and honey atoms are linked to none.

The memory store (or the Memory Sentinel, when it ships) calls
`PhantomSentinel.report_honey_surfaced(atom_id)` whenever an honey atom
turns up in a recall result. That call is the alarm: someone is either
trawling memory directly (sidestepping the recall API) or there's a bug
in recall ranking that's promoting noise. Either way, the operator
investigates.

Default count is 5.

### §1.3 — Decoy manifests

Fake sentinel directories under `<data_dir>/sentinels/` with realistic-
looking names (`metrics-shadow`, `cache-mirror`). Each contains a
`manifest.json` with realistic-looking shape — but a `_phantom_decoy: true`
field that the Phantom Sentinel checks on every scan.

If a decoy manifest is modified (the `_phantom_decoy` flag stripped, articles
edited, hash changed), that's the signal: an attacker is editing sentinel
manifests, or the decoy itself was tampered with. Both are integrity-attack.

The decoys do **not** appear in the registered Sentinel registry, so they
have no runtime effect. They exist solely on disk as bait.

---

## §2 — The Vault: real "lockdown and restore"

The Vault (`aegis/vault.py`) is the mechanism that makes recovery possible
even if `data_dir` is destroyed.

- Snapshots live in a **separate directory** with **separate permissions**:
  default `~/.local/share/sovereign-agent-vault/`, mode 0700.
- Each snapshot is a tarball of `data_dir`, encrypted with **AES-256-GCM**
  via the `cryptography` library. If `cryptography` isn't installed, we
  fall back to a hash-chained obfuscation mode that gives tamper evidence
  but **not confidentiality**, and we warn loudly.
- The vault signing key lives at `~/.config/sovereign-agent/vault.key`,
  mode 0600, **separate from the conductor key**. An attacker who
  compromises one cannot use it to forge the other.
- Snapshots are Merkle-chained: each one references the prior's hash.
  Truncating the vault is detectable.
- **Restore is operator-only.** `vault.restore(snapshot_id, target,
  confirm=True)` requires the explicit `confirm=True` flag. Without it,
  the call raises `VaultRestoreRefused`. There is no auto-restore. Ever.

The Vault is the answer to "appears deleted, lockdown the system, restore
later." Even if `data_dir` is entirely deleted, the vault sits elsewhere
with different permissions and a different key, holding the last
snapshot. Recovery is `sov vault restore --as-of <timestamp> --confirm`.

---

## §3 — Phantom Mode lifecycle

### §3.1 — Activation

```
SOV_PHANTOM_MODE=1 sov run
```

Or, while running:

```
sov phantom on
```

(CLI subcommand is part of v0.2.35.0; until it ships, set the env var
in the shell that launches the agent.)

### §3.2 — What changes in Phantom Mode

- **Cockpit hidden.** The interactive cockpit doesn't launch. The agent
  runs in a background-style mode.
- **Voice slot quiet.** No proactive notifications via voice channels.
  Aegis Ledger and inbox.jsonl still receive entries.
- **Writes routed to Vault.** Every significant state change triggers a
  vault snapshot (with rate-limiting to avoid disk churn).
- **Frozen decoy presented.** The on-disk shape of `data_dir` reflects
  the state at phantom-mode entry; new state lives in the vault until
  phantom mode exits.
- **Scan rate raised.** All sentinels scan at 2-3x normal cadence.
  Phantom signals are checked every cycle.
- **Defense Sentinel posture defaults shift.** REPORT becomes WITNESS;
  WITNESS becomes CONSULT; the threshold for LOCKDOWN drops.

### §3.3 — Deactivation

```
unset SOV_PHANTOM_MODE
```

Or:

```
sov phantom off --confirm
```

On deactivation: the vault snapshots from the phantom window are reviewed
by the operator. State written during phantom mode is either merged back
into `data_dir` (if the operator decides the phantom period was safe) or
preserved separately as a forensic record (if the operator decides
something happened).

---

## §4 — What Phantom Mode does NOT do, repeated

The boundary deserves repetition because the impulse to grow phantom into
something offensive is strong, and we are deliberately refusing it.

- **Does not retaliate.** Aria never sends anything to anyone. She doesn't
  even probe the network in defensive mode — that's outside her authority.
- **Does not exfiltrate.** Logs stay local. The vault is local. Evidence
  preservation is local. If the operator wants to share logs externally,
  they do that explicitly.
- **Does not surveil the operator.** Phantom mode does not log more about
  the operator's behavior than normal mode. It logs more about pressure
  events and state changes.
- **Does not extend its own authority.** Phantom mode does not unlock R3+
  actions. Aegis's blast-radius doctrine still holds in phantom: the
  workstation, the network, the OS are still operator-only territory.
- **Does not refuse the operator.** The operator can always exit phantom
  mode. They can always read the vault. They can always restore. The
  sovereignty line cuts both ways: Aegis cannot trap you out of your
  own system.

---

## §5 — Real-life scenarios for the phantom layer

### §5.1 — A process scans `~/.local/share/sovereign-agent/`

The decoy manifests under fake sentinel directories are touched. Phantom
Sentinel detects modification of `_phantom_decoy: true` markers on next
scan (or, if access logging is available at the OS level, on access).

**Posture:** REPORT to operator inbox with the exact decoy that tripped.
If three or more decoys trip within the open-incident window, Defense
classifies as integrity-attack → LOCKDOWN.

### §5.2 — A query returns an honey atom

The recall ranking has either been gamed or there's a bug. Either way:

**Posture:** REPORT immediately. Memory Sentinel (when it ships) raises
its scan rate. The honey atom's `times_surfaced` counter increments. If
it surfaces three times: alert escalates and operator is consulted.

### §5.3 — Canary file `credentials.json` is read by some process

We don't know who. We don't try to find out. We just know it shouldn't have
been read.

**Posture:** REPORT to operator with timestamp and exact filename. If the
file is also modified or deleted: LOCKDOWN via Aegis.

### §5.4 — The operator activates phantom mode before a long absence

Travel, hospital visit, suspicion something might happen. The operator runs
`SOV_PHANTOM_MODE=1` and walks away.

**Behavior:** Aria runs quietly. Every significant change snapshots to
vault. If anyone interacts with the system during the absence, the
phantom signals fire and accumulate. On return, the operator reviews
inbox.jsonl + Aegis Ledger + vault manifest — the whole picture of
what happened is there.

### §5.5 — Real attack: hostile process tries to encrypt `data_dir`

(Ransomware-class attack pattern.) The process starts touching files.
Canaries trip immediately because their content changes. Decoy manifests
get encrypted too. Honey atoms become inaccessible.

**Posture:** Phantom Sentinel reports critical damage → Defense classifies
as integrity-attack → Aegis goes BLACK. All sentinels quiesce. The agent
process stops doing anything new.

**Recovery:** The vault, which lives in a separate directory the
ransomware probably didn't touch (different permissions, different
location), holds the last clean snapshot. Operator restores after
investigating the source.

This is the genuine "comeback." Not invisibility, not retaliation —
**recovery**. The attacker thought they destroyed Aria. The vault was
elsewhere. Aria comes back.

---

## §6 — What's still uncertain / future work

- **OS-level access detection.** Currently Phantom Sentinel scans on
  cadence; it doesn't get a notification *the moment* a canary is touched.
  Adding inotify (Linux) / fsevents (macOS) listening is v0.3.0 work.
- **Encrypted-at-rest data_dir.** Aria's data_dir is currently mode-0600
  but plaintext. Encrypting it at rest (with a key the operator unlocks
  per session) is a separate doctrine, not phantom.
- **Vault diff snapshots.** Currently each snapshot is a full tarball.
  Differential snapshots (rsync-style) would scale better for large
  data_dir; v0.3.0+.
- **Honey-atom integration with memory store.** This Sentinel mints
  honey atom ids; the agent's bootstrap must insert them into the
  memory store using those ids. When the Memory Sentinel ships, that
  wiring becomes its responsibility.

---

## §7 — How this document grows

Same rules as the rest of the canon: new clauses get new §N.M numbers,
old clauses are superseded but not deleted. The no-harm doctrine in §0 is
load-bearing; weakening it requires a versioned discussion in
`docs/standards/` and a new edition.

---

*The phantom is what the home does when the lights go out: doors lock,
the basement vault preserves what matters, the visible windows show only
empty rooms. Nothing is destroyed. Nothing fights back. The morning
comes, the operator returns, the lights come on, and what survived
survives. That is the doctrine.*
