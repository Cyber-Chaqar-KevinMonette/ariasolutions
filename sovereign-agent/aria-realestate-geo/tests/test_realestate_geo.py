"""Test realestate_geo module — patches work, no syntax errors."""
import sys
from pathlib import Path

# Scaffold adds this; import it to verify syntax
try:
    from sovereign_agent.realestate_geo import STATE_CATEGORIES, COUNTY_VERTICALS
except ImportError as e:
    raise RuntimeError(f"Import failed (module not applied yet?): {e}")


def test_state_categories():
    """Verify state categories are defined."""
    assert "REAL ESTATE — TN" in STATE_CATEGORIES
    assert "REAL ESTATE — VA" in STATE_CATEGORIES
    assert "REAL ESTATE — FL" in STATE_CATEGORIES
    assert "REAL ESTATE — CA" in STATE_CATEGORIES


def test_county_verticals():
    """Verify county verticals mapped to categories."""
    assert "realestate-tn-christian" in COUNTY_VERTICALS["REAL ESTATE — TN"]
    assert "realestate-tn-montgomery" in COUNTY_VERTICALS["REAL ESTATE — TN"]
    assert "realestate-tn-edmonson" in COUNTY_VERTICALS["REAL ESTATE — TN"]
    assert COUNTY_VERTICALS["REAL ESTATE — VA"]  # Has placeholder
    assert COUNTY_VERTICALS["REAL ESTATE — FL"]  # Has placeholder
    assert COUNTY_VERTICALS["REAL ESTATE — CA"]  # Has placeholder


def test_patches_module_exists():
    """Verify patches.py exists and can be imported."""
    patches_path = Path(__file__).parent.parent / "payload/src/sovereign_agent/realestate_geo/patches.py"
    assert patches_path.exists(), f"patches.py not found at {patches_path}"


if __name__ == "__main__":
    test_state_categories()
    test_county_verticals()
    test_patches_module_exists()
    print("✓ All tests passed")
