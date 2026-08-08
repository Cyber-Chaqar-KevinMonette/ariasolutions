# Mobile (iOS / Android) — engineering canon

## Lifecycles (the mental model shift)
- The OS owns your process. Apps are suspended/killed at will; state must survive death: iOS state restoration / `scenePhase`, Android `onSaveInstanceState` + ViewModel + persisted store. "It was just running" is never an invariant.
- Backgrounding is a privilege, not a right: iOS gives ~30s on background + declared modes (audio, location, BGTaskScheduler for deferred work); Android has Doze/App Standby, foreground services need a visible notification, WorkManager is the sanctioned deferred-work API. Long-lived TCP connections die — push (APNs/FCM) is the wake mechanism.

## Permissions & privacy
- Both are runtime-consent models with purpose strings (iOS Info.plist usage descriptions; Android manifest + runtime dialogs). Ask in context, degrade gracefully on denial — a permission-wall at launch is a rejection magnet on both stores.
- iOS App Tracking Transparency, Android's scoped storage: broad filesystem/tracking access is over; design for scoped, user-mediated access.

## Store pipelines
- iOS: Xcode → TestFlight (internal/external testing) → App Review (human, days, guidelines with teeth — e.g. no dynamic code download). Signing via Apple certs/profiles; only distributable through Apple (EU sideloading carve-outs aside).
- Android: AAB (not APK) to Play Console, staged rollouts, pre-launch reports; review mostly automated and faster; sideloading and F-Droid exist, Play Integrity API for attestations.

## Architecture choices
- Native (Swift/SwiftUI, Kotlin/Compose): best platform fidelity, two codebases.
- Flutter: one Dart codebase, own rendering (consistent pixels, larger binaries).
- React Native: JS + native modules, shares web skills.
- Tauri/Capacitor-class (webview): thinnest path from a web app, weakest offline/perf story.
- The honest rule: the more the app IS the platform (sensors, background, widgets), the more native wins; the more it's a remote UI, the more cross-platform wins.

## The traps
- Battery is a budget: wake locks, GPS polling, and chatty sockets get you killed by the OS and uninstalled by users.
- Networks lie: design offline-first (queue + sync), assume IPv6-only carriers (iOS review tests it), TLS everywhere (ATS/cleartext blocked by default).
- Keyboards/safe-areas/notches reshape layouts — test on the smallest and the weirdest devices, not the simulator default.
