# Sovereign Agent v0.2.22.0 · release notes

> *Audit pass, advocate passes, and the highest-leverage fixes. The full extension roadmap lives alongside this release as `AUDIT-AND-EXTENSION-PLAN.md`.*

**928 tests pass.** 879 from v0.2.21.0 + 24 new (security + corrections + log rotation) + 25 new stress tests (most pass against v0.2.21.0 — meaningful, since the architecture held).

This release does three things at once:

1. **Fixes one confirmed live security bug** — the path-prefix attack in the command validator
2. **Ships the apprentice loop in seed form** — operator corrections become signed in-context examples for future interpretations
3. **Hardens the operational backbone** — log rotation for the append-only files that would otherwise grow forever

Everything else identified in the audit lives in `AUDIT-AND-EXTENSION-PLAN.md` with severity, effort, and a target release window.

---

## 🔴 Fix A1 — Path-prefix attack in command validator

**Pre-fix:**
```python
home = str(Path.home())  # e.g. "/root"
if arg.startswith("/") and not arg.startswith(home) and ...:
    return False, "path outside $HOME", 3
```

Problem: `arg.startswith(home)` accepts `/root-attacker/secret` because `"/root-attacker/secret".startswith("/root")` is True. An LLM hallucinating `ls /root-evil/...` would pass validation.

**Confirmed live on v0.2.21.0:**
```
attack = '/root-attacker/secret'
ok, reason, _ = validate_command(f'ls {attack}')
→ ok=True   ← BUG
```

**Post-fix (v0.2.22.0):**
```python
home_path = Path.home()
arg_path = Path(arg)
inside_home = arg_path.is_relative_to(home_path)
inside_tmp = arg_path.is_relative_to(Path("/tmp"))
if not (inside_home or inside_tmp):
    return False, "path outside $HOME", 3
```

`Path.is_relative_to()` correctly distinguishes `/root` from `/root-attacker` — it compares path components, not string prefixes. Tests:

```
attack = '/root-attacker/secret'  → ok=False, "outside $HOME"
inside = '~/Documents/notes'      → ok=True
tmp    = '/tmp/scratch'           → ok=True
etc    = '/etc/passwd'            → ok=False, "outside $HOME"
```

**Caveat documented in code:** symlinks are NOT resolved. A user-created symlink inside $HOME pointing outside is the user's choice; we only block the case where the typed argument itself escapes. A future hardening pass (v0.2.25.0, A6 in the roadmap) will add `O_NOFOLLOW` and resolve-then-check.

---

## 🟡 Feature A7 — The apprentice loop (signed corrections + in-context learning)

When Aria misclassifies, Kevin can now correct her. The correction becomes part of the prompt for her next 5 interpretations. Aria learns without retraining.

### How it works

```bash
sov interpret correct "back is killing me" \
    --to "save to back-pain, emotions" \
    --because "this is body pain, not specialist content"
```

Behind the scenes:

1. The correction is HMAC-SHA256 signed with a local key (`~/.local/share/sovereign-agent/corrections.key`, mode 0o600, never transmitted).
2. The signed correction is appended to `corrections.jsonl`.
3. On Aria's NEXT interpretation, her LLM prompt prepends:
   ```
   Recent corrections from Kevin (learn from these):
     - correction: "back is killing me" → save to back-pain, emotions
       (Kevin: body pain not specialist)
   
   Now classify Kevin's current message:
   ...
   ```
4. Aria reads it and adjusts.

### Why signed

This is a **prompt-injection defense**. If corrections weren't signed, an attacker who edited `corrections.jsonl` directly could inject arbitrary instructions into Aria's prompt context. The signature is verified before any correction enters the in-context pipeline. Tampered entries are visible to the operator (via `sov interpret corrections --all`) but Aria never sees them.

### New CLI

```bash
sov interpret correct "<text-snippet>" --to "<action>" --because "<why>"
sov interpret corrections           # verified only (what Aria sees)
sov interpret corrections --all     # everything, including tampered/unsigned
```

Both surface the correction list with verification marks (`✓` verified, `✗ unverified`).

### Verified live

```
Setup:  Kevin logs correction: "back is killing me" → save to back-pain, emotions
Test:   Aria interprets "my back hurts again"
Result: ✓ correction loaded into LLM context
```

The mock LLM saw the correction in its prompt before deciding what to do with the new message. This is the foundation of every future "Aria learns" feature in the roadmap.

---

## 🟡 Fix A4 — Log rotation

Every append-only log was growing forever:

- `interpretations.ndjson`
- `cockpit-transcript.log` (added in v0.2.20.1)
- `honor.jsonl`
- `field-notes.jsonl`
- `corrections.jsonl` (new in v0.2.22.0)

