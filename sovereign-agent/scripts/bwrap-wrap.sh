#!/usr/bin/env bash
# bwrap-wrap.sh — convenience wrapper for sandboxed tool operations.
# Architecture v1.1 §12. The Python sandbox.build_bwrap_argv() builds the same
# command line programmatically; this script is for ad-hoc shell use.
#
# Usage:
#   AGENT_MODE=oneshot AGENT_HOME=$HOME/.local/share/sovereign-agent \
#     PROJECT_DIR=$HOME/work/myproject ./bwrap-wrap.sh python -c 'import os; print(os.listdir())'

set -euo pipefail

: "${AGENT_HOME:?AGENT_HOME must be set}"
: "${AGENT_MODE:=oneshot}"
: "${PROJECT_DIR:=}"

# Mode-conditional bind for $PROJECT_DIR — third layer of BUSY safety
case "$AGENT_MODE" in
    busy) PROJECT_BIND_FLAG="--ro-bind" ;;
    *)    PROJECT_BIND_FLAG="--bind" ;;
esac

bwrap_args=(
    --ro-bind /usr /usr
    --ro-bind /lib /lib
    --ro-bind /lib64 /lib64
    --ro-bind /etc/resolv.conf /etc/resolv.conf
    --ro-bind /etc/ssl /etc/ssl
    --tmpfs /tmp
    --proc /proc
    --dev /dev
    --bind "$AGENT_HOME/sandbox" "$HOME/work"
    --ro-bind-try /dev/null "$HOME/.ssh"
    --ro-bind-try /dev/null "$HOME/.gnupg"
    --ro-bind-try /dev/null "$HOME/.aws"
    --unshare-pid
    --unshare-uts
    --unshare-ipc
    --unshare-cgroup-try
    --new-session
    --die-with-parent
)

if [[ -n "$PROJECT_DIR" ]]; then
    bwrap_args+=("$PROJECT_BIND_FLAG" "$PROJECT_DIR" "$PROJECT_DIR")
fi

# Network: only for the web_fetch tool, which sets AGENT_NET=1
if [[ "${AGENT_NET:-0}" != "1" ]]; then
    bwrap_args+=(--unshare-net)
fi

exec bwrap "${bwrap_args[@]}" -- "$@"
