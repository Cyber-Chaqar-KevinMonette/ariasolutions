#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/auto_crown.py', 'r') as f:
    content = f.read()

old = '''TRUST_TIER_MAX_HOURS: dict[int, float] = {
    1: 1.0,
    2: 2.0,
    3: 4.0,
    4: 12.0,
}'''

new = '''TRUST_TIER_MAX_HOURS: dict[int, float] = {
    1: 2.0,
    2: 3.0,
    3: 5.0,
    4: 13.0,
}'''

if old in content:
    content = content.replace(old, new)
    with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/auto_crown.py', 'w') as f:
        f.write(content)
    print("Successfully extended trust tier max hours by +1")
else:
    print("Could not find the exact text")
    print("Looking for:", repr(old[:100]))