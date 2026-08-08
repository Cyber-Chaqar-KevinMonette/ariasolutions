#!/usr/bin/env bash
# sovereign-agent install.sh — uv-first, pip-fallback, idempotent installer.
#
# HAPPY PATH (preferred, deterministic):
#   1. uv is on PATH and working
#   2. `uv sync --no-dev` installs into a managed venv at
#      ${XDG_DATA_HOME:-$HOME/.local/share}/sovereign-agent/venv from uv.lock
#   3. `sov` / `sov-chat` / `sovereign` shims at ~/.local/bin exec the venv
#      interpreter by absolute path
#
# FALLBACK PATH (degraded, loud):
#   - Fires when uv is missing OR `uv sync` exits non-zero
#   - Uses stdlib `python -m venv` + pip to install from pyproject.toml
#   - LOSES lockfile-driven determinism — resolution happens fresh
#   - Writes a marker file the venv at ${MANAGED_VENV}/.install-method so
#     `sov doctor` reports the degraded state forever after
#   - Banners loudly so the operator always knows which path ran
#
# What this script does NOT do:
#   - Install uv (you install package managers yourself; we never do)
#   - Install Python (uv resolves; the fallback uses whatever python3 is on PATH)
#   - Install Ollama (separate, optional)
#   - Touch your data directory
#   - Silently degrade — every fallback is announced
#
# Idempotent. Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EREBO_DIR="${HOME}/AA-Erebo"
CURRENT_SYMLINK="${EREBO_DIR}/sovereign-agent-current"

XDG_DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
XDG_BIN_HOME="${XDG_BIN_HOME:-${HOME}/.local/bin}"
MANAGED_VENV="${XDG_DATA_HOME}/sovereign-agent/venv"
INSTALL_METHOD_FILE="${MANAGED_VENV}/.install-method"

# ─── Colors (only if stdout is a tty) ──────────────────────────────────────
if [[ -t 1 ]]; then
    C_BOLD=$'\033[1m'
    C_GREEN=$'\033[32m'
    C_YELLOW=$'\033[33m'
    C_RED=$'\033[31m'
    C_DIM=$'\033[2m'
    C_RESET=$'\033[0m'
else
    C_BOLD="" C_GREEN="" C_YELLOW="" C_RED="" C_DIM="" C_RESET=""
fi

say()   { printf '%s\n' "$*"; }
ok()    { printf "${C_GREEN}✓${C_RESET} %s\n" "$*"; }
warn()  { printf "${C_YELLOW}⚠${C_RESET} %s\n" "$*"; }
err()   { printf "${C_RED}✗${C_RESET} %s\n" "$*" >&2; }
head1() { printf "\n${C_BOLD}%s${C_RESET}\n" "$*"; }

banner_degraded() {
    cat >&2 <<BANNER
${C_YELLOW}╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║  [!]  DEGRADED MODE -- pip fallback in use                               ║
║                                                                          ║
║  $1
║                                                                          ║
║  Installing via stdlib python + pip instead of uv. The install will     ║
║  succeed, but you LOSE:                                                  ║
║                                                                          ║
║    * lockfile-driven determinism (uv.lock is not consulted by pip)      ║
║    * the fast incremental sync uv gives you on re-runs                  ║
║                                                                          ║
║  ${C_BOLD}sov doctor${C_RESET}${C_YELLOW} will report install method as 'pip-fallback' going        ║
║  forward. To upgrade to the deterministic path:                         ║
║                                                                          ║
║    curl -LsSf https://astral.sh/uv/install.sh | sh                     ║
║    # (start a new shell, then)                                          ║
║    ./install.sh                                                          ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝${C_RESET}
BANNER
}

# ─── Step 1: pyproject.toml sanity ─────────────────────────────────────────

head1 "▸ Install source check"
if [[ ! -f "${SCRIPT_DIR}/pyproject.toml" ]]; then
    err "No pyproject.toml in ${SCRIPT_DIR}"
    err "Are you running install.sh from inside the unpacked sovereign-agent-vX.Y.Z directory?"
    exit 1
fi
INSTALL_VERSION="$(grep -E '^version *= *"' "${SCRIPT_DIR}/pyproject.toml" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')"
ok "Source dir: ${SCRIPT_DIR}"
ok "Version in source: ${INSTALL_VERSION}"

mkdir -p "$(dirname "${MANAGED_VENV}")" "${XDG_BIN_HOME}"

