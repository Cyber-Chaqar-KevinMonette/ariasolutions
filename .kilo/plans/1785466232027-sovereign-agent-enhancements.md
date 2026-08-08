# Sovereign Agent System — Enhancement Plan

**Date:** 2026-07-30
**Status:** Draft — ready for review before implementation
**Scope:** Enhancements to the existing sovereign-agent system (Aria), not new standalone features

---

## 1. Current State Summary

The sovereign-agent system is a mature, well-architected local-first AI agent with:

- **220+ registered tools** across 4 authority tiers (0–3)
- **27+ sentinels** for health, integrity, and observability
- **12 MCP tools** exposed via `mcp_server.py` (FastMCP, stdio + SSE)
- **552 test files**, 3,133+ passing tests
- **100+ aria- modules** covering memory, quality, grounding, wellbeing, integrity, workflow, etc.
- **Kernel safety**: authority tiering, universal scanner kernel, protocol-zero, DEFERRED_UNSAFE boundary
- **Peig-engine** exists as a separate repo (`/home/kmon/AA-Erebo/peig-engine/`) with no formal dependency integration
- **Feedback module** exists but is isolated from the agent loop
- **`future-placeholders/`** contains 5 unbuilt ideas (docker-launch, platform-compat, mcp-serve, systems-audit, holo-bitnet)

### Key Gaps Identified

| Gap | Impact | Priority |
|---|---|---|
| MCP server exposes only 12 of 220+ tools | External systems (Claude Desktop, other agents) can only access a tiny fraction of Aria's capabilities | High |
| No structured tracing/observability | Debugging tool chains, latency, and failure patterns is ad-hoc | High |
| Feedback module is isolated | Operator ratings don't influence agent behavior | Medium |
| Peig-engine is a separate repo with no dep | Quantum brain and PEIG framework are loosely coupled | Medium |
| No systematic benchmark/regression suite | Performance regressions in proving-ground wings are caught manually | Medium |
| No automated canary testing for module applies | `safe_apply` has no pre-flight canary gate | Medium |
| Docker/platform-compat are placeholders | Deployment is manual and Linux-only | Low |

---

## 2. Enhancement Proposals

### 2.1 — Expand MCP Server Tool Surface (High Priority)

**Problem:** The MCP server (`mcp_server.py`, 377 lines, 12 tools) is the primary integration point for external systems, but it exposes only status, ledger, and a few read-only tools. The full 220+ tool registry is invisible to MCP clients.

**Approach:**
1. Add a `list_tools` MCP tool that returns the full registry (name, tier, description, failure_modes) — already partially available via `authority.all_tools()`.
2. Add a `run_tool` MCP tool that accepts a tool name and arguments, runs it through the authority gate, and returns the result. This must respect the mode's tier ceiling and require approval for Tier 3 tools.
3. Add MCP tools for the most commonly needed external-facing capabilities:
   - `memory_search` / `memory_write` (T0)
   - `read_file` / `write_file` (T1)
   - `shell_exec` (T2, sandboxed)
   - `git_status` / `git_diff` (T2)
   - `consult_council` (T1)
   - `get_health` (T0)
4. Keep the existing 12 tools; add new ones alongside them.
5. Add `--mcp-tools` CLI flag to `sov-mcp` that allows operators to whitelist which tools are exposed via MCP (security surface reduction).

**Files to modify:**
- `src/sovereign_agent/mcp_server.py` — add tools
- `src/sovereign_agent/cli.py` — add `--mcp-tools` flag

**Validation:**
- Run existing test suite: `pytest tests/ -x -q`
- Add new tests for `list_tools`, `run_tool`, and the whitelist flag
- Verify that `run_tool` correctly rejects tools above the mode's tier ceiling
- Verify that Tier 3 tools without approval raise `AuthorityViolation`

---

### 2.2 — Structured Observability & Tracing (High Priority)

**Problem:** The system has a `telemetry_sentinel.py` and cockpit telemetry panel, but no structured tracing that connects a single user request through its full tool-call chain. When a workflow fails mid-step, operators cannot see which tool failed, how long it took, or what the causal chain was.

