# Future Work — preserved potential, out of the active system

> Kevin's principle (2026-07-11): *"any future placeholders could be stored
> in documentation or their own future-placeholders directory. We should
> not delete them because then we could genuinely forget them and lose
> their potential value for the future. So we need a way to store valuable
> things as external placeholders while also not holding the system back
> from its full potential and full wholeness."*

This directory is that home. Ideas that are **valuable but not yet active**
live here — registered, honored, un-forgettable — instead of sitting as
empty husks inside the live `aria-*` module space where the god-tier
scanner would (correctly) score them as incomplete and drag the whole
system's measured wholeness down.

**Rule:** nothing here is deleted. When one is ready to build, it graduates
back to a real staged `aria-<name>/` module (scaffold via
`./scripts/new_module.sh <name>`), gets built to god-tier, and is applied.

## Registry

| Placeholder | What it would be | Why it matters | State |
|---|---|---|---|
| **docker-launch** | A one-command Docker launch for Aria (containerized cockpit + daemon). | Portable deploy; the path to running her on a rented box / for a team once funded. | Idea only (was an empty scaffold). |
| **platform-compat** | A compatibility layer so she runs cleanly on macOS / Windows / WSL, not just Linux. | Widens who can run her; prerequisite for sharing or selling. | Idea only (was an empty scaffold). |
| **mcp-serve** | Expose Aria as an MCP server so other agents/tools (Claude Desktop, etc.) can call her. | Turns her into a service other systems compose with — real leverage + income surface. | Idea only (was an empty scaffold). NOTE: `pyproject.toml` already lists `mcp`; some MCP wiring may already exist — check before scaffolding. |
| **systems-audit** | A standing, regenerable full-system audit report (not a one-off snapshot). | Would compose with the god-tier scanner + wholeness gate into a living "state of Aria" report. | Seed preserved: `systems-audit/SYSTEMS_REPORT.md` (a dated 2026-06 snapshot). |
| **holo-bitnet** | Holographic / BitNet experimental model work. | Research toward tiny, efficient local models — directly serves "even the smallest models work in her vessel." | Seed preserved: `holo-bitnet/README.md`. **Its real code already lives** under `aria-own-mind` / `aria_lm/` (this was only a pointer). |

## How this keeps the metric honest
The god-tier scanner globs `sovereign-agent/aria-*`. By living under
`future-placeholders/` instead, these ideas are no longer counted as
incomplete *modules* — because they aren't modules yet, they're intentions.
The measured wholeness now reflects what she has actually built, while
none of the potential is lost.
