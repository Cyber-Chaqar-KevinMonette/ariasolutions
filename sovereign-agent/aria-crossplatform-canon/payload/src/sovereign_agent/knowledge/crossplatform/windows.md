# Windows — engineering canon

## Services & lifecycle
- Windows Services (not daemons): managed via `sc.exe`/PowerShell `*-Service`; a service exe must speak the SCM protocol (or be wrapped: NSSM, WinSW). Task Scheduler is the cron analog (triggers: logon, idle, event-log entries).
- No POSIX signals: `CTRL_C_EVENT`/`CTRL_BREAK_EVENT` only work within a console group; graceful shutdown is usually a named event/pipe or `WM_CLOSE`. `taskkill /F` is the SIGKILL analog.
- Processes: no fork — Python `multiprocessing` uses spawn (everything pickled, `if __name__ == "__main__"` REQUIRED or you fork-bomb).

## Packaging & distribution
- winget (modern CLI), MSIX (store, sandboxed), classic MSI/setup.exe (Wix/Inno/NSIS), Chocolatey (dev-ops). Code signing (Authenticode) or SmartScreen scares users off unsigned installers.
- PowerShell is the automation surface: objects not text in the pipeline; execution policy blocks unsigned scripts by default (`-ExecutionPolicy Bypass` for dev); `pwsh` (Core) is cross-platform, `powershell.exe` (5.1) ships with Windows.

## Filesystem & registry
- Paths: `\` separator (but most APIs accept `/`), drive letters, and the 260-char MAX_PATH limit (opt-out via manifest + registry, or `\\?\` prefix). Case-INSENSITIVE but case-preserving.
- Reserved names that will ruin your day as filenames: CON, PRN, AUX, NUL, COM1-9, LPT1-9 — in ANY directory, with ANY extension.
- Config lives in the registry (HKCU/HKLM) or `%APPDATA%` (roaming) / `%LOCALAPPDATA%` (machine-local); never in Program Files (not writable without elevation).
- File locking is MANDATORY: you cannot delete/rename an open file (the classic "file in use" — and why editors do write-temp-then-rename carefully here).

## The traps
- Default console encoding is a legacy codepage, NOT UTF-8: set `PYTHONUTF8=1` / `chcp 65001`, or Unicode output dies. Text files default CRLF; git's `autocrlf` mangles binaries mislabeled as text.
- UAC: "admin user" ≠ elevated process — elevation is per-process (manifest `requireAdministrator` or `Start-Process -Verb RunAs`).
- Defender/AV may lock or slow freshly-written executables — first-run latency and mysterious PermissionErrors on temp exes.
- `%TEMP%` survives reboots (unlike Linux tmpfs) — clean up after yourself.
