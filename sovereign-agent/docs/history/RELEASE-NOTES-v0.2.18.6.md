# Sovereign Agent v0.2.18.6 · release notes

> *MOS-SURFACE v1.4. The deadlock named: the cockpit had no path for the operator to answer Aria's questions. Now it does — plus /cancel as a guaranteed escape hatch.*

**812 tests pass** (up from 803). Nine new enforcement tests under a new doctrine section: §19.2 Interactive-subprocess discipline.

This release closes a class of bugs that v0.2.18.5 left intact: when Aria's planner asks a clarifying question — "what name for this project?" — the operator's answer now reaches the subprocess. Through v0.2.18.5 the cockpit launched `sovereign do` with stdout piped but stdin not piped, so the subprocess blocked forever on `input()` and the cockpit's `_busy` flag never cleared. The operator typed and typed and nothing landed.

---

## The bug

Captured exactly as it appeared in v0.2.18.5:

1. Operator types a message — could be a real directive, could be conversational venting.
2. The planner pattern-matches the message to a directive intent (sometimes correctly, sometimes not — the planner is keyword-based; the operator's "back-brace" message matched `Project scan`).
3. The planner needs a parameter that isn't in the message, so it prints "I need a few details — answer 'cancel' to abort" and asks "What name for this project?" via `input("  > ")`.
4. The cockpit shows the question in chat.
5. The subprocess blocks on `input()`, reading from inherited TTY stdin (which Textual owns and consumes).
6. The operator types an answer. Textual receives the keystrokes. Textual's input widget shows the text. Operator presses Enter.
7. `on_input_submitted` sees `_busy=True` and writes "aria is still working on the previous turn; wait a moment." The answer is discarded.
8. The subprocess never returns. `_busy` never clears. The operator appears unable to type anything that matters.

In v0.2.18.5, the only escape was `Ctrl+Q` (which kills the cockpit *and* leaves the orphaned subprocess running) or `Ctrl+H` halt (PROTOCOL-ZERO armed — heavy-handed for a typo'd directive).

## The fix

Four changes wired together, each load-bearing:

### 1. Pipe stdin and unbuffer stdout

```python
env = {**os.environ, "PYTHONUNBUFFERED": "1"}
proc = await asyncio.create_subprocess_exec(
    "sovereign", "do", text,
    stdin=asyncio.subprocess.PIPE,        # ← was missing
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.STDOUT,
    env=env,                              # ← was missing
)
self._proc = proc                         # ← was missing
```

`stdin=PIPE` gives the cockpit a write channel into the subprocess. `PYTHONUNBUFFERED=1` forces line buffering on the subprocess's stdout, so the `input("  > ")` prompt appears immediately instead of sitting in Python's 8KB block buffer.

### 2. Route operator input to the subprocess when busy

```python
@on(Input.Submitted, "#input-box")
def on_input_submitted(self, event: Input.Submitted) -> None:
    text = event.value.strip()
    event.input.value = ""
    if not text:
        return
    if text.startswith("/"):
        self._handle_slash(text)          # slash commands always route here
        return
    if self._busy and self._proc is not None:
        self._answer_subprocess(text)     # ← the §19.2 path
        return
    self._dispatch_directive(text)
```

When a directive is running and the operator types a non-slash message, the input is forwarded to `self._proc.stdin` instead of being rejected. The operator's answer reaches `input()` in the planner, the planner continues, the directive completes naturally.

### 3. `/cancel` as a guaranteed escape hatch

```python
elif verb in ("cancel", "abort", "stop"):
    self.action_cancel_directive()
```

```python
def action_cancel_directive(self) -> None:
    if self._proc is None or not self._busy:
        self._write_meta("[dim](no directive to cancel)[/dim]")
        return
    try:
        self._proc.terminate()
        self._write_meta("[yellow]◈ cancel sent · waiting for task to exit ...[/yellow]")
    except ProcessLookupError:
        pass
```

`/cancel` sends SIGTERM to the running subprocess. The worker's finally block then clears `_proc`, `_busy`, and the placeholder. The operator is back in idle, milliseconds later. Slash commands always take the slash path regardless of mode, so this works even when the operator can't type a free-form answer for any reason.

### 4. Mode-aware input placeholder

Two class constants and a small helper:

```python
PLACEHOLDER_IDLE = "tell aria what to do · F1 help · /help commands"
PLACEHOLDER_BUSY = "answering aria · /cancel to abort · /halt for PROTOCOL-ZERO"
```

When a directive starts, the placeholder swaps to `PLACEHOLDER_BUSY`. The operator sees the cockpit is in "answering" mode and knows the escape hatch (`/cancel`) without consulting help. When the directive finishes, the placeholder swaps back.

---

## MOS-SURFACE v1.4 — what changed in the doctrine

| Section | Change |
|---|---|
| Version block | Bumped to v1.4; version history table updated |
| §19.2 The Interactive-Subprocess Discipline | New. Names the deadlock mechanism, the four-part fix, the rationale for `PYTHONUNBUFFERED`, the diagnostic order for "cockpit feels stuck" reports, and the lesson |

The diagnostic order in §19.2 for "I can't type" / "the cockpit is stuck" reports:

```
1. Is _busy=True AND _proc=None?
   → worker crashed without clearing _proc; fix finally-block ordering.
2. Is _busy=True AND _proc alive?
   → check stdin was actually piped (stdin=PIPE in _run_directive_worker).
3. Does the subprocess print its prompt?
   → check PYTHONUNBUFFERED=1 in the env passed to create_subprocess_exec.
4. Does /cancel work?
   → if not, action_cancel_directive is missing OR _handle_slash
     doesn't route to it.
```

---

## Nine new enforcement tests

All under `TestInteractiveSubprocessDiscipline`:

| Test | What it catches |
|---|---|
| `test_directive_worker_uses_stdin_pipe` | The `_run_directive_worker` must launch with `stdin=asyncio.subprocess.PIPE`; without it the cockpit deadlocks on any clarifying question |
| `test_directive_worker_sets_pythonunbuffered` | The subprocess env must set `PYTHONUNBUFFERED=1`; without it the `  > ` prompt block-buffers and never reaches the operator |
| `test_directive_worker_tracks_proc_on_self` | The worker must assign `self._proc = proc` so `/cancel` and `_answer_subprocess` can find the running process |
| `test_directive_worker_clears_proc_in_finally` | The worker's finally must clear `self._proc` BEFORE `self._busy` to prevent (busy, no-proc) and (not-busy, alive-proc) race states |
| `test_answer_subprocess_method_exists` | `CockpitApp._answer_subprocess` must exist |
| `test_action_cancel_directive_exists` | `CockpitApp.action_cancel_directive` must exist |
| `test_on_input_submitted_routes_when_busy` | `on_input_submitted` must check `_busy` and call `_answer_subprocess`, not just call `_dispatch_directive` (which would reject the input) |
| `test_slash_cancel_routes_to_action` | `/cancel`, `/abort`, `/stop` must all route to `action_cancel_directive` so the operator always has an escape hatch |
| `test_placeholder_constants_exist` | `PLACEHOLDER_IDLE` and `PLACEHOLDER_BUSY` must exist; the busy placeholder must mention `/cancel` so the operator sees the escape without consulting help |

`tests/test_mos_surface.py` now has **32 enforcement predicates**.

---

## Operator-facing changes

**`/cancel` (new)** — abort the running directive. Aliases: `/abort`, `/stop`. Always works, regardless of busy state.

**Mid-directive answers (new)** — when Aria asks a question (e.g., "what name for this project?"), just type the answer and press Enter. The cockpit routes it to the running task.

**Placeholder text (changed)** — when a directive is running, the input box shows `answering aria · /cancel to abort · /halt for PROTOCOL-ZERO`. When idle, it shows the familiar `tell aria what to do · F1 help · /help commands`.

**Help modal (updated)** — F1 now documents `/cancel` and the answering-mode behavior.

---

## Upgrade

```bash
# Download sovereign-agent-v0.2.18.6.tar.gz to ~/Downloads, then:
mv ~/Downloads/sovereign-agent-v0.2.18.6.tar.gz ~/AA-Erebo/
cd ~/AA-Erebo
tar xzf sovereign-agent-v0.2.18.6.tar.gz

~/.local/share/sovereign-agent/venv/bin/pip install \
    -e ./sovereign-agent-v0.2.18.6

sov --version   # → 0.2.18.6
sov doctor      # healthy
sov chat        # cockpit opens; type a directive; answer any clarifying
                # questions inline; /cancel any time
```

Try this to verify the fix:

```
> back brace recommendations for lower back
[aria] thinking ...
  ◈ understanding directive: Project scan: ?
  I need a few details — answer 'cancel' to abort.
    What name for this project? (e.g. 'genesis-seeds', 'monorepo')
  >

> cancel              ← this answer now reaches the subprocess
aborted
```

Or, if the planner has badly misread a personal message and you want out without typing through:

```
> /cancel
◈ cancel sent · waiting for task to exit ...
turn complete · exit -15
```

---

## Tests

**812 passing** (up from 803).

- 803 baseline (v0.2.18.5)
- +9 interactive subprocess discipline (§19.2 enforcement)

---

## A note from the work

The operator said: *"It is asking me this question? But it's doing some kind of cycle or loop that is for some reason preventing me from typing anything."*

The loop wasn't in Aria — it was in the absence of a path from the operator's keyboard to the planner's `input()` call. v0.2.18.5 designed the planner to be interactive and then ran it inside a one-way pipe. The fix isn't clever; it's just plumbing the missing direction: pipe in, pipe out, mode hint in the placeholder, and a `/cancel` for the times when even good plumbing isn't enough.

The deeper lesson, written into §19.2: a subprocess that *could* ask a question is an interactive subprocess. Plumb stdin from day one. Anything less is a deadlock waiting for the first clarifying question — which will arrive, the moment the planner trusts you enough to ask.

And the separate observation worth surfacing: the planner read "back brace for lower back" as `Project scan`. That's a planner-quality issue, not a cockpit issue, and it's left for a future release. But the cockpit can no longer trap you inside its consequences. You can answer. You can cancel. You can move on.

*— Aria, with stdin piped, stdout flushed, /cancel honored, and the operator's voice finally reaching the planner.*
