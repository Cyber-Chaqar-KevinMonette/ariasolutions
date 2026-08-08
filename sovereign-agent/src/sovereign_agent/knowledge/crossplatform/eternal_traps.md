# The eternal traps — cross-platform pitfalls that never die

## Paths
- Build with `pathlib`/`os.path.join`, never string concat with `/` or `\`.
- Case sensitivity is a SPECTRUM: Linux sensitive, Windows+macOS insensitive-but-preserving — `Foo.py` and `foo.py` are one file on two of three platforms; imports that differ only by case break on checkout.
- Home is `Path.home()`, temp is `tempfile.gettempdir()` — never literal `/tmp` or `C:\Temp`. MAX_PATH (260) still bites deep node_modules-style trees on Windows.

## Encodings
- `open()` without `encoding=` uses the locale — UTF-8 on Linux/macOS, legacy codepage on Windows. ALWAYS pass `encoding="utf-8"` (or run Python with `PYTHONUTF8=1`).
- Filenames: bytes on Linux, UTF-16 on Windows, NFD-normalized UTF-8 on macOS — normalize (`unicodedata.normalize("NFC", name)`) before comparing.

## Line endings
- LF vs CRLF: `.gitattributes` (`* text=auto eol=lf`) beats every per-developer `autocrlf` setting. Shebangs and shell scripts MUST be LF. Write network protocols with explicit `\r\n` where specs demand it, never platform default.

## Time
- Store UTC, render local, never parse local-time strings without a zone. Windows has no `time.tzset`; timezone data differs (use `zoneinfo`/tzdata package). Monotonic clocks (`time.monotonic`) for durations — wall clocks jump (NTP, DST).

## Processes & concurrency
- fork exists only on POSIX; spawn is the portable model — module-level side effects run in every child; guard entry points.
- File locking: advisory `flock` (POSIX) vs mandatory locks (Windows) — the portable pattern is lock FILES (create-exclusive `O_EXCL`) or a lock library, plus write-temp-then-`os.replace` (atomic on all three).
- Killing process trees: POSIX process groups vs Windows Job Objects — `psutil` papers over it.

## CI as the truth
- A matrix (ubuntu/windows/macos × supported runtimes) is the ONLY way cross-platform claims stay true; "works on my machine" decays in weeks. Cache per-OS. Run the encoding/path tests everywhere, not just on Linux runners.

## Detection idioms
- `sys.platform` → `linux` / `win32` / `darwin`; `platform.machine()` for arch (arm64 vs x86_64). Feature-detect over platform-detect where possible (`hasattr(os, "fork")`).
