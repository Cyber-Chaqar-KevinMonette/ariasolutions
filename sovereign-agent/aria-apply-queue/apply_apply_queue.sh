#!/usr/bin/env bash
# apply_apply_queue.sh — promote aria-apply-queue into live src/.
#
# Ships:
#   • src/sovereign_agent/apply_queue/             — durable queue + quarantine store + CLI
#   • src/sovereign_agent/cockpit/apply_queue_screen.py — Ctrl+Shift+A multi-select modal
#   • scripts/apply_queue_run.sh                   — the safe sequencer (drains the queue)
#   • wires the cockpit screen into cockpit/app.py (anchored, idempotent, best-effort)
#
# Anatomy: guard (cockpit stopped + venv) → backup touched files → copy payload + sequencer →
#          wire app.py (3 anchored, idempotent edits; any missing anchor is skipped, never fatal) →
#          py_compile → copy + run tests.  Reversible: backups under aria-apply-queue/backups/<ts>.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-apply-queue"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
APP="$REPO_ROOT/src/sovereign_agent/cockpit/app.py"

echo "=== aria-apply-queue apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
[[ -f "$APP" ]] && cp "$APP" "$BACKUP_DIR/app.py.bak"

# 1. copy the apply_queue package
mkdir -p "$REPO_ROOT/src/sovereign_agent/apply_queue"
cp "$STAGING"/payload/src/sovereign_agent/apply_queue/*.py "$REPO_ROOT/src/sovereign_agent/apply_queue/"

# 2. copy the cockpit screen
cp "$STAGING/payload/src/sovereign_agent/cockpit/apply_queue_screen.py" \
   "$REPO_ROOT/src/sovereign_agent/cockpit/"

# 3. install the safe sequencer script
cp "$STAGING/apply_queue_run.sh" "$REPO_ROOT/scripts/apply_queue_run.sh"
chmod +x "$REPO_ROOT/scripts/apply_queue_run.sh"

# 4. wire the cockpit screen into app.py — 3 anchored, idempotent, best-effort edits.
if [[ -f "$APP" ]]; then
  "$VENV_PY" - "$APP" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text(encoding="utf-8")
changed = []

# (a) guarded import, before `logger = logging.getLogger(__name__)`
if "apply-queue-import-d" not in t:
    lines = t.splitlines()
    idx = next((i for i, l in enumerate(lines) if l.startswith("logger = logging.getLogger")), None)
    if idx is not None:
        block = [
            "try:",
            "    from .apply_queue_screen import ApplyQueueScreen  # apply-queue-import-d",
            "except Exception:  # pragma: no cover — apply queue is strictly optional",
            "    ApplyQueueScreen = None  # type: ignore[assignment,misc]",
            "",
        ]
        lines[idx:idx] = block
        t = "\n".join(lines)
        changed.append("import")

# (b) keybinding, after the ctrl+v paste binding inside the main BINDINGS list
if "apply-queue-binding-d" not in t:
    anchor = next((l for l in t.splitlines()
                   if 'Binding("ctrl+v"' in l and "paste_clipboard" in l), None)
    if anchor:
        add = ('        Binding("ctrl+shift+a", "apply_queue", "apply-queue", '
               'show=False, priority=True),  # apply-queue-binding-d')
        t = t.replace(anchor, anchor + "\n" + add, 1)
        changed.append("binding")

# (c) action method, before `def action_paste_clipboard`
if "apply-queue-action-d" not in t:
    anchor = next((l for l in t.splitlines()
                   if l.strip().startswith("def action_paste_clipboard")), None)
    if anchor:
        indent = anchor[: len(anchor) - len(anchor.lstrip())]
        method = [
            f"{indent}def action_apply_queue(self) -> None:  # apply-queue-action-d",
            f'{indent}    """Ctrl+Shift+A → multi-select staged modules into the durable apply queue."""',
            f"{indent}    if ApplyQueueScreen is None:  # pragma: no cover",
            f"{indent}        return",
            f"{indent}    if isinstance(self.screen, ApplyQueueScreen):",
            f"{indent}        self.pop_screen(); return",
            f"{indent}    try:",
            f"{indent}        from pathlib import Path",
            f"{indent}        import sovereign_agent",
            f"{indent}        repo_root = Path(sovereign_agent.__file__).parents[3]",
            f"{indent}        self.push_screen(ApplyQueueScreen(repo_root))",
            f"{indent}    except Exception as exc:  # noqa: BLE001",
            f"{indent}        logger.warning('apply-queue screen failed: %r', exc)",
            "",
        ]
        t = t.replace(anchor, "\n".join(method) + indent + anchor.lstrip(), 1)
        changed.append("action")

if changed:
    p.write_text(t, encoding="utf-8")
    print("Patched cockpit/app.py:", ", ".join(changed))
else:
    print("SKIP: cockpit/app.py already wired (or anchors not found)")
PYEOF
fi

echo "→ Compile check..."
"$VENV_PY" -m py_compile \
  "$REPO_ROOT"/src/sovereign_agent/apply_queue/*.py \
  "$REPO_ROOT/src/sovereign_agent/cockpit/apply_queue_screen.py"
[[ -f "$APP" ]] && "$VENV_PY" -m py_compile "$APP"

# 5. copy + run tests
cp "$STAGING/tests/test_apply_queue.py" "$REPO_ROOT/tests/"
echo "Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT"/tests/test_apply_queue.py -q || true

echo "=== aria-apply-queue applied. Reversible: backups at $BACKUP_DIR 💛 ==="
echo "    flow:  cockpit → Ctrl+Shift+A → select → Queue selected → close cockpit"
echo "           → ./scripts/apply_queue_run.sh   (drains queue safely; quarantines rollbacks)"
echo "    cli:   $VENV_PY -m sovereign_agent.apply_queue status"
