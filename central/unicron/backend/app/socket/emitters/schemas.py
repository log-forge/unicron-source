from datetime import datetime
from typing import List, Optional, Union

from pydantic import BaseModel, Field

from unicron_shared import HeraldStatus


class HeraldRegisterEventSuccessData(BaseModel):
    herald_id: str
    herald_name: str
    group: Optional[str] = None
    tags: List[str] = []
    status: str = HeraldStatus.healthy


class HeraldRegisterFailureDetailData(BaseModel):
    code: str
    message: Optional[str] = None


class HeraldRegisterEventFailData(BaseModel):
    herald_id: str
    herald_name: str
    status: str = HeraldStatus.failed
    reason: Optional[str] = "unspecified"
    failure: Optional[HeraldRegisterFailureDetailData] = None


class HeraldHealthEventPayload(BaseModel):
    herald_id: str
    herald_name: Optional[str] = None
    status: HeraldStatus = HeraldStatus.unknown
    message: Optional[str] = None
    last_ping: Optional[datetime] = None
    registered_at: Optional[datetime] = None
    check_in_interval: Optional[int] = None
    socket_online: bool = False
    socket_last_seen: Optional[datetime] = None
    region: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    central_url: Optional[str] = None
    herald_version: Optional[str] = None
    hostname: Optional[str] = None
    herald_os: Optional[str] = None
    os_version: Optional[str] = None
    architecture: Optional[str] = None
    cpu_count: Optional[int] = None
    host_total_memory_bytes: Optional[int] = None
