import socketio
from datetime import datetime, timedelta, timezone
from typing import Annotated

from app.core.config import settings
from app.core.database import get_session
from app.core.deps import get_socketio_server, require_spiffe_id
from app.core.logging import get_logger
from app.models.herald.crud.herald_crud import create_herald, get_herald
from app.models.herald.crud.herald_token_crud import (
    clear_herald_token_failure,
    get_herald_token,
    get_latest_bootstrapped_go_streamer_token_by_name,
    get_latest_pending_go_streamer_token_by_name,
    update_herald_token_status,
)
from app.routes.herald.schemas import HeraldRegisterRequest, HeraldRegisterResponse
from app.socket.emitters.central.health import emit_herald_health_update
from app.socket.emitters.central.herald_register_emitters import (
    emit_herald_registered,
)
from app.utils.herald_register_state import (
    build_rebootstrap_required_detail,
    is_register_failure_state,
)
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from unicron_shared import HeraldStatus

router = APIRouter()
logger = get_logger(__name__)


def _coerce_utc(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_fresh_reactivation_token(herald_token: object | None, existing: object, herald_id: str) -> bool:
    if herald_token is None:
        return False
    if getattr(herald_token, "status", None) != "consumed":
        return False
    token_name = str(getattr(herald_token, "herald_name", "") or "").strip()
    if token_name != herald_id:
        return False
    tags = {str(tag).lower() for tag in (getattr(herald_token, "tags", None) or [])}
    if "go-streamer" not in tags:
        return False

    unregistered_at = _coerce_utc(getattr(existing, "unregistered_at", None))
    if unregistered_at is None:
        return True
    created_at = _coerce_utc(getattr(herald_token, "created_at", None))
    return bool(created_at and created_at >= unregistered_at)


def _is_pending_go_streamer_token_for_name(herald_token: object | None, herald_id: str) -> bool:
    if herald_token is None:
        return False
    if getattr(herald_token, "status", None) != "pending":
        return False
    token_name = str(getattr(herald_token, "herald_name", "") or "").strip()
    if token_name != herald_id:
        return False
    tags = {str(tag).lower() for tag in (getattr(herald_token, "tags", None) or [])}
    return "go-streamer" in tags


def _is_fresh_pending_rebootstrap_token(
    herald_token: object | None,
    herald_id: str,
    *,
    newer_than: datetime | None = None,
) -> bool:
    if not _is_pending_go_streamer_token_for_name(herald_token, herald_id):
        return False

    created_at = _coerce_utc(getattr(herald_token, "created_at", None))
    if created_at is None:
        return False
    expiry_time = datetime.now(timezone.utc) - timedelta(seconds=settings.TOKEN_EXPIRY_SECONDS)
    if created_at < expiry_time:
        return False
    if newer_than is not None and created_at < newer_than:
        return False
    return True


async def _latest_fresh_pending_rebootstrap_token(
    session: AsyncSession,
    herald_id: str,
    *,
    newer_than: datetime | None = None,
):
    herald_token = await get_latest_pending_go_streamer_token_by_name(session, herald_id)
    if _is_fresh_pending_rebootstrap_token(herald_token, herald_id, newer_than=newer_than):
        return herald_token
    return None


def _raise_rebootstrap_required(status_code: int) -> None:
    raise HTTPException(status_code=status_code, detail=build_rebootstrap_required_detail())


async def _reactivate_unregistered_herald(
    session: AsyncSession,
    existing,
    herald_token,
    *,
    requested_cpu_count: int,
) -> None:
    existing.unregistered = False
    existing.unregistered_at = None
    existing.unregistered_reason = None
    existing.unregistered_by = None
    existing.herald_name = herald_token.herald_name
    existing.central_url = herald_token.central_url
    existing.check_in_interval = getattr(herald_token, "check_in_interval", 60)
    existing.tags = getattr(herald_token, "tags", [])
    existing.cpu_count = requested_cpu_count
    if is_register_failure_state(
        health_status=getattr(existing, "health_status", None),
        health_message=getattr(existing, "health_message", None),
    ):
        existing.health_status = HeraldStatus.unknown
        existing.health_message = ""

    await session.commit()
    await session.refresh(existing)


@router.post("/register", response_model=HeraldRegisterResponse)
async def register_herald(
    body: Annotated[HeraldRegisterRequest | None, Body()] = None,
    session: AsyncSession = Depends(get_session),
    sio: socketio.AsyncServer = Depends(get_socketio_server),
    herald_id: str = Depends(require_spiffe_id),
):
    requested_cpu_count = body.cpu_count if body else None
    existing = await get_herald(session, str(herald_id))
    if existing and not existing.unregistered:
        existing_cpu_count = getattr(existing, "cpu_count", None)
        effective_cpu_count = requested_cpu_count or existing_cpu_count or 1
        should_emit_health = False
        should_commit = False
        if is_register_failure_state(
            health_status=getattr(existing, "health_status", None),
            health_message=getattr(existing, "health_message", None),
        ):
            existing.health_status = HeraldStatus.unknown
            existing.health_message = ""
            should_commit = True
            should_emit_health = True
        if requested_cpu_count is not None and existing_cpu_count != requested_cpu_count:
            existing.cpu_count = requested_cpu_count
            should_commit = True
        if should_commit:
            await session.commit()
            await session.refresh(existing)
        logger.info(
            "Herald registration treated as idempotent: id=%s, name=%s, central_url=%s",
            herald_id,
            existing.herald_name,
            existing.central_url,
        )
        if should_emit_health:
            await emit_herald_health_update(existing, sio=sio)
        return HeraldRegisterResponse(success=True, status="registered", herald_id=herald_id)

    herald_token = await get_herald_token(session, str(herald_id))
    # go-streamer enrollment tokens are keyed by random token id while SPIFFE identity
    # uses herald_name, so fallback to a bootstrap-complete name-based lookup when
    # direct id lookup misses on first registration.
    if not herald_token:
        herald_token = await get_latest_bootstrapped_go_streamer_token_by_name(session, str(herald_id))

    if existing and existing.unregistered:
        if not _is_fresh_reactivation_token(herald_token, existing, str(herald_id)):
            unregistered_at = _coerce_utc(getattr(existing, "unregistered_at", None))
            if await _latest_fresh_pending_rebootstrap_token(
                session,
                str(herald_id),
                newer_than=unregistered_at,
            ):
                _raise_rebootstrap_required(403)
            raise HTTPException(status_code=403, detail="Herald was deregistered; redeploy with a new ID")

        effective_cpu_count = requested_cpu_count or getattr(existing, "cpu_count", None) or 1
        should_clear_token_failure = bool(
            getattr(herald_token, "failure_details", None) is not None
            or getattr(herald_token, "reason", None)
        )
        await _reactivate_unregistered_herald(
            session,
            existing,
            herald_token,
            requested_cpu_count=effective_cpu_count,
        )
        await update_herald_token_status(session, str(herald_token.id), "active")
        if should_clear_token_failure:
            await clear_herald_token_failure(session, str(herald_token.id))

        logger.info(
            "Herald reactivated after fresh enrollment: id=%s, name=%s, central_url=%s",
            herald_id,
            herald_token.herald_name,
            herald_token.central_url,
        )
        await emit_herald_registered(sio, herald_id, herald_token)
        return HeraldRegisterResponse(success=True, status="registered", herald_id=herald_id)

    if not herald_token:
        if await _latest_fresh_pending_rebootstrap_token(session, str(herald_id)):
            _raise_rebootstrap_required(401)
        raise HTTPException(status_code=401, detail="Unknown or expired herald_token")

    if _is_pending_go_streamer_token_for_name(herald_token, str(herald_id)):
        if _is_fresh_pending_rebootstrap_token(herald_token, str(herald_id)):
            _raise_rebootstrap_required(401)
        raise HTTPException(status_code=401, detail="Unknown or expired herald_token")

    if herald_token.status in {"pending", "consumed", "active"}:
        effective_cpu_count = requested_cpu_count or 1
        should_clear_token_failure = bool(
            getattr(herald_token, "failure_details", None) is not None
            or getattr(herald_token, "reason", None)
        )
        await create_herald(
            session,
            herald_name=herald_token.herald_name,
            central_url=herald_token.central_url,
            herald_id=str(herald_id),
            check_in_interval=getattr(herald_token, "check_in_interval", 60),
            tags=getattr(herald_token, "tags", []),
            cpu_count=effective_cpu_count,
        )

        if herald_token.status != "active":
            await update_herald_token_status(session, str(herald_token.id), "active")
        if should_clear_token_failure:
            await clear_herald_token_failure(session, str(herald_token.id))
    else:
        if await _latest_fresh_pending_rebootstrap_token(session, str(herald_id)):
            _raise_rebootstrap_required(401)
        raise HTTPException(status_code=401, detail="Unknown or expired herald_token")

    logger.info(
        "Herald registered: id=%s, name=%s, central_url=%s",
        herald_id,
        herald_token.herald_name,
        herald_token.central_url,
    )

    await emit_herald_registered(sio, herald_id, herald_token)

    return HeraldRegisterResponse(success=True, status="registered", herald_id=herald_id)
