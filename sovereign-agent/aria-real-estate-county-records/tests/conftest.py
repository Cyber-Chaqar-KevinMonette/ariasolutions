import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parents[2] / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

extend_paths(pathlib.Path(__file__).parent.parent)
