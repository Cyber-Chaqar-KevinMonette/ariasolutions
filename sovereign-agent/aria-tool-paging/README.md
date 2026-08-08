# aria-tool-paging

Keys round K5 — tool-calling hardening: dynamic tool paging within
authority + helpful unknown-tool refusals.

## The gap

The prompt diet keeps requests inside the 8B model's 8,192-token window by
sending an 18-tool curated core — but discovery without attachment was a
dead end: `list_available_tools` showed ~200 names the model could never
actually call, and a call to any of them (or a one-character typo) got a
bare "REFUSED: unknown tool" with no path forward.

## The fix

- **`request_tools(names)`** (T0, new): the model asks for tools by name;
  the loop attaches their schemas for the rest of the run. **Bounded**
  (≤10 names/call, ≤40 paged tools/run — the schema budget stays inside
  the window) and **authority-safe by construction**: the loop only
  attaches names from the SAME authority meta-list it was built from —
  paging can never smuggle a tool past the tier ceiling (proven by
  `test_paging_never_exceeds_the_authority_gate`: a Tier-2 tool requested
  in BUSY mode never executes). Every attachment emits `tool-paged-d`
  (visible via K1).
- **Helpful refusals**: unknown names get difflib closest-matches; a name
  that EXISTS but isn't attached gets "NOT ATTACHED — call
  request_tools(['name'])". The full chain is proven end-to-end through
  the REAL agent_loop with a scripted client
  (`test_loop_attaches_granted_tools_mid_run`).
- `request_tools` joins the diet's always-visible core — the
  discovery/attachment pair must both be present or the pair is a dead
  end again.

## Verify / Apply

```
.venv/bin/python -m pytest aria-tool-paging/tests/test_patcher.py -q
./aria-tool-paging/apply_tool_paging.sh   # ends by re-running BOTH smoke gates
```

Reversible: restore the 3 files from the timestamped `backups/` dir and
remove `tools/tool_paging.py`.
