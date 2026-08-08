# aria-paste-plus — Workstream B

Right-click / long-text paste in the chat box, exactly as the plan spec'd it.

## What this ships

`src/sovereign_agent/cockpit/app.py` — 3 anchored patches:
- Import `PastePreviewScreen` (new file, same try/except-guarded pattern as
  `CommandPaletteScreen`).
- `RippleInput.on_mouse_down` — right-click (`button == 3`) fires
  `action_paste_clipboard()`, same as Ctrl+V. Confirmed via reading
  Textual's `message_pump.py::_get_dispatch_methods` that this fires
  *alongside* `Input`'s own private `_on_mouse_down` (cursor placement),
  not instead of it — left-click behavior is completely untouched.
- `action_paste_clipboard()` rewritten: multi-line clipboard content no
  longer collapses to one space-joined line. Instead it pushes
  `PastePreviewScreen` — an editable `TextArea` pre-filled with the full
  text, Ctrl+Enter/Send to dispatch as a real turn, Escape/Cancel to back
  out untouched. Single-line content is byte-for-byte unaffected. A new
  `_send_pasted_text()` helper does the dispatch, honoring the same
  slash-command-wins-first rule as `on_input_submitted`.

`src/sovereign_agent/cockpit/paste_preview_screen.py` — new file, mirrors
`CommandPaletteScreen`'s proven `ModalScreen` shape (Escape/q close, lazy
`.app` imports to sidestep any circular-import risk).

## Why not migrate `#input-box` to a `TextArea` wholesale

`on_input_submitted`'s entire dispatch chain — slash commands, tier-3
confirm callbacks, busy-subprocess forwarding, `sov`/`sovereign` prefix
normalization — keys off `Input.Submitted`, which a `TextArea` doesn't
raise. Reworking that whole chain to support a different event flow was
assessed as much higher risk than adding a side path for the one case that
actually needs multi-line editing: a paste. Normal typing is completely
unaffected by this module.

## Tests

`tests/test_patcher.py` (9 tests) — the patch applies cleanly against the
CURRENT live `app.py`, is idempotent, both files compile, the multi-line
check runs before the collapse line, `_send_pasted_text` routes slash
commands correctly, a missing anchor raises `PatchError` (never a silent
no-op).

`tests/test_paste_plus.py` (8 tests, staging only, shadow-copy — legitimate
pre-apply verification, never promoted) / `tests/test_paste_plus_live.py`
(same 8, promoted to live `tests/` after apply, plain imports, zero
`sys.modules` manipulation — the lesson learned twice already this session
in `test_locator_events_fix.py` and `test_security_strip_wire.py`): single-
line paste still collapses and inserts at cursor; multi-line paste opens
the preview screen with newlines intact and does NOT touch the input box;
Send dispatches the (possibly-edited) text and closes the popup; Cancel
discards without dispatching; a pasted block starting with `/` routes
through the slash handler, not the conversation pipeline; right-click on
`#input-box` triggers paste; left-click still behaves normally (regression
guard for the new mouse handler).

Reversible: restore `app.py` from the backup, delete `paste_preview_screen.py`.
