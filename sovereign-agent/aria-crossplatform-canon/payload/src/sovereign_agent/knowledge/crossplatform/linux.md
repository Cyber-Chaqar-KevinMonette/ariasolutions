# Linux — engineering canon

## Services & lifecycle
- systemd is the init: units in `/etc/systemd/system/` (admin) or `~/.config/systemd/user/` (user services — no root, die at logout unless `loginctl enable-linger`). `Type=simple|forking|notify|oneshot`; `Restart=on-failure` + `RestartSec` for daemons; `journalctl -u <unit> -f` for logs.
- Signals are the contract: SIGTERM = graceful stop (handle it, flush, exit), SIGKILL = unstoppable, SIGHUP conventionally = reload config. A daemon that ignores SIGTERM gets SIGKILLed after `TimeoutStopSec` (default 90s).
- cron vs systemd timers: timers get logging, jitter (`RandomizedDelaySec`), dependencies, and catch-up (`Persistent=true`) — prefer them for anything that matters.

## Packaging
- deb (apt, Debian/Ubuntu) and rpm (dnf, Fedora/RHEL) are distro-native; Flatpak is sandboxed desktop apps (portals for filesystem access); AppImage is a self-contained single file (no install, no auto-update by default); snap auto-updates (and can't be told not to, only deferred).
- Python apps: never `pip install` into the system Python (PEP 668 marks it externally-managed) — venv or pipx, always.

## Filesystem & FHS
- Config in `~/.config/<app>/` (XDG_CONFIG_HOME), data in `~/.local/share/<app>/` (XDG_DATA_HOME), caches in `~/.cache/<app>/` — honor the env overrides, never hardcode.
- Case-SENSITIVE filesystems (ext4/btrfs). `~` expansion is the shell's job, not the kernel's — `os.path.expanduser` in code.
- File locking: `fcntl.flock` is advisory (both parties must opt in); NFS breaks it in old versions.

## The traps
- Line endings LF; a CRLF shebang (`#!/usr/bin/env python\r`) fails with "bad interpreter" — the single most common cross-platform script bug.
- `/tmp` is often tmpfs (RAM, cleared at boot) and can be per-user-namespaced; XDG runtime dir (`/run/user/<uid>`) for sockets.
- Executable bit matters (`chmod +x`); zip archives from Windows lose it.
- glibc vs musl (Alpine): binary wheels built for glibc (manylinux) don't run on musl — pick `musllinux` wheels or build from source.
