from __future__ import annotations

from unicron_shared import HeraldStatus


REGISTER_FAILURE_PREFIX = "register: "
REBOOTSTRAP_REQUIRED_CODE = "REBOOTSTRAP_REQUIRED"
REBOOTSTRAP_REQUIRED_MESSAGE = "Certificate bootstrap required for fresh enrollment"


def build_register_failure_message(reason: str) -> str:
    text = str(reason or "").strip() or "unspecified"
    return f"{REGISTER_FAILURE_PREFIX}{text}"


def is_register_failure_state(*, health_status: object, health_message: object) -> bool:
    return (
        str(health_status or "") == HeraldStatus.failed
        and str(health_message or "").startswith(REGISTER_FAILURE_PREFIX)
    )


def build_rebootstrap_required_detail() -> dict[str, str]:
    return {
        "code": REBOOTSTRAP_REQUIRED_CODE,
        "message": REBOOTSTRAP_REQUIRED_MESSAGE,
    }


__all__ = [
    "REBOOTSTRAP_REQUIRED_CODE",
    "REBOOTSTRAP_REQUIRED_MESSAGE",
    "REGISTER_FAILURE_PREFIX",
    "build_register_failure_message",
    "build_rebootstrap_required_detail",
    "is_register_failure_state",
]