**Approach:**
1. Add a `trace` module (`src/sovereign_agent/trace/`) that implements OpenTelemetry-compatible spans:
   - `Span` dataclass: `trace_id`, `parent_id`, `name`, `start_time`, `end_time`, `attributes`, `status`
   - `TraceRecorder` — append-only NDJSON ledger (same pattern as epistemic ledger, checkpoint chunks)
   - `TraceContext` — thread-local context that tracks the current span stack
2. Instrument the agent loop (`loop.py`) to create a root span per user message, with child spans for each tool call.
3. Instrument the MCP server to create spans for each MCP tool invocation.
4. Add a `trace_query` tool (T0) that lets operators search traces by trace_id, tool name, time range, or status (error/success).
5. Add a `trace_summary` sentinel that computes p50/p95/p99 latency per tool and flags regressions.

**Files to create:**
- `src/sovereign_agent/trace/__init__.py`
- `src/sovereign_agent/trace/span.py`
- `src/sovereign_agent/trace/recorder.py`
- `src/sovereign_agent/trace/context.py`

**Files to modify:**
- `src/sovereign_agent/loop.py` — root span creation
- `src/sovereign_agent/mcp_server.py` — MCP tool spans
- `src/sovereign_agent/tools/runner.py` — per-tool spans
- `src/sovereign_agent/stewardship/registry.py` — register trace_summary sentinel

**Validation:**
- Verify traces are written to the NDJSON ledger in append-only fashion
- Verify trace_query returns correct results for synthetic traces
- Verify trace_summary sentinel detects latency regressions in test data
- Run existing test suite to ensure no regressions in loop.py

---

### 2.3 — Feedback-Driven Agent Loop (Medium Priority)

**Problem:** The `feedback/` module stores operator ratings (thumbs up/down) but they are never consumed by the agent loop. The ratings sit in the database and are never used to adjust behavior.

**Approach:**
1. Add a `feedback_router` that reads recent feedback (last N sessions) and produces a `FeedbackProfile` — a structured summary of what the operator liked/disliked.
2. Wire the `FeedbackProfile` into the prompt builder (`core/prompt_builder.py`) so that the model receives operator preferences at the start of each session.
3. Add a `feedback_adjust` tool (T1) that lets the operator adjust specific behaviors inline (e.g., "be more concise," "use more structured output," "avoid shell commands"). These adjustments are persisted and surfaced in the prompt.
4. Add a `feedback_digest` CLI command (`sov feedback digest`) that shows a summary of recent ratings with trends.

**Files to modify:**
- `src/sovereign_agent/feedback/feedback.py` — add FeedbackProfile class
- `src/sovereign_agent/core/prompt_builder.py` — inject feedback context
- `src/sovereign_agent/cli.py` — add `feedback` command group
- `src/sovereign_agent/tools/` — add feedback_adjust tool

**Validation:**
- Verify FeedbackProfile correctly aggregates ratings from the feedback DB
- Verify prompt_builder includes feedback context when available
- Verify `sov feedback digest` produces correct output
- Run existing test suite

---

### 2.4 — Peig-Engine Formal Integration (Medium Priority)

**Problem:** The peig-engine lives in a separate repo (`/home/kmon/AA-Erebo/peig-engine/`) and is not a declared dependency. The sovereign agent references it via `peig_sentinel.py` and `peig_portrait_tool.py`, but there's no `pip install` path, no version pinning, and no clean integration layer.

**Approach:**
1. Add peig-engine as an optional dependency in `pyproject.toml` under a new `[project.optional-dependencies]` group (e.g., `peig`).
2. Create a clean integration layer at `src/sovereign_agent/peig/` that:
   - Imports from the peig-engine package with graceful degradation if not installed
   - Provides a `PeigState` adapter that normalizes peig-engine's output to Aria's sentinel interface
   - Exposes a `peig_status` MCP tool (T0) that returns the current PEIG coherence state
3. Update the peig sentinel to use the integration layer instead of direct imports.
4. Update `install.sh` to offer `peig` as an optional install group.

