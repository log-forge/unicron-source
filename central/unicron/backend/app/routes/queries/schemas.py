from typing import Dict, List, Optional

from pydantic import BaseModel, RootModel


class HeraldQuerySchema(BaseModel):
    herald_id: str
    herald_name: str
    central_url: str
    registered_at: Optional[str] = None
    health_status: str
    last_ping: Optional[str] = None
    health_message: Optional[str] = None
    check_in_interval: Optional[int] = None
    region: Optional[str] = None
    tags: List[str] = []
    socket_online: bool
    socket_last_seen: Optional[str] = None
    herald_version: Optional[str] = None
    hostname: Optional[str] = None
    herald_os: Optional[str] = None
    os_version: Optional[str] = None
    architecture: Optional[str] = None
    cpu_count: Optional[int] = None
    host_total_memory_bytes: Optional[int] = None


class HeraldsListSchema(RootModel[List[HeraldQuerySchema]]):
    """Root model wrapping a list of HeraldQuerySchema items."""


class HeraldsSummarySchema(BaseModel):
    total: int
    statuses: Dict[str, int]
    last_ping_latest: Optional[str]
    socket_online_total: int
    groups: Dict[str, int]
    regions: Dict[str, int]
    # """Summary of Heralds: total, statuses, last ping."""
