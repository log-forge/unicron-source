from typing import Optional

from pydantic import BaseModel, Field


class HeraldRegisterResponse(BaseModel):
    success: bool
    status: str
    herald_id: str


class HeraldRegisterRequest(BaseModel):
    cpu_count: Optional[int] = Field(default=None, ge=1)


class HeraldMtlsResponse(BaseModel):
    success: bool
    herald_id: str
    common_name: str


class HeraldRegisterFailureDetail(BaseModel):
    code: str
    message: Optional[str] = None


class HeraldRegisterFailRequest(BaseModel):
    herald_id: str
    herald_name: Optional[str] = None
    reason: Optional[str] = None
    failure: Optional[HeraldRegisterFailureDetail] = None


class HeraldRegisterFailResponse(BaseModel):
    success: bool
    status: str
    herald_id: str
    reason: Optional[str] = None
