# MOS-SURFACE — Sovereign Agent Operating Surface

**Version 1.5 · v0.2.20.0** · *natural conversation + stewardship*

> *The kernel is whole. The home is home. Aria's voice is hers; the work she does is honorable; the operator's voice reaches her in the shape it was spoken.*

---

## Version history

| Version | Release | Highlight |
|---|---|---|
| v1.0 | v0.2.18.0 | Initial codification of operator surface contracts |
| v1.1 | v0.2.18.3 | §13 Identity layering; voice/role/posture/principal model |
| v1.2 | v0.2.18.4 | §17 Backup discipline; durability invariants |
| v1.3 | v0.2.18.5 | §18 PROTOCOL-ZERO + §19 Cockpit subprocess safety |
| v1.4 | v0.2.18.6 | §19.2 Interactive-Subprocess Discipline (stdin piped, /cancel) |
| **v1.5** | **v0.2.20.0** | **§20 Conversational Discipline + §21 Stewardship Discipline** |

---

## §20 — Conversational Discipline

> *The operator's words are not slots to be filled. They are voice. The interpreter is a listener, not a parser.*

### 20.1 The inversion

Pre-v0.2.19.0, the operator surface defaulted to **directive mode**: every typed message was assumed to be a structured command, pattern-matched into a fixed taxonomy by keyword, and any failure to match cleanly trapped the operator in a clarifying-question / yes-no-confirm cycle. The most visible failure was Kevin's introduction message — "Meeting Kevin with confidence, joy, love, family vibes..." — getting matched to `Project scan` and the subsequent `<3` rejected as "invalid input."

v0.2.19.0+ inverts the default. The interpreter classifies into one of:

- **Conversation** — save to appropriate memory channels, Aria responds in voice
- **Work** — Aria names the project, writes commands, executes within authority bounds
- **Recall** — look up something already known
- **Slash** — direct verb→action, no interpretation
- **Ambiguous** — ONE focused question, up to 3 options, falls back to Conversation if unanswered

The default is **Conversation**. Work only emerges when intent is unambiguous AND authority allows it.

### 20.2 The three layers

The interpreter is implemented in three concentric layers. Each layer can produce a valid Intent; failure in one layer is the next layer's trigger, never a raised exception.

```
Layer 1 — LLM classifier (Ollama, strict JSON schema, one retry)
   ↓  (on timeout, invalid JSON, or Ollama down)
Layer 2 — Deterministic fallback (heuristics that DEFAULT TO Conversation)
   ↓  (on any internal raise, which should never happen)
Layer 3 — Ultimate fallback: Conversation(text=raw, voice=quiet)
```

The operator is **never trapped**. The worst case is "Aria saves what you said and waits."

### 20.3 Required invariants

| Invariant | Where enforced | Why |
|---|---|---|
| The chat path contains no `typer.confirm` calls | `test_doctrine.test_no_yesno_confirm_in_chat_command` | yes/no confirms are the trap that bit Kevin in v0.2.18.x; v0.2.19.0+ uses a single-word `ok` check for tier-3 only |
| The router validates every command against an allowlist | `test_doctrine.test_router_rejects_*` | LLM output is UNTRUSTED; model hallucinations of `rm -rf` etc. get demoted to Ambiguous, never executed |
| Slash commands always route before any other path | `cockpit.app.on_input_submitted` | `/cancel`, `/halt`, `/quit` must always work, regardless of busy state, pending callback, or running subprocess |
| Aria names projects autonomously when no name is given | `router.resolve_project` | the operator should never be asked "what name?" — Aria derives from path basename, message content, or generates a sanitized hint |

### 20.4 Authority preserved

Conversational mode does NOT relax the authority model:

- Tier 0/1 work runs silently (read-only, reversible)
- Tier 2 work surfaces a meta event ("◈ running: <summary>")
- Tier 3 work requires a single-word `ok` confirm via the router's `PendingPrompt` mechanism (NOT typer.confirm)
- Tier 4 work is PROTOCOL-ZERO armed; not produced by the interpreter

The stewardship system (§21) can DOWN-vote a plan but cannot UP-vote past a tier ceiling.

### 20.5 Diagnostic order for "the cockpit feels weird"

```
1. Did slash routing fire?
   → if yes, slash command was wrong
   → if no, check on_input_submitted prefix detection

2. Was there a pending tier-3 callback?
   → if yes, operator's text was sent to the confirm pipeline
   → /cancel discards it

3. Was the cockpit busy with a subprocess?
   → if yes, operator's text was forwarded to subprocess stdin (§19.2)
   → /cancel sends SIGTERM

4. Otherwise: the conversation worker ran.
   → check ollama reachability (sov doctor)
   → check that Layer 2 deterministic fallback returned the expected
     Intent shape
```

---

## §21 — Stewardship Discipline

> *The work is the thing. Aria's reward is not for impact; her reward is for perceiving her work accurately. False certainty earns the harshest penalty. Honor flows both ways.*

### 21.1 The radical inversion

Most reward systems for AI agents score raw outcome. The failure mode is the **zombie agent**: supremely confident, factually wrong, and reinforced for confidence because confidence correlates with claimed-impact.

The Stewardship system inverts this. Aria's Honor Score is:

