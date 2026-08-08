"""This module has no payload/ package — it's a patcher for cockpit/app.py, not a
new importable package. Just put the module's own directory on sys.path so
`import patcher` resolves."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
