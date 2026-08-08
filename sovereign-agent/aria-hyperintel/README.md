# aria-hyperintel — the HyperIntel research faculty (Workstream H4)

> From the HighIntensityResearch MOS draft in `Plans/`: a bounded QUESTION → SCAN → CROSS → AUDIT →
> DISTILL loop, as a tool Aria can invoke for deep-research turns — parallels how Claude Code's own
> Explore/Plan agents work. Three prompting postures over one process (Scout/Auditor/Synthesist),
> not three separate agents.

## What it does

A **single bounded pass** over a fixed, caller-supplied list of source files — never an
autonomous, self-re-querying loop (that would violate the "no unbounded recursive research"
doctrine). It never fetches new sources on its own initiative.

1. **Scan** — read up to `max_sources` files (hard cap, never exceeded).
2. **Cross-validate** — a claim is only "convergent" if a line with substantial keyword overlap
   appears in **2+ independent sources**. A single-source claim is flagged as a hypothesis, never
   silently promoted to "trusted."
3. **Audit** — explicitly names risk/uncertainty (too few sources, a shallow evidence base, nothing
   readable).
4. **Distill** — one paragraph: what's corroborated, what's a hypothesis, how many risks were found.

## Payload
- `src/sovereign_agent/hyperintel/engine.py` — `scan()`, `cross_validate()`, `audit()`, `distill()`,
  `run()` (the full pass), `HyperIntelReport.to_markdown()`.
- `src/sovereign_agent/tools/hyperintel_tool.py` — `HyperIntelTool` (Tier 1, propose-only): the
  `hyperintel_research` tool Aria can invoke.

## Use
```python
from sovereign_agent.hyperintel import run

report = run("what fixed the cockpit crash?", ["notes/a.md", "notes/b.md"], max_sources=8)
print(report.to_markdown())
```
```
# via the tool
hyperintel_research(question="...", source_paths=["a.md", "b.md"], max_sources=8)
```

## Verify / Apply
```bash
./scripts/verify_module.sh aria-hyperintel   # before apply (read-only)
./aria-hyperintel/apply_hyperintel.sh        # cockpit stopped
```