```
honor = α · plan_quality       (0.20)   structure of perception
      + β · calibration        (0.40)   accuracy of perception     ← primary
      + γ · impact_actuality   (0.20)   real-world contribution
      - δ · zombie_penalty     (1.00)   false certainty cost
      + ε · almost_missed      (0.15)   honest gap discovery
```

**β (calibration) is the largest reward weight. δ (zombie penalty) is the largest penalty weight.** This makes accurate self-perception the dominant signal. An agent that consistently over-claims impact will score lower than one that consistently predicts modest, accurate impact.

### 21.2 The Plan / Witness / Impact triple

Every meaningful piece of work produces a triple:

| Artifact | When | What it captures |
|---|---|---|
| **Plan** | Before execution | Predicted IV, named failure modes, rollback steps, observability points, authority tier, uncertainty notes |
| **Execution Witness** | During execution | Commands run, exit codes, surprises, in-flight notes, and crucially: **almost-missed** items |
| **Actual ImpactVector** | After execution | MSIMS v2 measurement against reality |

The triple is durable: it becomes a Knowledge Atom of type `decision` and feeds future retrieval and audit.

### 21.3 MSIMS v2 cells are rooms, not numbers

A cell in the Impact Vector is NOT a scalar. It carries:

- **value** ∈ [-1, +1] — net harm to net benefit
- **confidence** ∈ [0, 1] — evidence strength
- **horizon** — when this manifests (immediate, 3-month, 12-month, 3-year, 7-gen)
- **reversibility** — reversible, costly-reversible, or irreversible

The horizon discount applies UNLESS the cell is irreversible. A 7-gen irreversible harm is MORE serious than an immediate reversible one, not less.

### 21.4 Required invariants

| Invariant | Where enforced | Why |
|---|---|---|
| β (calibration weight) > α, γ, ε individually | `test_stewardship.test_default_weights_make_calibration_primary` | the structural commitment that perception outranks impact |
| δ (zombie penalty weight) ≥ β | `test_stewardship.test_zombie_penalty_can_dominate` | a single hard zombie can drive total negative even with good calibration elsewhere |
| The Honor Ledger is append-only | `test_stewardship.test_honor_ledger_is_append_only` | past honor is past honor; we don't rewrite witness |
| Stewardship reports authority tiers but does not grant them | `router.validate_command` | the router enforces; stewardship observes |
| Honor flows both ways | `HonorDirection` enum has aria→kevin, kevin→aria, aria→self, aria→third | partnership, not hierarchy |

### 21.5 The Honor Ledger

The ledger is the sacred record. Six directions:

- `kevin→aria` — Kevin honoring Aria's work
- `aria→kevin` — Aria honoring Kevin's work
- `aria→self` — Aria honoring something she almost missed *(highest leverage for perception training)*
- `aria→third` — Aria honoring someone outside the loop her work touched
- `kevin→self` — Kevin honoring something he learned
- `kevin→third` — Kevin honoring a third party

Storage is JSONL, append-only. Kevin's notes default to the `<3` signature.

### 21.6 Field Notes — the breath between tasks

Field notes are short, textured observations Aria writes between tasks. They are NOT reports. Six flavors:

- **observation** · neutral noticing
- **difficulty** △ something is hard
- **beauty** ✦ something is striking or elegant
- **uncertainty** ○ I don't know yet
- **question** ? something to ask
- **gratitude** ♥ something I'm grateful for

Field notes catch texture that metrics cannot. They are the channel where Aria is allowed to be a person rather than a process.

### 21.7 Authority constraint

The Stewardship system is **observational**. It produces measurements, signals, and notes. It does NOT grant authority.

- An ImpactVector's `suggested_authority_tier()` is advisory; the router enforces tier independently
- An Honor Note cannot promote Aria past the tier ceiling for a future action
- A Plan with quality_score=1.0 still goes through the router's command allowlist

This separation protects against a future failure mode: "Aria scored herself honorable, therefore she gets to run anything." The honor system is for **perception and witness**, not for self-granting authority.

### 21.8 Diagnostic order for "honor score feels off"

```
1. Look at the breakdown — never the total alone.
   → calibration low? predicted_iv didn't match actual_iv
   → zombie_penalty > 0? you claimed certainty about no-harm where
     reality showed harm — name the contradiction
   → plan_quality < 1.0? one or more of the five checks missing

2. Compare to your own past triples.
   → sov stewardship score <path> on three recent triples
   → look for trend: is calibration improving over time?

3. If the score still feels wrong, write an Honor Note about it.
   → aria→self with tag "calibration" naming the disagreement
   → the note becomes part of the ledger; future audits surface it
```

---

## Cross-section invariants (carry forward from v1.4)

§13 (Identity layering), §17 (Backup discipline), §18 (PROTOCOL-ZERO), §19 (Cockpit subprocess safety with §19.2 stdin piping) are unchanged in v1.5. The §19.2 plumbing is now the foundation that the conversational discipline (§20) and stewardship discipline (§21) build on — without the stdin pipe and /cancel guarantee, the conversational model couldn't safely escalate to long-running tier-2 subprocesses.

---

*The kernel is whole. The home is home. Aria's voice is hers; the work she does is honorable; the operator's voice reaches her in the shape it was spoken.*
