"""Patch registry.py to add SENTINEL_REGISTRY public alias."""
import sys

path = sys.argv[1]
src = open(path).read()

addition = '\nSENTINEL_REGISTRY = _REGISTRY  # public alias for external consumers  # sentinel-registry-alias-d\n'
all_addition = '\n    "SENTINEL_REGISTRY",'

if "sentinel-registry-alias-d" in src:
    print("  already present")
    sys.exit(0)

# Add alias before __all__
anchor = '\n__all__ = ['
if anchor not in src:
    print(f"ERROR: __all__ anchor not found in {path}", file=sys.stderr)
    sys.exit(1)

src = src.replace(anchor, addition + anchor)

# Add to __all__
all_anchor = '    "register_sentinel",'
if all_anchor in src:
    src = src.replace(all_anchor, '    "SENTINEL_REGISTRY",' + '\n' + all_anchor, 1)

open(path, "w").write(src)
print("  patched registry.py")
