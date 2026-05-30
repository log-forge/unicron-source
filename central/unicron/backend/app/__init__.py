"""Backend application package bootstrap."""

from __future__ import annotations

import sys
from importlib.util import find_spec
from pathlib import Path


def _ensure_unicron_shared_import_path() -> None:
    """Best-effort local import bootstrap for ``unicron_shared``.

    Production images install/copy this package explicitly. Local unittest runs
    from source may not, so we add known repository paths only when necessary.
    """
    if find_spec("unicron_shared") is not None:
        return

    candidates = [
        Path(__file__).resolve().parents[4] / "libs" / "unicron_shared",
        Path("/unicron_shared"),
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        candidate_path = str(candidate)
        if candidate_path not in sys.path:
            sys.path.insert(0, candidate_path)
        if find_spec("unicron_shared") is not None:
            return


_ensure_unicron_shared_import_path()
