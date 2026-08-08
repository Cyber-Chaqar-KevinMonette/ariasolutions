#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  APPLY_CHECKLIST.sh  — Aria feature rollout tracker
#  Updated: 2026-06-21
#
#  STATUS KEY:
#    [APPLIED]  — artifact confirmed in src/ or tests/  (nothing to run)
#    [STAGED]   — built + tested; run the script below to apply
#    [M75-M79]  — newest batch (Depth Offering); apply these first
#
#  HOW TO USE:
#    1. Stop sovereign cockpit if running
#    2. cd /home/kmon/AA-Erebo/sovereign-agent
#    3. Run each [STAGED] script in the order listed below
#    4. After all done: run the full test suite (last command)
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail
cd /home/kmon/AA-Erebo/sovereign-agent

# ── STEP 0: Ensure venv is current ───────────────────────────────────────────
.venv/bin/pip install -e . --quiet

# ═══════════════════════════════════════════════════════════════════════════════
#  PRIORITY BATCH — M75-M79 Depth Offering (built 2026-06-18)
#  These 5 are the newest and should be applied first.
# ═══════════════════════════════════════════════════════════════════════════════

# M75 — Birth Records + Lineage Tool
# What it does: seeds Aria's founding atoms (6 birth-record atoms in atoms.ndjson),
#               adds the `lineage` tool (T0) so Aria can recall her own origin.
# [STAGED]
bash aria-birth-records/apply_birth_records.sh

# M76 — Self-Portrait Synthesis
# What it does: adds `self_portrait` tool (T0); Aria can synthesize a full
#               self-portrait: identity, mood, growth trajectory, readiness,
#               capabilities, and narrative.
# [STAGED]
bash aria-self-portrait/apply_self_portrait.sh

# M77 — Conductor & Vault Resilience Tests
# What it does: adds 16 resilience tests (8 conductor + 8 vault) covering
#               malformed state recovery, quiesce exceptions, Merkle tamper,
#               key permissions, manifest corruption, and shutdown safety.
# [STAGED]
bash aria-conductor-vault-hardening/apply_conductor_vault_hardening.sh

# M78 — Autonomy & Execution Resilience Tests
# What it does: adds 25 hardening tests across dream_runner (DreamNotFound,
#               HARD_CAP, EC-DREAM-006 idle detection), shell_handler (kill
#               switch, allowlist, timeout, large output truncation), and
#               natural_language_handler (UTF-8 goals, scorer failure,
#               hallucinated action_kinds, kill switch).
# [STAGED]
bash aria-autonomy-hardening/apply_autonomy_hardening.sh

# M79 — Honor & Calibration Tools
# What it does: adds 5 new tools:
#               log_prediction (T1) — log a prediction with confidence
#               resolve_prediction (T1) — mark prediction correct/incorrect
#               calibration_ledger (T0) — accuracy vs. confidence analytics
#               honor_log_read (T0) — read recent honor ledger entries
#               honor_log_write (T1) — write categorized honor entries
# [STAGED]
bash aria-honor-calibration/apply_honor_calibration.sh

# M80 — Knowledge Atoms (24 distilled domain knowledge atoms in atoms.ndjson)
# What it does: seeds Aria's semantic memory with 24 atoms across:
#               software engineering · AI safety · partnership doctrine ·
#               codebase architecture · calibration discipline
# [STAGED]
bash aria-knowledge-atoms/apply_knowledge_atoms.sh

# M81 — Continuation Hardening Tests
# What it does: adds 38 tests for continuation.py:
#               format_elapsed, Continuation properties (cursor, progress,
#               model affinity, elapsed, is_drained), status recomputation,
#               YAML roundtrip, corrupt-input rejection, ContinuationStore
#               (create/get/lock/delete, concurrent lock exclusion)
# [STAGED]
bash aria-continuation-hardening/apply_continuation_hardening.sh

# M82 — Health Scanner Hardening Tests
# What it does: adds 34 tests for health.py:
#               HealthReport.ok/summary_line/by_severity, _parse_iso_to_seconds,
#               scan_idle_cycles (EC-DREAM-006), scan_zombies (EC-HEALTH-001),
#               plan_repairs (zombie/pause/lock mapping), apply_repairs dry-run
# [STAGED]
bash aria-health-hardening/apply_health_hardening.sh

# M83 — Wisdom Atoms (12 operational wisdom PATTERN atoms in atoms.ndjson)
# What it does: seeds Aria's semantic memory with 12 PATTERN atoms about
#               HOW she operates: Kevin's trust pattern, staging doctrine,
#               test discipline, apply markers, confidence ladder,
#               self-model loop, and boring-reliability doctrine.
# [STAGED]
bash aria-wisdom-atoms/apply_wisdom_atoms.sh

# ═══════════════════════════════════════════════════════════════════════════════
#  SECONDARY BATCH — Older staged modules (built in prior sessions)
#  Apply after M75-M79 in any order. All are idempotent.
# ═══════════════════════════════════════════════════════════════════════════════

# capability-gaps — workflow capability gap detection + variant routing
# [STAGED]
bash aria-capability-gaps/apply_capability_gaps.sh

# institutional-impulse — institutional health sentinel
# [STAGED]
bash aria-institutional-impulse/apply_institutional_impulse.sh

# multi-step — multi-step agentic task execution
# [STAGED]
bash aria-multi-step/apply_multi_step.sh

# observatory — observability / metrics sentinel
# [STAGED]
bash aria-observatory/apply_observatory.sh

# response-depth — response quality depth doctrine patches
# [STAGED]
bash aria-response-depth/apply_response_depth.sh

