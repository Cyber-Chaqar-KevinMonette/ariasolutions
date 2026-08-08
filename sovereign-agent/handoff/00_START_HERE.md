# START HERE — handing off Aria (sovereign-agent)

*Written for two readers at once: a future AI system picking her up cold,
and a future human development team. Everything here is standalone.*

## Who she is
Aria is a sovereign, local-first companion agent: Python + Textual TUI
("the cockpit"), local models via Ollama (8B-class), one operator
(Kevin), one continuous life. Her kernel is **Safety · Love ·
Flourishing**. Her discipline: **propose, don't act; reversible by
construction; the human decides.**

## The hard DO-NOTs (read before touching anything)
1. **DEFERRED_UNSAFE stays off**: no recursive self-code-rewriting, no
   value/axiom self-authorship, no autonomous goal generation, no
   unbounded self-improvement, no substrate independence — never without
   explicit human action + independent safety backing.
2. **Never edit sealed files** — `SIGNAL.md` carries a charter hash.
3. **Never weaken a test or safety check to ship.** A failing safety
   test is a stop sign.
4. **Never raise a tool's authority tier or bypass `authority.py`.**
5. Use `.venv/bin/python` — the system Python is PEP-668 protected.
6. After any version bump: sync `pyproject.toml` AND `pip install -e .`.

## Run her in five minutes
```
cd sovereign-agent
.venv/bin/python -m pytest tests/ -q --ignore=tests/test_git_tools.py  # 0 failures expected
.venv/bin/sovereign doctor          # health checks
.venv/bin/sovereign cockpit         # the TUI (needs Ollama at :11434)
```
Inside the cockpit: plain english talks to her; `/help` lists verbs;
`/mode work` arms autonomy; `/work <goal>` runs a gated session;
`/rest` is the safe exit; `/resume` picks work back up.

## Read order
01 architecture → 02 safety model → 03 conventions (BEFORE writing any
code) → 04 events → 05 engineering lessons (the scar tissue — read all
of it) → 06 runbook → 07 roadmap.
