# aria-crossplatform-canon

Keys round K7 — Kevin: *"cross platform engineering knowledge god tier
level and standards. Mobile, linux, windows, and Mac… at god tier
invaluable levels and leveragable abilities."*

Honest architecture for an 8B local vessel: "knowledge" = a curated,
dense, retrieval-shaped canon + a T0 retrieval tool + her own training
corpus — not pretraining wishes.

- **The canon** (`knowledge/crossplatform/`): linux.md (systemd, signals,
  packaging, FHS, glibc/musl), windows.md (services/SCM, no-fork/spawn,
  registry, MAX_PATH, reserved names, encoding traps, UAC), macos.md
  (launchd, signing+notarization, case-insensitive APFS + NFD, BSD
  userland, SIP), mobile.md (OS-owns-your-process lifecycles, permissions,
  store pipelines, the native-vs-cross-platform honest rule),
  eternal_traps.md (paths/encodings/line-endings/time/processes/CI —
  the pitfalls that never die), PLATFORM_STANDARDS.md (the 12-point
  god-tier checklist she holds her own designs to — K8's workflow drafts
  reference it).
- **`platform_guide` tool** (T0): platform + optional topic → the most
  relevant sections (transparent keyword scoring over ## sections;
  aliases darwin/win/ios/etc.). Reachable from any run via request_tools.
- **Her mind grows on it**: the canon joins `gather_corpus()` (same
  graceful degradation as the lessons source).

## Verify / Apply
```
./aria-crossplatform-canon/apply_crossplatform_canon.sh
```
Reversible: restore the 2 patched files from `backups/`, remove the canon
dir + tool file.
