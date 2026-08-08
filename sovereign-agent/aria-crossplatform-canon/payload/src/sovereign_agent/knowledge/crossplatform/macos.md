# macOS — engineering canon

## Services & lifecycle
- launchd is the one init: LaunchAgents (`~/Library/LaunchAgents`, per-user, GUI session) vs LaunchDaemons (`/Library/LaunchDaemons`, root, boot). Plists with `KeepAlive`, `StartInterval`/`StartCalendarInterval` (the cron analog — cron exists but is deprecated in spirit). `launchctl bootstrap/print` for control; unified logging via `log stream --predicate`.
- Signals work POSIX-style; App Nap throttles background GUI apps (disable per-activity with NSProcessInfo assertions).

## Packaging, signing, notarization
- Distribution outside the App Store: sign with a Developer ID cert AND notarize (upload to Apple, staple the ticket) or Gatekeeper blocks with "unidentified developer". Quarantine xattr (`com.apple.quarantine`) rides on downloads — `xattr -d` in dev, notarize in prod.
- Homebrew is the developer package manager (formulas = CLI, casks = apps); `.dmg` for drag-install, `.pkg` for installer logic.
- Hardened Runtime + entitlements: camera/mic/automation each need Info.plist usage strings AND user consent (TCC database) — silent access is impossible by design.

## Filesystem
- APFS: case-INSENSITIVE by default (case-preserving) — the same trap class as Windows, on a Unix. Normalizes Unicode filenames (NFD!): "café" saved may come back as `cafe´` — compare with `unicodedata.normalize`.
- Sandboxed app data in `~/Library/Containers/`; normal config convention is `~/Library/Application Support/<app>/` (XDG is respected by CLI tools but not native apps).
- `/tmp` symlinks to `/private/tmp`; `$TMPDIR` is a per-user confstr path — use it.

## The traps
- The BSD userland: `sed -i` needs `sed -i ''`, `date -d` doesn't exist (`date -v`), `readlink -f` historically absent — GNU-ism scripts break; prefer `python3 -c` for portability or `brew install coreutils` (g-prefixed).
- System Python is gone (12.3+); `python3` stub triggers a CLT install dialog. Ship your own or use brew's.
- Apple Silicon vs Intel: universal2 binaries or per-arch wheels; Rosetta hides the difference until a native lib doesn't.
- SIP (System Integrity Protection): `/System`, `/usr` (not `/usr/local`) are unwritable even as root.
