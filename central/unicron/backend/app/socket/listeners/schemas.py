from typing import Literal, Optional

from app.base_schemas import ContainerSelector
from app.telemetry.victoria.schemas import LogRow
from pydantic import BaseModel


class TailDataEvent(BaseModel):
    """
    Socket.IO payload for 'logs:tail:data'
    """

    type: Literal["logs:tail:data"] = "logs:tail:data"
    row: LogRow


class TailErrorEvent(BaseModel):
    """
    Socket.IO payload for 'logs:tail:error'
    """

    type: Literal["logs:tail:error"] = "logs:tail:error"
    error: str


class LogsTailPayload(ContainerSelector):
    """
    Live tail; boolean-only `filter` (no pipes).
    """

    filter: Optional[str] = None
    start_offset: Optional[str] = None  # e.g. "5m"
    offset: Optional[str] = None  # e.g. "1s"
    refresh_interval: Optional[str] = None
    account_id: Optional[int] = None
    project_id: Optional[int] = None
