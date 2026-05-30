"""Backend test package bootstrap."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure local shared library imports resolve in direct unittest runs.
_repo_root = Path(__file__).resolve().parents[4]
_shared_lib = _repo_root / "libs" / "unicron_shared"
if _shared_lib.exists():
    shared_path = str(_shared_lib)
    if shared_path not in sys.path:
        sys.path.insert(0, shared_path)