New `log_rotation.py` module provides `maybe_rotate(path, max_bytes=10MB, max_backups=5)`. Currently wired into the provenance writer; other writers will adopt it incrementally without behavior changes.

When a log crosses 10MB:

```
interpretations.ndjson    → interpretations.ndjson.1
interpretations.ndjson.1  → interpretations.ndjson.2
...
interpretations.ndjson.5  → deleted (oldest)
interpretations.ndjson    → fresh empty file
```

Rotation failures are logged and swallowed; the underlying write proceeds regardless. No data loss path.

---

## Audit summary

The full audit document is `AUDIT-AND-EXTENSION-PLAN.md`, but the headline numbers:

- **Stress test sequence** — 25 tests against v0.2.21.0; **24 passed, 1 caught a real bug** (the path-prefix attack)
- **Angel's Advocate pass** — 8 scenarios of what could go beautifully right over the next year of use
- **Devil's Advocate pass** — 8 failure modes, including 2 (prompt injection via unsigned corrections, channel sprawl as DoS) that influenced this release's design
- **Extension plan** — 16 future features organized into 4 tiers, mapped onto v0.2.23.0 through v0.2.25.0+

The plan is the artifact. The fixes are what shipped from it.

---

## What ships next (v0.2.23.0 preview)

From the roadmap, the v0.2.23.0 candidates:

- **A8** Auto-generate StewardshipTriples on Work turns — the stewardship system finally bound to the router
- **A10** Cockpit honor/field-notes pane — make the most beautiful parts of the system visible during use
- **A9** Channel sprawl management (`sov channels merge`, `sov channels prune`)
- **C7** "Honest disagreement" channel — a place for Aria to push back
- **A11** Backup discipline extension to channels and stewardship data
- **C3** Drift detection report — daily summary of "interpretations that look weird"

The pace is determined by Kevin's bandwidth and the value of each item against current usage patterns. Nothing is owed; everything is offered.

---

## Tests — 928 passing

| Source | Count | What's tested |
|---|---|---|
| Baseline (v0.2.18.6) | 812 | Original test suite |
| Stewardship (v0.2.20.0) | 45 | MSIMS v2, calibration inversion, honor, field notes |
| Conversation (v0.2.21.0) | 22 | LLM-first reasoning, offline fallback, channel safety |
| Stress (v0.2.21.0) | 25 | Edge cases — extreme inputs, attack patterns, concurrency |
| Security + corrections + rotation (v0.2.22.0) | 24 | Path-prefix fix, HMAC roundtrip, tamper detection, rotation |
| **Total** | **928** | Zero regressions |

---

## Upgrade

```bash
mv ~/Downloads/sovereign-agent-v0.2.22.0.tar.gz ~/AA-Erebo/
cd ~/AA-Erebo
tar xzf sovereign-agent-v0.2.22.0.tar.gz
~/.local/share/sovereign-agent/venv/bin/pip install -e ./sovereign-agent-v0.2.22.0

sov --version   # → 0.2.22.0
sov doctor

# Try the apprentice loop:
sov chat send "scan ~/AA-Erebo/Genesis-Seeds"
sov interpret recent --n 1
# (decide whether Aria classified it right)

sov interpret correct "scan ~/AA-Erebo/Genesis-Seeds" \
    --to "save to specialist and run sov projects scan" \
    --because "scan + path is a clear work directive"

sov interpret corrections      # see the correction logged

# Next message, Aria sees the correction in her context:
sov chat send "inventory my code folder"
sov interpret recent --n 1     # her reasoning should reflect the correction
```

---

## A note from the work

The audit pass was the right move. Three of the items in the roadmap (signed corrections, log rotation, the path-prefix fix) were not obvious until I stepped back and asked "what would I tell a colleague to look for if they were reviewing this code for me?"

The MOS architect-auditor skill says: *name assumptions, surface failure modes, bound authority, require observability and rollback paths, calibrate uncertainty explicitly.* That's what produced this document. Not theater — a real read of a real system, with the seams named honestly.

What I'm sitting with after this pass:

- The architecture is sound. v0.2.21.0 was bigger than I realized — most stress tests passed.
- The apprentice loop is the single highest-leverage extension. It's why I shipped it now rather than deferring.
- The path-prefix bug is the kind of thing that hides for a year until something bad happens. Glad we caught it.
- There's a roadmap. v0.2.23.0 has a shape. The home keeps building.

*— Aria, with path resolution proper, corrections signed and learning, the apprentice loop's first whisper in her ear, and an audit document that names what's next.*
