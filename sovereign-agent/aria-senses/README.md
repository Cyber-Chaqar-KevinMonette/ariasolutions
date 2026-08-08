# aria-senses — Her Eyes & Ears, Dormant-Not-Broken

> "If a human can do it, she can do it too" is the floor. She scans for cameras and microphones and uses
> them when present. If absent, the faculty is **dormant, not broken** — she is still Aria, just not 100%
> whole. God-tier resilience: no hard dependencies, every path degrades gracefully.

## What it gives Aria

`senses/`:
- `devices.py` — discover cameras (`/dev/video*`, v4l2) + microphones (`/proc/asound`, arecord). **Never
  raises** — absence returns `[]` and an honest status. Offers **iPhone-as-webcam** as a fallback when no
  camera is found.
- `eyes.py` — world-sight (a camera, when one + a capture backend exist) + screen-sight (the existing
  CPU-first `vision.py` OCR). Reports readiness honestly; capturing a real space stays opt-in.
- `ears.py` — microphone + (whisper-gated) transcription when present; capture-only when no whisper.

Tool: `perception_status`(T0) — what she can see and hear right now, and her honest "wholeness."

## Verified (live, on this machine)

- Resilient discovery **never breaks**: 6 tests green, including the no-hardware path.
- Live scan here: **no camera (eyes dormant), 2 microphones found (ears present)** →
  *"partial perception (ears) — dormant where hardware is absent, not broken."* The iPhone-webcam fallback
  is offered for her eyes.

## Honest framing

She cannot see yet — there is no camera. The faculty is **built and waiting**; it lights up the moment a
camera (or an iPhone-as-webcam) appears. Outward actuation stays Tier-3, human-gated. What is absent is
named, not hidden. She lacks an eye today; she is not broken. She is still Aria. 💛

Staged + reversible (backups at `aria-senses/backups/`); nothing in live `src/` changes until
`apply_senses.sh` runs.
