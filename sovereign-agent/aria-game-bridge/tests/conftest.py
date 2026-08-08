"""Test-before-apply path shim (see scripts/lib/aria_conftest.py's docstring
for the general pattern). aria-game-bridge was already applied once before
this session's edits — its payload now differs from live src/ for
game_bridge_client.py and game_place_piece.py — so the shared helper's
default append-to-end-of-__path__ (live wins if both exist) is wrong here;
promote payload to the front so these tests actually exercise the new code,
not a stale live copy.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parents[2] / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

_MODULE_ROOT = pathlib.Path(__file__).parent.parent
# extend_paths() imports sovereign_agent.tools as a side effect, which loads
# LIVE tools/__init__.py -> live game_place_piece.py/game_world_state.py ->
# live game_bridge_client.py — caching the OLD versions in sys.modules
# before we ever get a chance to reorder __path__. Reordering __path__
# afterwards only affects future lookups, not already-cached modules, so
# those stale entries must be evicted explicitly below.
extend_paths(_MODULE_ROOT)

import sovereign_agent  # noqa: E402
import sovereign_agent.tools as _sa_tools  # noqa: E402

_payload_root = str(_MODULE_ROOT / "payload" / "src" / "sovereign_agent")
if _payload_root in sovereign_agent.__path__:
    sovereign_agent.__path__.remove(_payload_root)
    sovereign_agent.__path__.insert(0, _payload_root)

_payload_tools = str(pathlib.Path(_payload_root) / "tools")
if _payload_tools in _sa_tools.__path__:
    _sa_tools.__path__.remove(_payload_tools)
    _sa_tools.__path__.insert(0, _payload_tools)

# Evict anything already cached from the live copy so the next import of
# each name re-resolves through the now-payload-first __path__ above.
for _stale in (
    "sovereign_agent.game_bridge_client",
    "sovereign_agent.tools.game_bridge_connect",
    "sovereign_agent.tools.game_place_piece",
    "sovereign_agent.tools.game_world_state",
    "sovereign_agent.tools.game_action_status",
):
    sys.modules.pop(_stale, None)
