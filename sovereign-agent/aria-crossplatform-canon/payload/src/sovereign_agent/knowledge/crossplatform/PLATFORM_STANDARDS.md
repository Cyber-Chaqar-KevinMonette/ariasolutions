# PLATFORM_STANDARDS — what god-tier cross-platform engineering MEANS

The checklist Aria holds herself — and every workflow she designs — to.

1. **Paths**: pathlib everywhere; no hardcoded separators, homes, or temp
   dirs; case-collision-free filenames; tested against MAX_PATH depth.
2. **Encodings**: every `open()` declares `encoding="utf-8"`; filename
   comparisons normalize Unicode; console output survives a Windows
   legacy codepage.
3. **Line endings**: `.gitattributes` pins LF for text; shebangs LF;
   protocol CRLF explicit.
4. **Time**: UTC stored, zones explicit, monotonic for durations.
5. **Processes**: spawn-safe entry points (`if __name__ == "__main__"`),
   graceful-stop contract handled per platform (SIGTERM / CTRL events /
   SCM), no orphaned children (groups/jobs).
6. **Atomic writes**: write-temp-then-`os.replace`, fsync where loss
   matters — the one idiom that is atomic on all three desktops.
7. **Services**: the platform's own lifecycle (systemd unit / launchd
   plist / Windows Service or Task) — never a detached nohup pretending
   to be a daemon.
8. **Packaging**: distro/platform-native artifacts, signed where the
   platform expects it (Authenticode / Developer ID + notarization);
   never install into system interpreters.
9. **Permissions**: least privilege; runtime consent asked in context;
   graceful degradation on denial.
10. **Mobile mindset where it applies**: the OS owns the process — state
    survives death; background work uses the sanctioned scheduler; battery
    and offline are budgets, not afterthoughts.
11. **CI matrix**: ubuntu + windows + macos on every supported runtime;
    the path/encoding/line-ending tests run on ALL of them.
12. **Honesty**: platform limitations documented where users will read
    them, not discovered by them.