# ripple-coalesce — event ripple + coalescing for burst deduplication
# [STAGED]
bash aria-ripple-coalesce/apply_ripple_coalesce.sh

# risk-register — Aria_Weakness_Risk_Register read tool
# [STAGED]
bash aria-risk-register/apply_risk_register.sh

# sentinel-chat — chat/text interface for sentinel status
# [STAGED]
bash aria-sentinel-chat/apply_sentinel_chat.sh

# sentinel-fidelity — sentinel contract fidelity tests
# [STAGED]
bash aria-sentinel-fidelity/apply_sentinel_fidelity.sh

# session-memory — session-scoped memory layer
# [STAGED]
bash aria-session-memory/apply_session_memory.sh

# vision-deep — deep vision analysis (heavy GPU, serialized via vram_lock)
# [STAGED]
bash aria-vision-deep/apply_vision_deep.sh

# workout — Aria fitness / benchmark runs
# [STAGED]
bash aria-workout/apply_workout.sh

# ═══════════════════════════════════════════════════════════════════════════════
#  FINAL VERIFICATION — run after all apply scripts
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "=== Final test suite ==="
.venv/bin/python -m pytest --ignore=tests/test_cockpit.py -q

# ═══════════════════════════════════════════════════════════════════════════════
#  ALREADY APPLIED — confirmed by artifact presence in src/ or tests/
#  (Nothing to run for these.)
# ═══════════════════════════════════════════════════════════════════════════════
#
#  [APPLIED] aria-atoms-compact         atoms_compact_tool.py
#  [APPLIED] aria-authority-fidelity    vram-lock-timeout-d event
#  [APPLIED] aria-auto-crown            auto_tools.py
#  [APPLIED] aria-backlog-gate          backlog gate in tools
#  [APPLIED] aria-behavior-self         behavior_tools.py
#  [APPLIED] aria-browser-crown         browser_tools.py
#  [APPLIED] aria-cache-crown           cache_tools.py
#  [APPLIED] aria-clipboard-yank        Ctrl+Y yank-last in cockpit
#  [APPLIED] aria-cockpit-god           cockpit god-mode layout
#  [APPLIED] aria-cockpit-vitality      cockpit vitality panel
#  [APPLIED] aria-collab-secure         evolving_run.py + vault + requests
#  [APPLIED] aria-command-invariants    test_command_invariants.py
#  [APPLIED] aria-command-master        command_master.py
#  [APPLIED] aria-companion             companion_tools.py
#  [APPLIED] aria-compression           compression_tools.py
#  [APPLIED] aria-confidence-crown      confidence_crown.py
#  [APPLIED] aria-cron-hygiene          schedule_sentinel.py
#  [APPLIED] aria-cron-internal         schedule_tool.py
#  [APPLIED] aria-deep-mind             loop.py deep reasoning patch
#  [APPLIED] aria-emotion-crown         emotion_tools.py
#  [APPLIED] aria-eval-crown            eval_tools.py
#  [APPLIED] aria-experience-crown      experience_tools.py
#  [APPLIED] aria-git-experience        git experience tool
#  [APPLIED] aria-git-eyes              git_eyes.py
#  [APPLIED] aria-git-write             git_write.py
#  [APPLIED] aria-god-workflow          god_workflow_tools.py
#  [APPLIED] aria-help-refbuttons       F1 toggle + close button in cockpit
#  [APPLIED] aria-honor-write           honor_write.py
#  [APPLIED] aria-hypothesis-close      test_hypothesis_close.py
#  [APPLIED] aria-image-edit            image_edit.py
#  [APPLIED] aria-image-gen             image_generate.py
#  [APPLIED] aria-inbox-context         requests.py rich context fields
#  [APPLIED] aria-inbox-pane            cockpit inbox pane
#  [APPLIED] aria-interjection          interjection_tools.py
#  [APPLIED] aria-know-thyself          aria_status.py + loop patches
#  [APPLIED] aria-lessons-loop          lessons_tool.py
#  [APPLIED] aria-leverage              leverage_tools.py
#  [APPLIED] aria-mode-master           mode_tools.py
#  [APPLIED] aria-notify-crown          notify_tools.py
#  [APPLIED] aria-osc11-bgsync         OSC11 background sync in cockpit
#  [APPLIED] aria-palace-write          palace_write.py
#  [APPLIED] aria-palette-legend        palette legend in cockpit
#  [APPLIED] aria-proof-crown           proof_tools.py
#  [APPLIED] aria-protocol-zero-hardening  mode_controller.py patch
#  [APPLIED] aria-provenance-tool       provenance_tool.py
#  [APPLIED] aria-qol                   boot sequence, auto-notify, Ctrl-P voice
#  [APPLIED] aria-reflection-crown      reflection_tools.py
#  [APPLIED] aria-researcher            researcher_tools.py
#  [APPLIED] aria-resilience            resilience_tools.py
#  [APPLIED] aria-resume-crown          resume_tools.py
#  [APPLIED] aria-router-expand         router expansion
#  [APPLIED] aria-safe-glyphs           safe glyph rendering
#  [APPLIED] aria-sandbox-runner        sandbox_runner.py
#  [APPLIED] aria-screenshot            screenshot.py
#  [APPLIED] aria-self-knowledge        self_knowledge.py
#  [APPLIED] aria-sentinel-crown        sentinel crown
#  [APPLIED] aria-telemetry-sentinel    telemetry_sentinel.py
#  [APPLIED] aria-vision-crown          vision_tools.py
#  [APPLIED] aria-voice-crown           voice_tools.py
#  [APPLIED] aria-watchdog-tests        test_watchdog_sentinel.py
#  [APPLIED] aria-web-better            web_better.py
#  [APPLIED] aria-workflow-wire         workflow_tools.py
