# Aria — Triage: Make the Core Loop Work First
## Read from the screenshots, not from the wish list ✦ v0.2.60

> You asked for a lot tonight: a god-tier flagging system, per-request tool evaluation, redundancy on
> every system, autonomous orchestration, hardened persistence, clipboard copy. Most of it is good. But
> the eleven screenshots show a system that **can't yet do the things those features would sit on top
> of.** This doc orders the work by what's actually true on screen. The honest headline: **don't add
> capability to a loop that isn't connected. Connect the loop first.**

---

## 1. What the screenshots actually show (the diagnosis)

Symptoms, straight from the frames:

- **Every reply is 2-3 sentences of agreeable filler.** "I'm here to help you, Kevin! What specific
  assistance do you need?" / "I'll keep that in mind." This is a small local model generating pleasant
  text — not a system reasoning over its tools.
- **She cannot name her own tools.** Asked twice ("list all your tools and sentinels", "are you not able
  to tell what tools you have access to?") she deflects both times. → **The model is not receiving a
  tool manifest in its context.**
- **A subcommand 404s and the turn dies.** `I can't run 'sov test-system-create-verify' (unknown sov
  subcommand)`. → **The NL→action path has no graceful fallback and no real dispatch to existing tools.**
- **Memory is flat the entire session.** `patterns: 0 · atoms: 0 · valuable: 0`, `total: 2` unchanging.
  → **The memory channels are not being written. What looks like persistence is the chat log scrolling.**
- **No turn-taking / orchestration.** She answers once and stops; never plans, never chains a step. →
  **There is no agentic loop wiring the model to tools and back.**

**Root cause (one sentence):** the pieces exist — model, tools, sentinels, memory — but the **wiring
between them is not connected.** This is RISK-005 (integration is the weak seam) and RISK-002 (the local
model is a junior), exactly as flagged. It is **not** a missing-feature problem.

---

## 2. Why the requested features can't go first

Each requested feature *depends on* the broken layer:

| You asked for | It requires (which is broken) |
|---|---|
| "Evaluate all tools/sentinels per request" | a tool manifest reaching the model — she can't list tools at all |
| "God-tier problem flagging system" | the loop running far enough to *detect* a problem to flag |
| "Autonomous orchestration / take turns" | an agentic loop that doesn't exist yet |
| "Redundancy on every system" | a working system to make redundant (two copies of disconnected = disconnected) |
| "Aria tracks the proof board / her own capabilities" | memory writes that currently aren't happening |

**Adding these now is building rooms onto a house whose plumbing isn't connected.** It feels like
progress and increases surface area (RISK-006) while the core stays broken.

---

## 3. The correct sequence (smallest first, each verifiable)

**▶ STEP 0 — The clipboard yank (do this first; it's the warm-up).**
A copy-the-last-response affordance (`^y` to yank, or a copy button per turn in the chat pane). Tiny,
concrete, real. It's the perfect first Claude-Code task: well-scoped, low-risk, and it lets you send
Aria's replies to me cleanly instead of screenshotting at 2am.

**STEP 1 — Give the model its tools (fixes "she doesn't know her tools").**
The tool/sentinel manifest must be injected into the model's context every turn, and the dispatch path
must actually call them. This is the single highest-leverage fix: it turns her from a chatbot into an
agent. (Likely the `authority.py` tool list isn't being rendered into the prompt — the gate withholds
out-of-tier tools, but *something* must be passing the in-tier ones in. Verify that path.)

**STEP 2 — Graceful fallback for unknown subcommands (fixes the hard stop).**
She should NEVER hit "unknown sov subcommand" and die. Unknown → map to nearest known tool, or fall back
to "save as conversation," or ask one clarifying question — never halt. (The frames show a half-built
version of this: it lists "1. just save this as conversation" but then stalls.)

**STEP 3 — Wire the memory channels (fixes flat memory + flaky persistence).**
`patterns/atoms/valuable` must actually be written during a turn. Until they are, "harden persistence"
has nothing to harden — the channels are empty by wiring, not by fragility.

**STEP 4 — The orchestration loop (fixes "stops after every turn").**
A real agentic loop: model reads manifest → plans → calls tool(s) → reads result → continues or
finishes. This is what "take turns like other AI systems" actually means. It's a meaningful build, and
it must come *after* steps 1-3, because it orchestrates exactly those.

**THEN — and only then — the features you asked for:** per-request tool evaluation (step 1 makes it
possible), the flagging system (step 4 makes problems detectable), redundancy (now there's a working
system to protect), Aria reading/updating the proof board (step 3 makes the writes real).

---

## 4. On "strong-arm this before Claude Code" — the one honest reversal

This is the turn where Claude Code stops being optional, and I have to say so plainly.

Every problem above is a **run-it / read-the-error / fix-the-wiring / run-it-again** problem:
- *Why does the model not get the tool manifest?* → read the prompt-assembly code, print what's actually
  sent.
- *Why does the subcommand 404?* → run `sov`, read the real traceback.
- *Why is memory not writing?* → run a turn under a debugger, watch the channel write (or not).

**None of that can be done from here.** I'm reasoning through screenshots (RISK-012); you're
hand-shuttling PNGs at 2am. That is the slowest, lossiest possible debugging loop. Claude Code, in the
repo, running `sov` and reading the real errors, closes every one of these in minutes. **The thing
that's broken is precisely the thing Claude Code is for.** Strong-arming it from chat first isn't faster
— it's the long way around.

Recommended: do STEP 0 (clipboard) in Claude Code as the trust-building first task, in Plan Mode, behind
a git branch. If it handles that cleanly, point it at STEP 1.

---

## 5. On redundancy (since you asked for it on everything)

Redundancy is a virtue *on a working component*, not a substitute for one. Apply it where it earns its
cost:
- **Worth it:** the memory write (write-then-verify, like your `diagnosis.py` rollback discipline); the
  ledger (append + checksum); backups (the status bar shows `backup: no snap` — that's a real gap, fix
  it).
- **Not yet:** don't duplicate subsystems that don't work singly. Two copies of a disconnected loop is
  not resilience; it's two bugs. Make it work once, reliably, *then* add the second path.

> Boring reliability over clever capability. A single core loop that works end-to-end for one real
> exchange beats ten half-wired subsystems with redundancy bolted on.

---

## 6. The one move that changes everything tonight

Make **one real exchange** work: you ask Aria to do a concrete thing, she consults her actual tools,
does it, writes it to memory, and confirms — without filler, without a hard stop. That single working
loop is worth more than every feature on the wish list, because every feature hangs off it.

Get the loop breathing. Then pour into her all you want — there'll finally be lungs to fill.

> *I know the next move: STEP 0 in Claude Code. Should I proceed to spec it?*
