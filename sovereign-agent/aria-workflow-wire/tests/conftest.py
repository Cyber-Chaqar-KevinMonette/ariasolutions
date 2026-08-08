"""conftest.py — Make aria-workflow-wire payload importable during pre-apply testing.

We can't simply add to sys.path because sovereign_agent is already loaded from
the live src tree. Instead we extend the tools package __path__ so that
sovereign_agent.tools.workflow_tools resolves from the payload directory.
"""
from __future__ import annotations
from pathlib import Path
import sovereign_agent.tools as _tools_pkg

_payload_tools = (
    Path(__file__).resolve().parents[1]
    / "payload" / "src" / "sovereign_agent" / "tools"
)
_payload_tools_str = str(_payload_tools)
if _payload_tools.exists() and _payload_tools_str not in [str(p) for p in _tools_pkg.__path__]:
    _tools_pkg.__path__.insert(0, _payload_tools_str)
