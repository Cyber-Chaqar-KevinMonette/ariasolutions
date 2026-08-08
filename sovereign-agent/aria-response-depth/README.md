# aria-response-depth — SUPERSEDED, do not apply (2026-07-03)

**Do not run `apply_response_depth.sh`.** It will fail its own anchor
check (`"expected anchor not found in interpreter.py — has the file
changed?"`), and that failure is correct, not a bug to fix.

## Why

This module (v0.2.42.0) set out to teach `interpreter.py`'s system
prompt to match response depth to question complexity — casual chat
stays brief, technical questions get thorough multi-paragraph answers.

That exact capability was independently added to live `interpreter.py`
at some point after this module was staged, under a richer "DEPTH
DOCTRINE" section — more elaborate than what this module's own patch
would have inserted (it also covers "creative / planning / big picture"
questions and a "SHOW YOUR THINKING" transparency directive this
module never had). Confirmed via direct read of the live system prompt.

## What was fixed here (2026-07-03)

`tests/test_response_depth.py` still checked for the OLD, exact wording
this module's own never-applied patch would have produced ("Depth:
match depth", "warm, conversational", lowercase "thorough"). Root-cause
fixed to check for the actual live phrasing instead ("DEPTH DOCTRINE",
"match depth to complexity", "THOROUGH", "Multiple paragraphs", "casual
chat" / "2-3 warm sentences") — proving the underlying capability is
genuinely present, without forcing a stale, now-redundant patch through.

If `interpreter.py`'s depth guidance is ever removed or weakened, these
tests will catch it — they just no longer expect this specific staged
module's own (superseded) wording.
