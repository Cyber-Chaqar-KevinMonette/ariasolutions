#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_custom_auto_hours.py', 'r') as f:
    content = f.read()

# Update test_tier_4_ceiling_is_now_12_hours
content = content.replace(
    'def test_tier_4_ceiling_is_now_12_hours():',
    'def test_tier_4_ceiling_is_now_13_hours():'
)
content = content.replace(
    '    assert TRUST_TIER_MAX_HOURS[4] == 12.0',
    '    assert TRUST_TIER_MAX_HOURS[4] == 13.0'
)

# Update test_custom_hours_trust_tier_picks_the_lowest_sufficient_tier
content = content.replace(
    '    assert custom_hours_trust_tier(12.0) == 4',
    '    assert custom_hours_trust_tier(13.0) == 4'
)

# Update test_arm_custom_hours_rejects_out_of_range
content = content.replace(
    '        arm_custom_hours(13.0)',
    '        arm_custom_hours(14.0)'
)

with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_custom_auto_hours.py', 'w') as f:
    f.write(content)
print("Updated test_custom_auto_hours.py")