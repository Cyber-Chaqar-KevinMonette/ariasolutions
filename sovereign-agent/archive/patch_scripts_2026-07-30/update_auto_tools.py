#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/tools/auto_tools.py', 'r') as f:
    content = f.read()

old = 'le=12.0,  # duration-ceiling-raise-d — matches TRUST_TIER_MAX_HOURS[4]'
new = 'le=13.0,  # duration-ceiling-raise-d — matches TRUST_TIER_MAX_HOURS[4]'

if old in content:
    content = content.replace(old, new)
    with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/tools/auto_tools.py', 'w') as f:
        f.write(content)
    print("Successfully updated auto_tools duration ceiling to 13.0")
else:
    print("Could not find the exact text")
    print("Looking for:", repr(old[:100]))