# ─── Step 2: install — try uv first, fall back to pip ─────────────────────

INSTALL_METHOD="uv"
UV_AVAILABLE=false
if command -v uv >/dev/null 2>&1 && uv --version >/dev/null 2>&1; then
    UV_AVAILABLE=true
fi

if [[ "${UV_AVAILABLE}" == "true" ]]; then
    head1 "▸ uv sync (managed venv)"
    UV_VERSION="$(uv --version 2>&1 | awk '{print $2}')"
    ok "uv ${UV_VERSION}"
    SYNC_OUT="$(mktemp)"
    if (
        cd "${SCRIPT_DIR}"
        UV_PROJECT_ENVIRONMENT="${MANAGED_VENV}" uv sync --no-dev --reinstall-package sovereign-agent
    ) >"${SYNC_OUT}" 2>&1; then
        ok "uv sync succeeded · venv → ${MANAGED_VENV}"
        rm -f "${SYNC_OUT}"
    else
        warn "uv sync FAILED. Output:"
        cat "${SYNC_OUT}" >&2
        rm -f "${SYNC_OUT}"
        banner_degraded "Reason: \`uv sync\` exited non-zero. See output above.        ║"
        INSTALL_METHOD="pip-fallback"
    fi
else
    banner_degraded "Reason: \`uv\` is not on PATH (or not executable).               ║"
    INSTALL_METHOD="pip-fallback"
fi

if [[ "${INSTALL_METHOD}" == "pip-fallback" ]]; then
    head1 "▸ pip fallback install"

    # Version check — uv handles requires-python implicitly; we have to do it here
    if ! command -v python3 >/dev/null 2>&1; then
        err "python3 is not on PATH. Install Python 3.11+ and re-run."
        exit 1
    fi
    PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
    PY_OK="$(python3 -c 'import sys; print("1" if sys.version_info >= (3, 11) else "0")')"
    if [[ "${PY_OK}" != "1" ]]; then
        err "sovereign-agent requires Python 3.11+ (found ${PY_VERSION})"
        exit 1
    fi
    ok "Python ${PY_VERSION}"

    # Build / refresh the venv
    if [[ ! -x "${MANAGED_VENV}/bin/python" ]]; then
        python3 -m venv "${MANAGED_VENV}"
        ok "created venv at ${MANAGED_VENV}"
    else
        ok "venv exists at ${MANAGED_VENV}"
    fi

    # Bootstrap pip
    "${MANAGED_VENV}/bin/python" -m pip install --upgrade pip --quiet
    ok "pip upgraded inside the venv"

    # Editable install of the project
    PIP_OUT="$(mktemp)"
    if "${MANAGED_VENV}/bin/pip" install --quiet -e "${SCRIPT_DIR}" >"${PIP_OUT}" 2>&1; then
        ok "pip install succeeded · venv → ${MANAGED_VENV}"
        rm -f "${PIP_OUT}"
    else
        err "pip install FAILED. Output:"
        cat "${PIP_OUT}" >&2
        rm -f "${PIP_OUT}"
        exit 1
    fi
fi

# ─── Step 3: Record which method was used (auditable forever) ──────────────

printf '%s\n' "${INSTALL_METHOD}" > "${INSTALL_METHOD_FILE}"
printf 'installed at: %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" >> "${INSTALL_METHOD_FILE}"
printf 'source version: %s\n' "${INSTALL_VERSION}" >> "${INSTALL_METHOD_FILE}"

# ─── Step 4: Write launcher shims ──────────────────────────────────────────

head1 "▸ Launcher shims"
write_shim() {
    local name="$1"
    local target="${XDG_BIN_HOME}/${name}"
    local target_bin="${MANAGED_VENV}/bin/${name}"
    if [[ ! -x "${target_bin}" ]]; then
        warn "${name} entry point not in venv (skipping shim) — pyproject [project.scripts] may have changed"
        return
    fi
    cat > "${target}" <<SHIM
#!/usr/bin/env bash
# Auto-generated by sovereign-agent install.sh — do not edit.
# Written at install of v${INSTALL_VERSION} (method: ${INSTALL_METHOD}).
# Repair: re-run install.sh from the sovereign-agent source tree.
set -e
VENV="${MANAGED_VENV}"
if [[ ! -x "\${VENV}/bin/${name}" ]]; then
    echo "✗ sovereign-agent venv is missing or broken: \${VENV}" >&2
    echo "  Repair: re-run install.sh from the sovereign-agent source tree." >&2
    exit 127
fi
exec "\${VENV}/bin/${name}" "\$@"
SHIM
    chmod +x "${target}"
    ok "shim → ${target}"
}
write_shim sov
write_shim sov-chat
write_shim sovereign
write_shim sov-mcp

