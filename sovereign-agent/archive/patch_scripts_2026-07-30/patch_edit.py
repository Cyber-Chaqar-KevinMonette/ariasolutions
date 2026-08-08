#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/tools/edit.py', 'r') as f:
    content = f.read()

old = '''    Args = EditArgs

    async def execute(self, args: EditArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002'''

new = '''    Args = EditArgs

    def __init__(self, mode: Mode | None = None) -> None:
        self._mode = mode or Mode.ONESHOT

    async def execute(self, args: EditArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002'''

if old in content:
    content = content.replace(old, new)
    with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/tools/edit.py', 'w') as f:
        f.write(content)
    print("Successfully patched edit.py")
else:
    print("Could not find the exact text")
    print("Looking for:", repr(old[:100]))