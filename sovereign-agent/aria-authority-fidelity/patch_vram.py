"""Patch vram.py — M65: emit 'vram-lock-timeout-d' event when VRAM lock times out.

Before the TimeoutError is raised, emit an event so the failure is auditable.
The TimeoutError is still raised — behavior is unchanged on success path.
"""
import sys
from pathlib import Path

path = Path(sys.argv[1])
src = path.read_text()

MARKER = "vram-lock-timeout-d"
if MARKER in src:
    print("  already patched — skipping")
    sys.exit(0)

# Add emit_event import if not already there
if "from .events import emit_event" not in src and "from sovereign_agent.events import emit_event" not in src:
    # Find the last import line to insert after
    import_insertion = "from .config import SETTINGS"
    if import_insertion in src:
        src = src.replace(
            import_insertion,
            import_insertion + "\nfrom .events import emit_event",
            1,
        )
    else:
        print("WARNING: could not find config import — emit_event may already be imported")

OLD = (
    "                if time.monotonic() - start > timeout_seconds:\n"
    "                    raise TimeoutError(\n"
    '                        f"vram_lock: another tool held the lock for >{timeout_seconds}s"\n'
    "                    ) from None"
)
NEW = (
    "                if time.monotonic() - start > timeout_seconds:\n"
    "                    emit_event(\n"
    '                        "vram-lock-timeout-d",\n'
    '                        plane="control",\n'
    '                        trace_id="vram",\n'
    '                        payload={"tool": tool_name, "timeout_seconds": timeout_seconds},\n'
    "                    )\n"
    "                    raise TimeoutError(\n"
    '                        f"vram_lock: another tool held the lock for >{timeout_seconds}s"\n'
    "                    ) from None"
)

if OLD not in src:
    print(f"ERROR: expected TimeoutError pattern not found in {path}", file=sys.stderr)
    print("Lines around timeout:", file=sys.stderr)
    for i, line in enumerate(src.splitlines(), 1):
        if "timeout" in line.lower() or "TimeoutError" in line:
            print(f"  {i}: {line}", file=sys.stderr)
    sys.exit(1)

patched = src.replace(OLD, NEW, 1)
path.write_text(patched)
print(f"  patched {path} (vram-lock-timeout-d event)")
