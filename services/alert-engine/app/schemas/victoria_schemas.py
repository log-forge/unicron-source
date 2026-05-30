"""Schemas for VictoriaLogs responses."""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LogMsgJSON(BaseModel):
    """Parsed structure when _msg contains JSON."""
    log: Optional[str] = None
    stream: Optional[str] = None
    time: Optional[str] = None


class LogRow(BaseModel):
    """
    One log entry from VictoriaLogs.

    VictoriaLogs returns NDJSON with underscore-prefixed metadata fields.
    We accept these via aliases.
    """
    # Core VL metadata (use aliases for underscore-prefixed input keys)
    time: Optional[datetime] = Field(default=None, alias="_time")
    stream_id: Optional[str] = Field(default=None, alias="_stream_id")
    stream: Optional[str] = Field(default=None, alias="_stream")

    # Message
    msg: Optional[str] = Field(default=None, alias="_msg")
    msg_json: Optional[LogMsgJSON] = Field(default=None)

    # Container context
    container_id: Optional[str] = None
    docker_container_id: Optional[str] = None
    container_key: Optional[str] = None
    container_name: Optional[str] = None
    herald_id: Optional[str] = None
    herald_name: Optional[str] = None
    image_name: Optional[str] = None
    service_name: Optional[str] = None
    severity: Optional[str] = None

    # Accept extra fields from Victoria
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @model_validator(mode="after")
    def parse_msg_json(self):
        """Auto-parse _msg if it contains JSON."""
        try:
            if isinstance(self.msg, str) and self.msg.lstrip().startswith("{"):
                parsed = json.loads(self.msg)
                if isinstance(parsed, dict):
                    self.msg_json = LogMsgJSON.model_validate(parsed)
        except Exception:
            pass
        return self


class LogQueryResponse(BaseModel):
    """Response from a logs query."""
    rows: List[LogRow]
    count: int
    query: str


class VictoriaError(BaseModel):
    """Error response from Victoria."""
    status: str
    error: Optional[str] = None
    message: Optional[str] = None


__all__ = ["LogRow", "LogMsgJSON", "LogQueryResponse", "VictoriaError"]
