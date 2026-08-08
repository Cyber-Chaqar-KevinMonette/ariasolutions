#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/modes.py', 'r') as f:
    content = f.read()

old = '''MODE_TIER_CEILING: dict[Mode, int] = {
    Mode.ONESHOT: 3,  # all tiers, but T3 still requires approval token
    Mode.TIMED: 3,
    Mode.UNTIL: 3,
    Mode.BUSY: 1,     # the load-bearing safety design
}'''

new = '''MODE_TIER_CEILING: dict[Mode, int] = {
    Mode.ONESHOT: 3,  # all tiers, but T3 still requires approval token
    Mode.TIMED: 3,
    Mode.UNTIL: 3,
    Mode.BUSY: 4,     # temporarily raised for testing
}'''

if old in content:
    content = content.replace(old, new)
    with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/modes.py', 'w') as f:
        f.write(content)
    print("Successfully raised BUSY mode tier ceiling to 4")
else:
    print("Could not find the exact text")
    print("Looking for:", repr(old[:200]))