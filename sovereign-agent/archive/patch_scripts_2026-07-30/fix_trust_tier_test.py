#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_custom_auto_hours.py', 'r') as f:
    lines = f.readlines()

# Find and update the test
for i, line in enumerate(lines):
    if 'assert custom_hours_trust_tier(1.5) == 2' in line:
        lines[i] = '    assert custom_hours_trust_tier(2.5) == 2\n'
    elif 'assert custom_hours_trust_tier(3.0) == 3' in line:
        lines[i] = '    assert custom_hours_trust_tier(4.0) == 3\n'
    elif 'assert custom_hours_trust_tier(4.0) == 3' in line:
        lines[i] = '    assert custom_hours_trust_tier(5.0) == 3\n'
    elif 'assert custom_hours_trust_tier(5.0) == 4' in line:
        lines[i] = '    assert custom_hours_trust_tier(6.0) == 4\n'
    elif 'assert custom_hours_trust_tier(13.0) == 4' in line and i > 30:
        # Keep this one as is, but add 14.0 test after it
        pass

# Add 14.0 test after the 13.0 test
for i, line in enumerate(lines):
    if 'assert custom_hours_trust_tier(13.0) == 4' in line:
        lines.insert(i + 1, '    assert custom_hours_trust_tier(14.0) == 4\n')
        break

with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_custom_auto_hours.py', 'w') as f:
    f.writelines(lines)
print("Updated test_custom_hours_trust_tier_picks_the_lowest_sufficient_tier")