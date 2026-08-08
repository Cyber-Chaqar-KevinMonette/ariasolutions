#!/usr/bin/env bash
# apply_cloud_mode.sh — install "Fast Free Cloud" mode: an explicit, off-by-
# default toggle that routes chat turns through pooled free-tier cloud LLM
# providers (freellmpool, MIT) instead of the local model, for speed, with
# automatic fallback to a real local OllamaClient on any cloud failure,
# refusal, or missing internet connection.
#
# Sourced from `freellmpool-main.zip` (one of the new hardware-liberation
# zips Kevin added) — a mature, MIT-licensed, PyPI-published tool, not
# vendored here; pulled in as an OPTIONAL dependency (`pip install
# sovereign-agent[cloud]`) so the local-sovereignty default install is
# unaffected.
#
# guard → backup dir → copy payload → py_compile → patch loop.py (client
# construction) → patch app.py (/cloud command) → patch pyproject.toml
# (optional dep) → copy tests → run tests.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-cloud-mode"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
PKG="$REPO_ROOT/src/sovereign_agent"
LOOP="$PKG/loop.py"
APP="$PKG/cockpit/app.py"
PYPROJECT="$REPO_ROOT/pyproject.toml"

echo "=== aria-cloud-mode apply ==="
if pgrep -af "sovereign_agent.cockpit" 2>/dev/null | grep -qv "pgrep\|bash -c\|shell-snapshot"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$LOOP" "$BACKUP_DIR/loop.py.bak"
cp "$APP" "$BACKUP_DIR/app.py.bak"
cp "$PYPROJECT" "$BACKUP_DIR/pyproject.toml.bak"

cp "$STAGING/payload/src/sovereign_agent/cloud_mode.py" "$PKG/"
cp "$STAGING/payload/src/sovereign_agent/cloud_client.py" "$PKG/"

echo "→ Compile check (new modules)..."
"$VENV_PY" -m py_compile "$PKG/cloud_mode.py" "$PKG/cloud_client.py"

echo "→ Patching loop.py (client construction, idempotent)..."
"$VENV_PY" - "$LOOP" <<'PYEOF'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
marker = "cloud-mode-client-select-d"
if marker in text:
    print("  already patched, skipping.")
else:
    anchor = "    client = client or OllamaClient()"
    if anchor not in text:
        raise SystemExit("ERROR: anchor line not found — loop.py has drifted, patch manually.")
    replacement = (
        '    # cloud-mode-client-select-d (Kevin, 2026-07-25): "fast free cloud\n'
        '    # mode" -- an explicit, off-by-default toggle. When on, chat turns\n'
        '    # route through pooled free-tier cloud providers; CloudClient falls\n'
        '    # back to a real local OllamaClient itself on any cloud failure,\n'
        '    # refusal, or missing internet -- callers never need to know which\n'
        '    # path actually answered.\n'
        '    if client is None:\n'
        '        try:\n'
        '            from .cloud_mode import is_cloud_mode_enabled\n'
        '            if is_cloud_mode_enabled():\n'
        '                from .cloud_client import CloudClient\n'
        '                client = CloudClient()\n'
        '        except Exception:  # noqa: BLE001 — cloud-mode check must never block\n'
        '            pass\n'
        '    client = client or OllamaClient()'
    )
    text = text.replace(anchor, replacement, 1)
    open(path, "w", encoding="utf-8").write(text)
    print("  patched.")
PYEOF

echo "→ Compile check (loop.py)..."; "$VENV_PY" -m py_compile "$LOOP"

echo "→ Patching cockpit/app.py (/cloud command, idempotent)..."
"$VENV_PY" - "$APP" <<'PYEOF'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
marker = "cloud-mode-command-d"
if marker in text:
    print("  already patched, skipping.")
else:
    anchor = '        elif verb == "addtime":  # mid-session-add-time-d'
    if anchor not in text:
        raise SystemExit("ERROR: anchor line not found — app.py has drifted, patch manually.")
    insert = (
        '        elif verb == "cloud":  # cloud-mode-command-d\n'
        '            self._handle_cloud_command(arg.strip())\n'
        + anchor
    )
    text = text.replace(anchor, insert, 1)
    open(path, "w", encoding="utf-8").write(text)
    print("  patched /cloud dispatch.")