**Files to modify:**
- `pyproject.toml` — add `peig` optional dependency group
- `src/sovereign_agent/stewardship/peig_sentinel.py` — use integration layer
- `src/sovereign_agent/mcp_server.py` — add `peig_status` tool
- `install.sh` — add peig group option

**Files to create:**
- `src/sovereign_agent/peig/__init__.py`
- `src/sovereign_agent/peig/adapter.py`

**Validation:**
- Verify peig-engine imports work when installed, degrade gracefully when not
- Verify `peig_status` MCP tool returns correct structure
- Verify peig sentinel uses the adapter layer
- Run existing test suite

---

### 2.5 — Evaluation & Regression Benchmark Suite (Medium Priority)

**Problem:** The proving-ground wings (quality, grounding, wellbeing, integrity, timeout) each have their own scoring engines, but there's no systematic benchmark suite that runs across all wings, tracks scores over time, and detects regressions automatically.

**Approach:**
1. Add a `benchmark` module (`src/sovereign_agent/benchmark/`) that:
   - Defines a standard benchmark set (fixed prompts + expected tool calls + expected quality thresholds)
   - Runs all proving-ground wings against the benchmark set
   - Records results in a `benchmark_results.ndjson` ledger (append-only, same pattern as other ledgers)
   - Compares current results against a baseline (last N runs or a pinned baseline)
   - Reports regressions (score drops below threshold) as sentinel findings
2. Add a `benchmark_run` CLI command (`sov benchmark run`) that executes the full suite.
3. Add a `benchmark_status` sentinel that checks for regressions and reports them in the doctor output.
4. Wire the benchmark results into the cockpit's system health panel.

**Files to create:**
- `src/sovereign_agent/benchmark/__init__.py`
- `src/sovereign_agent/benchmark/runner.py`
- `src/sovereign_agent/benchmark/prompts.py` — standard benchmark prompts
- `src/sovereign_agent/benchmark/regression.py` — regression detection logic
- `src/sovereign_agent/benchmark/ledger.py` — benchmark results ledger

**Files to modify:**
- `src/sovereign_agent/cli.py` — add `benchmark` command group
- `src/sovereign_agent/stewardship/registry.py` — register benchmark_status sentinel
- `src/sovereign_agent/doctor.py` — include benchmark status

**Validation:**
- Verify benchmark runner completes all wing tests and writes results to ledger
- Verify regression detection correctly flags score drops
- Verify `sov benchmark run` produces correct output
- Verify benchmark_status sentinel appears in `sov doctor` output
- Run existing test suite

---

### 2.6 — Canary Testing for Module Applies (Medium Priority)

**Problem:** The `safe_apply` pipeline has guard, snapshot, advocate gate, and auto-rollback, but no automated canary testing. When a new module is applied, it goes live immediately after the advocate gate passes, with no intermediate "does this actually work in a live context" step.

**Approach:**
1. Add a `canary` module (`src/sovereign_agent/canary/`) that:
   - After `safe_apply` applies a module, runs a lightweight smoke test against it
   - The smoke test is defined per-module (each `aria-*/README.md` should declare a `smoke_test` command)
   - If the smoke test fails, the module is automatically rolled back (using the existing snapshot/rollback mechanism)
   - Results are recorded in a `canary_ledger.ndjson`
2. Add a `canary_run` CLI command (`sov canary run <module>`) for manual canary testing.
3. Add a `canary_status` sentinel that checks for any modules that failed their canary and reports them.

**Files to create:**
- `src/sovereign_agent/canary/__init__.py`
- `src/sovereign_agent/canary/runner.py`
- `src/sovereign_agent/canary/ledger.py`

**Files to modify:**
- `src/sovereign_agent/cli.py` — add `canary` command group
- `src/sovereign_agent/stewardship/registry.py` — register canary_status sentinel
- `src/sovereign_agent/code_update.py` — integrate canary step after apply

**Validation:**
- Verify canary runner executes smoke tests after apply
- Verify failed canary triggers rollback
- Verify canary_ledger.ndjson records results correctly
- Verify canary_status sentinel reports failures in doctor output
- Run existing test suite

---

### 2.7 — Docker Deployment & Cross-Platform Support (Low Priority)

