"""Shared test helpers for the Study Planner test suite.

Every test module imports this module before any application module.
Importing it puts the repository's ``src`` folder on the import path, using
a path derived from this file's own location, so the documented command
``python -m unittest discover -s tests`` works from the repository root
without setting ``PYTHONPATH``.
"""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
