import json
import logging
import os
import sys
from typing import Any, Mapping

_BASIC_CONFIGURED = False


def _configure_once(level: int | None = None) -> None:
    global _BASIC_CONFIGURED
    if not _BASIC_CONFIGURED:
        # Determine desired log level: env wins, else argument, else DEBUG (show everything)
        env_level = os.getenv("UNICRON_LOG_LEVEL", "DEBUG").upper()
        resolved_level = getattr(logging, env_level, None)
        if resolved_level is None:
            resolved_level = logging.DEBUG
        if level is not None and level < resolved_level:
            # If caller explicitly asked for *more* verbosity (numerically lower), honor it
            resolved_level = level

        # Force ensures we override any prior basicConfig (e.g., uvicorn's early setup)
        logging.basicConfig(
            level=resolved_level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
            force=True,
        )
        _BASIC_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure_once()
    # Avoid duplicating prefix if caller already passed a fully-qualified project logger name
    prefix = "unicron.backend"
    if name.startswith(prefix):
        full_name = name
    elif name.startswith("backend."):
        full_name = f"{prefix}.{name[len('backend.'):]}"
    else:
        full_name = f"{prefix}.{name}"
    return logging.getLogger(full_name)


# Default project logger for dependencies
logger = get_logger("unicron.backend")
