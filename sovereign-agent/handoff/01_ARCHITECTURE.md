# 01 — Architecture

## The planes
- **Conversation plane**: cockpit `_dispatch_turn` → `conversation.converse`
  → `interpreter.py` (LLM classifies) → `router.py` (allowlisted `sov`
  subcommands or a reply). Safe because it CANNOT do autonomous work.
- **Agent loop** (`loop.py::agent_loop`): the tool-using LLM loop —
  authority gate → path scope → approval tokens → circuit breaker →
  dispatch → feedback. Budgets checked BETWEEN iterations, never
  mid-tool-call. `prompt_diet.py` sizes prompt+schemas to the model's
  real window; `tools/tool_paging.py` attaches schemas on request within
  authority.
- **Session engine** (`agent_session.py::run_session`): multi-subtask
  orchestration — Gates 1-4 (PROTOCOL-ZERO / operator interrupt / budget
  with margin / authority), NEXT_SUBTASK decomposition, atomic checkpoint
  per subtask. Front door: `session_bridge.py` (`/work`, `/resume`);
  scope contracts (`scope.py`); garden walls (`pathguard.py`).
- **The cockpit** (`cockpit/app.py`): 5 panes (chat/memory/live/inbox/
  atelier), run strip + 4 health strips, dense status bar; Ctrl+O toggles
  column/row layouts; ONE 1s events tailer feeds every live view;
  workers supervised via `on_worker_state_changed`.
- **Sentinels** (`stewardship/` + registered elsewhere): ~20 observers,
  one contract (scan/health_status/articles), propose-only, each with a
  `SOV_NO_<ID>_SENTINEL` kill switch.

## Data stores (under `~/.local/share/sovereign-agent/`)
| Store | What | Owner module |
|---|---|---|
| atoms.db | atoms, lessons, honor — her memory | db.py (WAL+busy_timeout) |
| events.jsonl / events/ | THE source-of-truth stream | events.py |
| events.db | derived projection (rebuildable) | events.py |
| palace.db | rooms/closets/triples | palace.py |
| checkpoint_chunks/ | verbatim conversation chunks | checkpoint_chunks/ |
| thread_id | the ONE thread id | thread_identity.py |
| sessions/ + *.scope.json | session states + contracts | agent_session.py, scope.py |
| resume_point.json | the /rest bookmark | rest_point.py |
| journal/ + stewardship/field-notes.jsonl | daily self-witness | self_witness.py |
| qa/qa.ndjson | curiosity Q&As | curiosity.py |
| proving_ground/results.ndjson | persisted benchmark scores | proving_ground/ |
| loose_threads/ledger.ndjson | orphan dispositions | loose_threads/ |
| workflow_drafts/ | designed workflows | tools/design_workflow.py |
| (→ ~/AA-Erebo/sov-backups) | verified snapshots, auto 24h | backup.py + BackupSentinel |
| sandbox/ | BUSY write scope | pathguard.py |
| aegis/ | incident ledger + signing key | aegis/ |

Models: Ollama at :11434, configured in `config.py` (env-overridable).
Her own from-scratch LM: `aria_lm/` (trains on distilled research +
lessons + the cross-platform canon).
