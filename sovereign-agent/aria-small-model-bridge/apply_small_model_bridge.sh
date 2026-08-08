#!/usr/bin/env bash
# apply_small_model_bridge.sh — Final-sprint Round 1.
# Wires small_model_bridge.normalize_response() into OllamaClient.chat so
# every model call has its (possibly small-model-mangled) tool calls
# rescued into structured form before the orchestrator sees them.
# guard → backup → copy payload → patch ollama_client (anchored/idempotent)
# → py_compile → copy tests → run tests. Reversible: backups under backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-small-model-bridge"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; OLLAMA="$REPO_ROOT/src/sovereign_agent/ollama_client.py"

echo "=== aria-small-model-bridge apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"; cp "$OLLAMA" "$BACKUP_DIR/ollama_client.py.bak"

# 1. copy payload package
mkdir -p "$REPO_ROOT/src/sovereign_agent/small_model_bridge"
cp "$STAGING"/payload/src/sovereign_agent/small_model_bridge/*.py "$REPO_ROOT/src/sovereign_agent/small_model_bridge/"

# 2. patch OllamaClient.chat (anchored + idempotent)
"$VENV_PY" - "$OLLAMA" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text(encoding="utf-8")
MARK = "small-model-bridge-d"
if MARK in t:
    print("SKIP: ollama_client already patched"); sys.exit(0)
anchor = (
    "                _resp = await self._aclient.chat(**kwargs)\n"
    "                return _resp if isinstance(_resp, dict) else _resp.model_dump()"
)
if t.count(anchor) != 1:
    print(f"ERROR: expected 1 anchor in ollama_client.chat, found {t.count(anchor)}"); sys.exit(1)
new = (
    "                _resp = await self._aclient.chat(**kwargs)\n"
    "                _raw = _resp if isinstance(_resp, dict) else _resp.model_dump()\n"
    "                # small-model-bridge-d — rescue small-model tool calls into structure\n"
    "                try:\n"
    "                    from .small_model_bridge import normalize_response as _smb_norm\n"
    "                    _kt = {tt[\"function\"][\"name\"] for tt in (kwargs.get(\"tools\") or [])\n"
    "                           if isinstance(tt, dict) and isinstance(tt.get(\"function\"), dict)\n"
    "                           and tt[\"function\"].get(\"name\")}\n"
    "                    return _smb_norm(_raw, _kt)\n"
    "                except Exception:  # noqa: BLE001 — the bridge must never break a call\n"
    "                    return _raw"
)
p.write_text(t.replace(anchor, new, 1), encoding="utf-8")
print("Patched ollama_client.py — OllamaClient.chat now bridges small-model tool calls")
PYEOF

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/small_model_bridge/*.py "$OLLAMA"

cp "$STAGING/tests/test_small_model_bridge.py" "$REPO_ROOT/tests/"
echo "→ Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT/tests/test_small_model_bridge.py" -q

echo "=== aria-small-model-bridge applied. Reversible: backups at $BACKUP_DIR 💛 ==="
