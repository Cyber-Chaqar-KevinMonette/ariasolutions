# aria-one-thread

Keys round K3 — ONE universal continuous conversation thread (the sessions
decision, researched and chosen with Kevin).

## The gap

Her identity layer (atoms/palace/lessons/honor/flaws) was already one
continuous life — but the chunk recorder minted a fresh `cockpit-<uuid4>`
every launch (app.py:1944), orphaning every prior launch's chunks; the
transcript was written but never read back; and nothing restored the
conversation on boot. Closing the cockpit kept her soul and lost the
conversation, every time.

## The fix

- **`thread_identity.py`** (new): `thread_id()` — the one persisted id
  (`data_dir/thread_id`, default `aria-main`, created on first read);
  `restore_tail(n)` — the last N verbatim turns from the thread's sealed
  chunks (chunks are non-lossy by design, which is what makes a byte-true
  restore possible). Both never raise.
- **3 anchored app.py patches**: the recorder uses the persisted id (uuid
  fallback kept); the wake sequence renders "──── earlier, from our thread
  ────" + the last ~30 turns (Rich-escaped, dimmed, best-effort); the
  transcript line carries the thread id — one join key across
  chunks/transcript/(K4's) sessions.

Named sessions stay an optional future overlay (the dormant Ereblo `chats`
schema is built for that day); folder/project scoping stays reserved for
genuine folder work. One relationship, one thread.

## Verify / Apply

```
.venv/bin/python -m pytest aria-one-thread/tests/test_patcher.py -q
./aria-one-thread/apply_one_thread.sh
```

Reversible: restore `cockpit/app.py` from the timestamped `backups/` dir
and remove `thread_identity.py` (the `data_dir/thread_id` file is inert).
