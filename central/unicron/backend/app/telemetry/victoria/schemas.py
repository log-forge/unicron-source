import json as _json
from datetime import datetime
from typing import Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

# =========================
# LOGS (ROW SHAPE)
# =========================


class LogMsgJSON(BaseModel):
    """
    Parsed structure when `_msg` itself contains a JSON object string.
    Example from VMUI:
        "_msg": "{\"log\":\"\\\\ synthetic log line ...\",\"stream\":\"stdout\",\"time\":\"2025-10-22T20:59:31.455Z\"}"
    We parse once and expose as `msg_json` for convenience.
    """

    log: Optional[str] = None
    stream: Optional[str] = None
    time: Optional[str] = None


class LogRow(BaseModel):
    """
    One log entry from VictoriaLogs (/select/logsql/query or /tail).
    Matches your VMUI sample and allows extra fields produced by pipes.
    """

    # Core VL metadata (pydantic field names must not start with underscores).
    # We accept the original underscore-prefixed keys from Victoria via aliases.
    time: Optional[datetime] = Field(default=None, alias="_time", description="Event time (RFC3339)")
    stream_id: Optional[str] = Field(default=None, alias="_stream_id", description="Stable stream grouping id")
    stream: Optional[str] = Field(
        default=None, alias="_stream", description='Stringified label set for the stream (e.g. "{k="v",...}")'
    )

    # Message (store as `msg` but accept `_msg` in input)
    msg: Optional[str] = Field(default=None, alias="_msg", description="Raw message as stored")
    msg_json: Optional[LogMsgJSON] = Field(
        default=None, description="Parsed JSON from _msg, if _msg is a JSON object string"
    )

    # Container / service context (fields from your sample):
    collector_role: Optional[str] = None
    docker_container_id: Optional[str] = None
    container_key: Optional[str] = None
    container_name: Optional[str] = None
    herald_env: Optional[str] = None
    herald_id: Optional[str] = None
    herald_name: Optional[str] = None
    image_name: Optional[str] = None
    image_tag: Optional[str] = None
    service_instance_id: Optional[str] = None
    service_name: Optional[str] = None
    service_namespace: Optional[str] = None
    severity: Optional[str] = None

    # Accept any extra fields (e.g., from `fields`, `json_extract`, etc.)
    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def _parse_msg_json_if_present(self):
        """Auto-parse `_msg` when it's a JSON object string; keep `_msg` unchanged."""
        try:
            if isinstance(self.msg, str) and self.msg.lstrip().startswith("{"):
                parsed = _json.loads(self.msg)
                if isinstance(parsed, dict):
                    self.msg_json = LogMsgJSON.model_validate(parsed)
        except Exception:
            pass
        return self


# ============================================================
# METRICS (Prometheus/VictoriaMetrics API shapes)
# ============================================================
# Raw API union returned by /api/v1/query and /api/v1/query_range.
# See: https://docs.victoriametrics.com/victoriametrics/url-examples/ (instant & range queries)
#      https://prometheus.io/docs/prometheus/latest/querying/api/
# These match the canonical Prometheus/VictoriaMetrics responses.


class VMVectorSample(BaseModel):
    metric: Dict[str, str] = Field(description="Label set for this vector sample")
    value: Tuple[float, str] = Field(description="[unix_ts, value_as_string]")


class VMMatrixSample(BaseModel):
    metric: Dict[str, str] = Field(description="Label set for this series")
    values: List[Tuple[float, str]] = Field(description="List of [unix_ts, value_as_string]")


class VMVectorData(BaseModel):
    resultType: Literal["vector"] = "vector"
    result: List[VMVectorSample]


class VMMatrixData(BaseModel):
    resultType: Literal["matrix"] = "matrix"
    result: List[VMMatrixSample]


class VMScalarData(BaseModel):
    resultType: Literal["scalar"] = "scalar"
    result: Tuple[float, str]


class VMStringData(BaseModel):
    resultType: Literal["string"] = "string"
    result: Tuple[float, str]


VMData = Union[VMVectorData, VMMatrixData, VMScalarData, VMStringData]


# ============================================================
# METRICS (VMUI-style "flat" shapes) — optional convenience
# ============================================================
# Some tooling (and your example) uses a simplified array of entries:
#   [{ metric: { ...labels }, value: [ts, "val"], group: 1 }, ...]
# We expose this as an optional `shape=flat` response from our endpoints.


class VMFlatVectorEntry(BaseModel):
    metric: Dict[str, str] = Field(description="Label set")
    value: Tuple[float, str] = Field(description="[unix_ts, value_as_string]")
    group: Optional[int] = Field(default=None, description="1-based series index (UI convenience)")


class VMFlatMatrixEntry(BaseModel):
    metric: Dict[str, str] = Field(description="Label set")
    values: List[Tuple[float, str]] = Field(description="Timeseries samples")
    group: Optional[int] = Field(default=None, description="1-based series index (UI convenience)")
