from functools import wraps
from typing import Any, Optional, Tuple, TypeVar

from app.core.logging import get_logger
from pydantic import BaseModel, ValidationError

from unicron_shared import AckErr, AckOk

logger = get_logger(__name__)
T = TypeVar("T")


def validate_event(model_cls):
    """
    Decorator validating a single dict payload against a Pydantic model.
    Returns ack {ok: False, error: ...} on failure.
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(sid, data, *args, **kwargs):
            try:
                obj = model_cls(**data)
            except ValidationError as exc:
                logger.error(f"Validation error for event {fn.__name__}: {exc}")
                return AckErr(
                    ok=False,
                    error=[f"{err['loc'][-1]}: {err['msg']}" for err in exc.errors()],
                )
            return await fn(sid, obj, *args, **kwargs)

        return wrapper

    return decorator


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
