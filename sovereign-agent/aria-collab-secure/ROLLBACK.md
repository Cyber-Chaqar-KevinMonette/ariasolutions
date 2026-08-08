# Rollback — agentic + collaboration + security drop (v0.2.36.0)

Additive change. New modules + one method on `agentic_loop.py` + spliced CLI
commands + one new dependency. Low-risk to remove.

## Files added (delete to remove)
- src/sovereign_agent/workflow/capabilities.py
- src/sovereign_agent/workflow/evolving_run.py
- src/sovereign_agent/workflow/requests.py
- src/sovereign_agent/security/__init__.py
- src/sovereign_agent/security/vault.py
- tests/test_capabilities.py
- tests/test_requests.py
- tests/test_vault.py

## Files modified
- src/sovereign_agent/workflow/agentic_loop.py  (added `append_step`)
- src/sovereign_agent/cli.py                     (spliced 4 command groups)
- pyproject.toml                                 (added `cryptography>=42.0`)

## Fast rollback (git)
    git checkout -- src/sovereign_agent/workflow/agentic_loop.py \
                    src/sovereign_agent/cli.py pyproject.toml
    rm -f src/sovereign_agent/workflow/capabilities.py \
          src/sovereign_agent/workflow/evolving_run.py \
          src/sovereign_agent/workflow/requests.py
    rm -rf src/sovereign_agent/security
    rm -f tests/test_capabilities.py tests/test_requests.py tests/test_vault.py

## Manual rollback (no git)
The apply script wrote `src/sovereign_agent/cli.py.bak.<timestamp>` before
splicing. Restore it, delete the new files, and (optionally) remove the
`append_step` method from `agentic_loop.py` (it sits between `write_plan` and
`plan_steps` and is self-contained). Remove the `"cryptography>=42.0",` line
from pyproject if you want the dependency gone.

## Harmless leftovers
- Proposal drafts:  `<data_dir>/proposals/capabilities/*.py`  — never imported;
  delete the folder any time.
- Inbox data lives in the `human_requests` table inside `atoms.db`. To clear it
  without touching anything else:
      sqlite3 "$(python3 -c 'from sovereign_agent.config import SETTINGS; print(SETTINGS.paths.atoms_db)')" \
        "DROP TABLE IF EXISTS human_requests;"
- Vault credential:  `<config_dir>/vault/owner.cred`  — delete to forget the
  owner passphrase (encrypted files become unrecoverable, so only do this if you
  no longer need them).

## Verify after rollback
    pytest -q