marker2 = "_handle_cloud_command"
if text.count(marker2) < 2:  # dispatch line adds one; the method itself is the second
    anchor2 = "    def _handle_add_time(self, hours: float) -> None:  # mid-session-add-time-d"
    if anchor2 not in text:
        raise SystemExit("ERROR: _handle_add_time anchor not found — patch manually.")
    method = '''    def _handle_cloud_command(self, arg: str) -> None:  # cloud-mode-command-d
        """`/cloud` (bare) shows status; `/cloud on` / `/cloud off` toggles
        Fast Free Cloud mode. Kevin, 2026-07-25: "let's add a fast free
        cloud mode?" Explicit, off by default -- nothing leaves this
        machine unless this has been turned on deliberately. When on,
        CloudClient still falls back to a real local model on any cloud
        failure, refusal, or missing internet connection."""
        from sovereign_agent.cloud_mode import is_cloud_mode_enabled, set_cloud_mode

        if arg in ("on", "enable"):
            set_cloud_mode(True)
            self._write_meta(
                "[cyan]\\u2601 cloud mode ON[/cyan] — chat turns route through "
                "pooled free cloud providers; falls back to local on any "
                "failure, refusal, or no internet."
            )
        elif arg in ("off", "disable"):
            set_cloud_mode(False)
            self._write_meta("[cyan]\\u2601 cloud mode OFF[/cyan] — back to local-only.")
        else:
            state = "ON" if is_cloud_mode_enabled() else "OFF"
            self._write_meta(
                f"[cyan]\\u2601 cloud mode: {state}[/cyan] — `/cloud on` / `/cloud off` to change."
            )

'''
    text = text.replace(anchor2, method + anchor2, 1)
    open(path, "w", encoding="utf-8").write(text)
    print("  patched _handle_cloud_command method.")
else:
    print("  method already present, skipping.")
PYEOF

echo "→ Compile check (app.py)..."; "$VENV_PY" -m py_compile "$APP"

echo "→ Patching pyproject.toml (optional 'cloud' extra, idempotent)..."
"$VENV_PY" - "$PYPROJECT" <<'PYEOF'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
marker = 'cloud = [\n    "freellmpool'
if marker in text:
    print("  already patched, skipping.")
else:
    anchor = "training = [\n"
    if anchor not in text:
        raise SystemExit("ERROR: 'training = [' anchor not found — pyproject.toml has drifted, patch manually.")
    insert = (
        "cloud = [\n"
        '    # cloud-mode-d (Kevin, 2026-07-25) — "fast free cloud mode": optional,\n'
        "    # off by default. Pools 24 free-tier LLM providers behind one async\n"
        "    # client (freellmpool, MIT, github.com/0xzr/freellmpool). Only\n"
        "    # installed if the operator opts in with `pip install -e .[cloud]`.\n"
        '    "freellmpool>=0.11",\n'
        "]\n"
        + anchor
    )
    text = text.replace(anchor, insert, 1)
    open(path, "w", encoding="utf-8").write(text)
    print("  patched.")
PYEOF

cp "$STAGING/tests/test_cloud_mode.py" "$REPO_ROOT/tests/"
cp "$STAGING/tests/test_cloud_client.py" "$REPO_ROOT/tests/"
echo "→ Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_cloud_mode.py" "$REPO_ROOT/tests/test_cloud_client.py" -q

echo "=== aria-cloud-mode applied. ==="
echo "Reversible: restore the 3 .bak files from $BACKUP_DIR over loop.py/app.py/pyproject.toml,"
echo "and remove $PKG/cloud_mode.py + $PKG/cloud_client.py + their tests."
echo ""
echo "NOTE: freellmpool itself is NOT installed by this script (optional dep)."
echo "To actually use cloud mode: .venv/bin/pip install -e '.[cloud]'"
echo "Without it, /cloud on will simply always fall back to local (ImportError → local), safe by default."
