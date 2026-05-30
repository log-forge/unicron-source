"""Herald-side Socket.IO helpers (ACK parsing, etc.)."""

from typing import Any, Optional, Tuple

from app.core.logging import get_logger
from pydantic import BaseModel

from unicron_shared import AckErr, AckOk

logger = get_logger(__name__)


def inspect_ack(
    raw_ack: Any,
    *,
    ok_data_model: Optional[type[BaseModel]] = None,
    log_context: str = "",
    _logger=logger,
) -> Tuple[bool, Any]:
    """Normalize and optionally log a Socket.IO ACK payload.

    Returns (True, data) for AckOk or (False, error_list_or_msg) for AckErr/malformed.
    If ok_data_model is provided and the ACK is ok, data is validated into that model.
    """
    try:
        ok = AckOk.model_validate(raw_ack)
        data = ok.data
        if ok_data_model is not None:
            try:
                data = ok_data_model.model_validate(data or {})
            except Exception as exc:
                if _logger:
                    _logger.warning(f"{log_context} ok-ack data validation failed: {exc}")
                return False, ["invalid-ok-data"]
        if _logger:
            dumped = data.model_dump() if isinstance(data, BaseModel) else data
            _logger.info(f"{log_context} -> ok: {dumped}")
        return True, data
    except Exception:
        pass

    try:
        err = AckErr.model_validate(raw_ack)
        if _logger:
            _logger.warning(f"{log_context} failed ack: {err}")
        return False, err.error or []
    except Exception:
        if _logger:
            _logger.warning(f"{log_context} malformed ack: {raw_ack}")
        return False, ["malformed-ack"]
