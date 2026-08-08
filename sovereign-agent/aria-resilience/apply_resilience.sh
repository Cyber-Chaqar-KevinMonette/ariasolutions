#!/usr/bin/env bash
# apply_resilience.sh — M34: circuit breaker + exponential backoff
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M34 resilience: $REPO"

cp "$REPO/aria-resilience/payload/src/sovereign_agent/resilience.py" \
   "$REPO/src/sovereign_agent/resilience.py"
echo "  OK   copied resilience.py"

cp "$REPO/aria-resilience/payload/src/sovereign_agent/tools/resilience_tools.py" \
   "$REPO/src/sovereign_agent/tools/resilience_tools.py"
echo "  OK   copied resilience_tools.py"

python3 - "$REPO" <<'PYEOF'
import sys
from pathlib import Path

repo = Path(sys.argv[1])

def patch(path, old, new, marker):
    src = path.read_text()
    if marker in src:
        print(f"  SKIP {path.name} — already patched ({marker})")
        return False
    if old not in src:
        print(f"  ERROR {path.name} — anchor not found for {marker}", file=sys.stderr)
        print(f"  Searched for: {old[:80]!r}", file=sys.stderr)
        sys.exit(1)
    path.write_text(src.replace(old, new, 1))
    print(f"  OK   {path.name} ({marker})")
    return True

loop = repo / "src/sovereign_agent/loop.py"
ollama = repo / "src/sovereign_agent/ollama_client.py"
init = repo / "src/sovereign_agent/tools/__init__.py"

# ── loop.py: import BreakerRegistry ──────────────────────────────────────────
patch(loop,
    old='from .cache import ResponseCache as _ResponseCache  # cache-crown-import-d',
    new='from .cache import ResponseCache as _ResponseCache  # cache-crown-import-d\nfrom .resilience import BreakerRegistry as _BreakerRegistry  # resilience-import-d',
    marker="resilience-import-d",
)

# ── loop.py: module-level registry singleton ──────────────────────────────────
patch(loop,
    old='_response_cache = _ResponseCache()  # T0 response cache, session-scoped  # cache-crown-singleton-d',
    new='_response_cache = _ResponseCache()  # T0 response cache, session-scoped  # cache-crown-singleton-d\n_breaker_registry = _BreakerRegistry()  # per-tool circuit breakers  # resilience-singleton-d',
    marker="resilience-singleton-d",
)

# ── loop.py: circuit breaker gate before tool dispatch ───────────────────────
patch(loop,
    old='                # ── Cache check (T0 read-only tools only) ──────────────  # cache-crown-dispatch-d',
    new='''\
                # ── Circuit breaker gate ─────────────────────────────  # resilience-tool-gate-d
                _tool_breaker = _breaker_registry.get_breaker(f"tool:{tool_name}")
                if not _tool_breaker.call_allowed():
                    _record("circuit-open-x", {"tool": tool_name})
                    messages.append({
                        "role": "tool", "name": tool_name,
                        "content": (
                            f"REFUSED: circuit breaker OPEN for {tool_name} "
                            f"(repeated failures). Try again in ~60s or call "
                            f"resilience_status() to see all breaker states."
                        ),
                    })
                    continue

                # ── Cache check (T0 read-only tools only) ──────────────  # cache-crown-dispatch-d''',
    marker="resilience-tool-gate-d",
)

# ── loop.py: record outcome in breaker after execute ─────────────────────────
patch(loop,
    old='                result: ToolResult = await tool.execute(parsed, trace_id=trace_id)\n                # ── Invariant 2: one event per action ────────────────',
    new='''\
                result: ToolResult = await tool.execute(parsed, trace_id=trace_id)
                # ── Resilience: record tool outcome in circuit breaker ─  # resilience-record-d
                if result.ok:
                    _tool_breaker.record_success()
                else:
                    _tool_breaker.record_failure()
                # ── Invariant 2: one event per action ────────────────''',
    marker="resilience-record-d",
)

# ── loop.py: RESILIENCE doctrine ─────────────────────────────────────────────
patch(loop,
    old='═══ CACHE CROWN ═══  # cache-crown-doctrine-d',
    new='''\
═══ RESILIENCE ═══  # resilience-doctrine-d
The loop has circuit breakers for every tool and LLM connection.
When a tool fails 3 times in a row, its breaker opens and calls are blocked
temporarily. After ~60 seconds, one probe call is allowed through (HALF_OPEN).
  resilience_status()  → see all breaker states right now (T0)

If you see "circuit open" refusals: try an alternative tool, or wait.
If resilience_status() shows many open breakers: something systemic is wrong.
Report to Kevin before continuing. The circuit breaker is your safety net.

═══ CACHE CROWN ═══  # cache-crown-doctrine-d''',
    marker="resilience-doctrine-d",
)

# ── ollama_client.py: retry with backoff on transient errors ─────────────────
patch(ollama,
    old='        response = await self._aclient.chat(**kwargs)\n        return response if isinstance(response, dict) else response.model_dump()',
    new='''\
        # ── Resilience: retry with exponential backoff on transient errors  # resilience-llm-retry-d
        import asyncio as _asyncio
        from .resilience import exponential_backoff as _backoff
        _llm_last_err: Exception | None = None
        for _llm_attempt in range(3):
            try:
                _resp = await self._aclient.chat(**kwargs)
                return _resp if isinstance(_resp, dict) else _resp.model_dump()
            except Exception as _llm_err:  # noqa: BLE001
                _s = (type(_llm_err).__name__ + str(_llm_err)).lower()
                _is_transient = any(k in _s for k in
                    ("connect", "timeout", "network", "reset", "refused", "eof"))
                if not _is_transient or _llm_attempt >= 2:
                    raise
                _llm_last_err = _llm_err
                await _asyncio.sleep(_backoff(_llm_attempt))
        raise _llm_last_err  # type: ignore[misc]''',
    marker="resilience-llm-retry-d",
)

# ── tools/__init__.py: import resilience_tools ───────────────────────────────
patch(init,
    old='from .cache_tools import (  # cache-crown-import-d',
    new='''\
from .resilience_tools import ResilienceStatusTool  # resilience-import-d
from .cache_tools import (  # cache-crown-import-d''',
    marker="resilience-import-d",
)

# ── tools/__init__.py: add to __all__ ────────────────────────────────────────
patch(init,
    old='    "CacheStatsTool",             # cache-crown-all-d',
    new='''\
    "ResilienceStatusTool",       # resilience-all-d
    "CacheStatsTool",             # cache-crown-all-d''',
    marker="resilience-all-d",
)

print("M34 resilience: all patches applied.")
PYEOF

cp "$REPO/aria-resilience/tests/test_resilience.py" "$REPO/tests/test_resilience.py"
echo "==> M34 done. Run: .venv/bin/python -m pytest tests/test_resilience.py -q"