# ─── Step 5: PATH check + version verify ──────────────────────────────────

head1 "▸ Verify version on PATH"
if ! command -v sov >/dev/null 2>&1; then
    err "\`sov\` is not on PATH after install."
    err "Add ${XDG_BIN_HOME} to your PATH:"
    err "    echo 'export PATH=\"${XDG_BIN_HOME}:\$PATH\"' >> ~/.bashrc && exec bash"
    exit 1
fi
SOV_BIN="$(command -v sov)"
ON_PATH_VERSION="$(sov --version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1 || echo "unknown")"
if [[ "$ON_PATH_VERSION" != "$INSTALL_VERSION" ]]; then
    warn "PATH binary version (${ON_PATH_VERSION}) does not match source version (${INSTALL_VERSION})"
    warn "This typically means a stale install elsewhere on \$PATH wins."
    warn "  binary: ${SOV_BIN}"
    warn "If this used to be a pip install, clean it up once:"
    warn "    pip uninstall --break-system-packages sovereign-agent 2>/dev/null || true"
    warn "Then re-run this script."
else
    ok "sov on PATH: ${SOV_BIN} (v${ON_PATH_VERSION})"
fi

# ─── Step 6: Update symlink if AA-Erebo layout is in use ──────────────────

if [[ -d "${EREBO_DIR}" ]]; then
    head1 "▸ AA-Erebo symlink"
    if [[ -L "${CURRENT_SYMLINK}" ]] || [[ ! -e "${CURRENT_SYMLINK}" ]]; then
        ln -sfn "${SCRIPT_DIR}" "${CURRENT_SYMLINK}"
        ok "${CURRENT_SYMLINK} → ${SCRIPT_DIR}"
    else
        warn "${CURRENT_SYMLINK} exists and is NOT a symlink; leaving untouched"
    fi
fi

# ─── Step 7: Run doctor for verification ──────────────────────────────────

head1 "▸ sov doctor"
sov doctor || {
    warn "doctor reported issues; review above. Continuing — many issues are auto-resolvable."
}

# ─── Step 8: Apply migrations (auto-backfills first) ──────────────────────

head1 "▸ sov migrations apply"
sov migrations apply || {
    err "Migration apply failed. Atoms.db may be in an unusable state."
    err "Try: sov doctor"
    exit 1
}

# ─── Step 9: Final summary ────────────────────────────────────────────────

head1 "▸ Install complete"
sov info || true

cat <<EOF

${C_BOLD}Install layout:${C_RESET}
  method → ${INSTALL_METHOD}$([ "${INSTALL_METHOD}" = "pip-fallback" ] && echo " ${C_YELLOW}(degraded; install uv to upgrade)${C_RESET}" || echo "")
  venv   → ${MANAGED_VENV}
  shims  → ${XDG_BIN_HOME}/{sov, sov-chat, sovereign, sov-mcp}
  source → ${SCRIPT_DIR}

${C_BOLD}Next steps:${C_RESET}
  ${C_DIM}# As of v0.2.30.0, \`sov\` and \`sov-chat\` are real binaries —${C_RESET}
  ${C_DIM}# they work in any shell without sourcing aliases.sh.${C_RESET}

  ${C_DIM}#${C_RESET} See what Aria can do
  ${C_DIM}\$${C_RESET} sov --help

  ${C_DIM}#${C_RESET} Talk to her in natural language
  ${C_DIM}\$${C_RESET} sov ask "what's our state?"

  ${C_DIM}#${C_RESET} Confirm the seven commitments are codified
  ${C_DIM}\$${C_RESET} sov constitution list

  ${C_DIM}#${C_RESET} Aria's first heartbeat on this install
  ${C_DIM}\$${C_RESET} sov heartbeat pulse "first pulse on ${INSTALL_VERSION}"

  ${C_DIM}#${C_RESET} Open the cockpit
  ${C_DIM}\$${C_RESET} sov-chat

  ${C_DIM}#${C_RESET} (Optional) Source the rich helper functions
  ${C_DIM}\$${C_RESET} echo "source ${SCRIPT_DIR}/scripts/aliases.sh" >> ~/.bashrc

EOF
