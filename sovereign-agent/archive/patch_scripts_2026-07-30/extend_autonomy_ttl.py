#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/autonomy/session.py', 'r') as f:
    content = f.read()

old = 'MAX_TTL_SECONDS = 2 * 60 * 60      # 2 hours; beyond this is a Tier-3 decision'
new = 'MAX_TTL_SECONDS = 3 * 60 * 60      # 3 hours; beyond this is a Tier-3 decision'

if old in content:
    content = content.replace(old, new)
    with open('/home/kmon/AA-Erebo/sovereign-agent/src/sovereign_agent/autonomy/session.py', 'w') as f:
        f.write(content)
    print("Successfully extended autonomy MAX_TTL_SECONDS by +1 hour")
else:
    print("Could not find the exact text")
    print("Looking for:", repr(old[:100]))