**Problem:** The system is Linux-only and requires manual setup. The `future-placeholders/` directory has a `docker-launch` idea and a `platform-compat` idea that are still unbuilt.

**Approach:**
1. Create a `Dockerfile` that:
   - Uses a slim Python 3.11 base image
   - Installs uv, runs `uv sync --no-dev`
   - Sets up the data/config directories with proper permissions
   - Exposes the MCP SSE port (8765) and the cockpit port
   - Includes a health check that runs `sov doctor`
2. Create a `docker-compose.yml` for local deployment with volume mounts for data persistence.
3. Add a `platform-compat` layer that detects the OS and adjusts paths, shell commands, and service management accordingly (Linux systemd, macOS launchd, Windows task scheduler).

**Files to create:**
- `Dockerfile`
- `docker-compose.yml`
- `src/sovereign_agent/platform_compat/__init__.py`

**Validation:**
- Verify Docker build succeeds
- Verify `docker-compose up` starts the agent correctly
- Verify `sov doctor` works inside the container
- Verify platform-compat layer correctly detects OS and adjusts behavior

---

## 3. Implementation Order

The enhancements are ordered by priority and dependency:

1. **MCP Server Expansion** (2.1) — highest impact, lowest risk, no dependencies on other enhancements
2. **Structured Observability** (2.2) — foundational; other enhancements (feedback, canary, benchmark) benefit from tracing
3. **Feedback-Driven Agent Loop** (2.3) — depends on tracing for measuring feedback impact
4. **Peig-Engine Integration** (2.4) — independent of other enhancements
5. **Evaluation & Regression Suite** (2.5) — depends on tracing for latency regression detection
6. **Canary Testing** (2.6) — depends on tracing for canary result observability
7. **Docker/Platform** (2.7) — independent, lowest priority

---

## 4. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| MCP `run_tool` could expose dangerous tools to external clients | Whitelist flag (`--mcp-tools`), tier ceiling enforcement, Tier 3 requires approval |
| Tracing overhead could slow the agent loop | Async span recording, configurable sampling rate, spans disabled by default in production |
| Feedback loop could create feedback bias (model over-optimizes for ratings) | Feedback is advisory only, never overrides kernel commitments; bounded influence |
| Peeg-engine integration adds a hard dependency | Optional dependency group, graceful degradation, adapter pattern isolates the integration |
| Benchmark suite becomes stale if prompts drift | Benchmark prompts are versioned and reviewed as part of the module apply process |
| Canary false positives roll back good modules | Smoke tests must pass 3/3 times before rollback is triggered; manual override available |

---

## 5. Open Questions

1. **MCP `run_tool` scope** — Should `run_tool` allow any tool in the registry, or should it be limited to a curated subset? The whitelist flag (`--mcp-tools`) addresses this, but the default set needs a decision.
2. **Tracing format** — OpenTelemetry is the standard, but the system uses NDJSON for all its ledgers. Should traces use OTLP format or the existing NDJSON convention?
3. **Benchmark prompt curation** — Who curates the standard benchmark prompts? The operator? The system itself via the hyperintel research tool?
4. **Canary smoke test definition** — Should each `aria-*/README.md` declare a `smoke_test` field, or should there be a centralized registry of smoke tests?
5. **Peig-engine versioning** — What version of peig-engine should be pinned, and how should version mismatches be handled?

---

## 6. Validation Plan

1. Run the full test suite after each enhancement: `pytest tests/ -x -q`
2. Run `sov doctor` after each enhancement to verify no regressions in sentinel health
3. Run `sov doctor --fix` to verify auto-fix still works
4. For MCP expansion: test with a real MCP client (Claude Desktop config) to verify tools are discoverable and callable
5. For tracing: verify trace output is valid NDJSON and can be queried
6. For feedback: verify feedback profile is correctly injected into prompts
7. For peig integration: verify graceful degradation when peig-engine is not installed
8. For benchmarks: verify regression detection works against synthetic score drops
9. For canary: verify rollback triggers on smoke test failure
10. For Docker: verify build and `docker-compose up` work end-to-end
