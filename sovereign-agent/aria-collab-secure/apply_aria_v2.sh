#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_aria_v2.sh — install the full agentic + collaboration + security drop
#  (v0.2.36.0)  Idempotent. Safe to re-run. SUPERSEDES the first
#  aria-agentic.tar.gz (apply this one on a clean cli.py).
#
#  Adds / updates:
#    • workflow/capabilities.py     (registry, gaps, variant routing — incl.
#                                    shipped flow variants like shell.git)
#    • workflow/evolving_run.py     (orchestrator; files inbox requests on pause)
#    • workflow/requests.py         (📬 collaboration inbox)
#    • workflow/agentic_loop.py     (+ append_step)
#    • security/__init__.py
#    • security/vault.py            (🔐 owner-controlled encryption at rest)
#    • tests/test_capabilities.py, test_requests.py, test_vault.py
#    • cli.py                       (sov agentic | capabilities | requests | vault)
#    • pyproject.toml               (+ cryptography dependency)
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAYLOAD="$HERE/payload"

# ── locate repo root (dir containing src/sovereign_agent/cli.py) ────────────
ROOT="${1:-$PWD}"
if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    if [[ -f "$d/src/sovereign_agent/cli.py" ]]; then ROOT="$d"; break; fi
    d="$(dirname "$d")"
  done
fi
if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  echo "✗ could not find src/sovereign_agent/cli.py."
  echo "  run from your sovereign-agent repo root, or: bash apply_aria_v2.sh /path/to/repo"
  exit 1
fi
echo "◊ repo root: $ROOT"

PKG="$ROOT/src/sovereign_agent"
WF="$PKG/workflow"
SEC="$PKG/security"
CLI="$PKG/cli.py"
PYPROJECT="$ROOT/pyproject.toml"

# ── 1. module files ─────────────────────────────────────────────────────────
echo "→ installing workflow modules"
cp "$PAYLOAD/src/sovereign_agent/workflow/capabilities.py" "$WF/capabilities.py"
cp "$PAYLOAD/src/sovereign_agent/workflow/evolving_run.py" "$WF/evolving_run.py"
cp "$PAYLOAD/src/sovereign_agent/workflow/requests.py"     "$WF/requests.py"
cp "$PAYLOAD/src/sovereign_agent/workflow/agentic_loop.py" "$WF/agentic_loop.py"
echo "  ✓ capabilities.py  evolving_run.py  requests.py  agentic_loop.py"

echo "→ installing security module"
mkdir -p "$SEC"
cp "$PAYLOAD/src/sovereign_agent/security/__init__.py" "$SEC/__init__.py"
cp "$PAYLOAD/src/sovereign_agent/security/vault.py"    "$SEC/vault.py"
echo "  ✓ security/__init__.py  security/vault.py"

echo "→ installing tests"
cp "$PAYLOAD/tests/test_capabilities.py" "$ROOT/tests/test_capabilities.py"
cp "$PAYLOAD/tests/test_requests.py"     "$ROOT/tests/test_requests.py"
cp "$PAYLOAD/tests/test_vault.py"        "$ROOT/tests/test_vault.py"
echo "  ✓ test_capabilities.py  test_requests.py  test_vault.py"

# ── 2. pyproject: add cryptography dependency (idempotent) ──────────────────
if [[ -f "$PYPROJECT" ]] && grep -q 'cryptography' "$PYPROJECT"; then
  echo "→ pyproject already lists cryptography — skipping"
elif [[ -f "$PYPROJECT" ]]; then
  echo "→ adding cryptography to pyproject dependencies"
  PYPROJECT="$PYPROJECT" python3 - <<'PY'
import os, re
p = os.environ["PYPROJECT"]
s = open(p, encoding="utf-8").read()
# insert after the textual pin inside the core dependencies list
anchor = re.search(r'(\n\s*"textual>=[^"]*",)', s)
if anchor:
    ins = anchor.group(1) + '\n    "cryptography>=42.0",'
    s = s[:anchor.start()] + ins + s[anchor.end():]
else:
    # fallback: add to the first dependencies = [ ... ]
    s = re.sub(r'(dependencies\s*=\s*\[)', r'\1\n    "cryptography>=42.0",', s, count=1)
open(p, "w", encoding="utf-8").write(s)
print("  ✓ cryptography added")
PY
fi

# ── 3. splice CLI commands into cli.py (idempotent + partial-state guard) ───
if grep -q 'name="vault"' "$CLI"; then
  echo "→ cli.py already has the full command block — skipping splice"
elif grep -q 'name="agentic"' "$CLI"; then
  echo "✗ cli.py has a PARTIAL earlier install (agentic present, vault missing)."
  echo "  This looks like the first aria-agentic.tar.gz was applied."
  echo "  Restore the cli.py backup it made, then re-run this script:"
  echo "      ls $PKG/cli.py.bak.*"
  echo "      mv $PKG/cli.py.bak.<newest> $CLI"
  exit 1
else
  echo "→ splicing 'sov agentic | capabilities | requests | vault' into cli.py"
  cp "$CLI" "$CLI.bak.$(date +%Y%m%d%H%M%S)"
  BLOCK="$PAYLOAD/cli_agentic_block.py" python3 - "$CLI" <<'PY'
import os, sys
cli_path = sys.argv[1]
block = open(os.environ["BLOCK"], encoding="utf-8").read().rstrip() + "\n\n\n"
src = open(cli_path, encoding="utf-8").read()
marker = 'if __name__ == "__main__":'
idx = src.rfind(marker)
new = (src[:idx] + block + src[idx:]) if idx != -1 else (src.rstrip() + "\n\n\n" + block)
open(cli_path, "w", encoding="utf-8").write(new)
print("  ✓ inserted command block before entrypoint")
PY
fi

# ── 4. compile check ────────────────────────────────────────────────────────
echo "→ compile check"
python3 -m py_compile \
  "$WF/capabilities.py" "$WF/evolving_run.py" "$WF/requests.py" "$WF/agentic_loop.py" \
  "$SEC/__init__.py" "$SEC/vault.py" "$CLI" \
  "$ROOT/tests/test_capabilities.py" "$ROOT/tests/test_requests.py" "$ROOT/tests/test_vault.py"
echo "  ✓ all files compile"

echo
echo "✓ done. next:"
echo "    source .venv/bin/activate          # if not already"
echo "    pip install -e '.[dev]'            # pulls in cryptography (new dep)"
echo "    pytest -q                          # expect: 1598 passed, 1 skipped"
echo
echo "  try it out:"
echo "    sov capabilities                   # subsystems, gaps, flow variants"
echo "    sov agentic \"set up a python project skeleton\" --plan"
echo "    sov requests                       # the collaboration inbox 📬"
echo "    sov vault init                     # set YOUR owner passphrase 🔐"
