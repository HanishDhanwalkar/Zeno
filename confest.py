"""Pytest bootstrap: make the hyphenated package dirs importable.

Python can't import a dir named ``zeno-ai`` directly, so we add each package
directory (which contains an underscore module) to sys.path.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).parent
for _pkg in ("zeno-ai", "zeno-agent-core"):
    _path = _ROOT / "packages" / _pkg
    if _path.is_dir():
        sys.path.insert(0, str(_path))
