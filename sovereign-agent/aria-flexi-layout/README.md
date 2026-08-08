# aria-flexi-layout

Keys round K2 — Kevin asked whether the live observability windows should
be horizontal instead of vertical. Shipped as a CHOICE: **Ctrl+O** toggles
Layout A (today's 5 side-by-side columns) ↔ Layout B (chat keeps its tall
column left; memory/live/inbox/atelier become full-width stacked rows
right — log lines are wide, and a fifth-of-the-terminal column truncates
them brutally). The preference persists (`config_dir/cockpit_layout.json`)
and is honored on the next boot.

Implementation is pure CSS — a grid on `#main` (chat `row-span: 4` in
column 1; the four panes fill column 2 in compose order; the vertical Rule
dividers hide). The widget tree is untouched, so every pane id, worker,
and test keeps working; RippleFrame (a Horizontal subclass) keeps painting
its ring because Textual's `layout` style overrides the container default.

## Verify / Apply

```
.venv/bin/python -m pytest aria-flexi-layout/tests/test_patcher.py -q
./aria-flexi-layout/apply_flexi_layout.sh
```

Reversible: restore `cockpit/app.py` from the timestamped `backups/` dir.
