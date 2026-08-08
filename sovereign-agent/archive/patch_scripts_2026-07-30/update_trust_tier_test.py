#!/usr/bin/env python3
with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_custom_auto_hours.py', 'r') as f:
    content = f.read()

# Update test_custom_hours_trust_tier_picks_the_lowest_sufficient_tier
# With new tier hours: 1:2.0, 2:3.0, 3:5.0, 4:13.0
content = content.replace(
    '''def test_custom_hours_trust_tier_picks_the_lowest_sufficient_tier():
    assert custom_hours_trust_tier(0.5) == 1
    assert custom_hours_trust_tier(1.0) == 1
    assert custom_hours_trust_tier(1.5) == 2
    assert custom_hours_trust_tier(3.0) == 3
    assert custom_hours_trust_tier(4.0) == 3
    assert custom_hours_trust_tier(5.0) == 4
    assert custom_hours_trust_tier(12.0) == 4''',
    '''def test_custom_hours_trust_tier_picks_the_lowest_sufficient_tier():
    assert custom_hours_trust_tier(0.5) == 1
    assert custom_hours_trust_tier(1.0) == 1
    assert custom_hours_trust_tier(2.0) == 1
    assert custom_hours_trust_tier(2.5) == 2
    assert custom_hours_trust_tier(3.0) == 2
    assert custom_hours_trust_tier(4.0) == 3
    assert custom_hours_trust_tier(5.0) == 3
    assert custom_hours_trust_tier(6.0) == 4
    assert custom_hours_trust_tier(13.0) == 4'''
)

with open('/home/kmon/AA-Erebo/sovereign-agent/tests/test_custom_auto_hours.py', 'w') as f:
    f.write(content)
print("Updated test_custom_hours_trust_tier_picks_the_lowest_sufficient_tier")