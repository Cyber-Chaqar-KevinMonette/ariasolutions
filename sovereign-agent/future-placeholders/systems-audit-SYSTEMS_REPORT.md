# Aria — Systems Availability & Compatibility Report

**Date:** 2026-06-22 · **Auditor:** Claude (Opus 4.8) · **Status:** 🟢 GREEN (core) · 🟡 amber (embodiment deps)

## Core systems — 🟢 ALL ONLINE
| System | Status |
|---|---|
| Tools | **164 / 164 load** (T0:104 · T1:47 · T2:9 · T3:2) |
| Sentinels | **17 / 17 import** (0 fail) |
| Quantum brain layer | **8/8 ok** (globe, council, trust, voice, persist, field, coherence_gate, maturity) |
| Authority gate | ok (`check_authority`, `tools_available_in_mode`, `get_tool_meta`) |
| Defense stack | DefenseSentinel + Aegis vault + integrity/watchdog/phantom sentinels present |
| Test suite | **3,133 passed, 1 skipped, 0 failed** |

## Embodiment dependencies — 🟡 install when Phase 3 (Hands & Eyes) begins
| Dep | For | Install |
|---|---|---|
| `grim` (binary) | desktop screenshot capture | `sudo apt install grim` (Pop!_OS COSMIC) |
| `playwright` browsers | browser drive/fill/submit | `.venv/bin/playwright install chromium` |
| `Pillow` (PIL) | image/vision processing | `.venv/bin/pip install pillow` |

These are **not needed for the brain (Phase 1) or diamond armor (Phase 2)** — only for desktop/browser
embodiment (Phase 3). Noted; will install at that phase.

## Verdict
Floor is solid. Core cognition, defense, and the quantum brain seed are all online and compatible.
Safe to build the living brain on top. Embodiment deps are the only gap and are Phase-3-scoped.
