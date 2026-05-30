from typing import Optional

from pydantic import BaseModel, field_validator


def _q(s: str) -> str:
    """Escape quotes in Victoria predicates / label matchers."""
    return s.replace('"', r"\"")


class ContainerSelector(BaseModel):
    """
    Canonical telemetry selector for browser/API calls.

    The greenfield contract is `container_key` only.
    """

    container_key: Optional[str] = None

    @field_validator("container_key", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    def ensure_container_key(self) -> None:
        if not self.container_key:
            raise ValueError("container_key is required")

    def logs_predicate(self) -> str:
        self.ensure_container_key()
        return f'container_key: "{_q(self.container_key or "")}"'

    def metrics_matcher(self) -> str:
        self.ensure_container_key()
        return f'{{container_key="{_q(self.container_key or "")}"}}'


class PingResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
