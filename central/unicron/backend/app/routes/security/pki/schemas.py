from datetime import datetime

from pydantic import BaseModel


class RootCAResponse(BaseModel):
    root_ca_pem: str


class CSRRequest(BaseModel):
    csr_pem: str
    not_after_seconds: int | None = None


class CertResponse(BaseModel):
    cert_pem: str
    chain_pem: str
    not_after: datetime
