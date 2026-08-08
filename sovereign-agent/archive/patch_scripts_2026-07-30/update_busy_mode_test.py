#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_cli.py', 'r') as f:
    content = f.read()

# Update test to expect tier 4 for busy mode
content = content.replace(
    'assert payload["tier_ceiling"] == 1',
    'assert payload["tier_ceiling"] == 4'
)

with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_cli.py', 'w') as f:
    f.write(content)
print("Updated test to expect tier 4 for busy mode")