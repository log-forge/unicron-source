"""WebSocket endpoint handler for go-streamer agents.

Accepts persistent WebSocket connections from go-streamer agents,
processes inventory/event/heartbeat messages, persists container data
to PostgreSQL, and caches in Redis for fast UI lookups.

Protocol: JSON envelopes matching go-streamer's upstreamEnvelope format:
    {"type": str, "host_id": str, "data": object}

Message types:
    - "inventory": Full container list refresh
    - "container_event": Single container state change (start/stop/die)
    - "heartbeat": Keep-alive signal
    - "stats": Per-container metrics relay to subscribed browsers via StatsRelay
    - "metrics": Per-container stats frames from StreamManager (on-demand streaming)
    - "fast_logs_frame": Normalized live log row for active fast-lane viewers
    - "fast_logs_error": Live-log control or history-seed failure for a container viewer group
    - "run_script_response": Script execution result from agent's run_script handler
    - "container_command_response": Container action result from agent (restart/stop/start/kill)
    - "monitoring_toggle_ack": Agent acknowledges a monitoring toggle command
    - "log_collection_state_changed": Container log-collection availability transition
    - "telemetry_health": Telemetry pipeline health transition from go-streamer
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.config import settings
from app.core.database import session_ctx
from app.core.deps.spiffe import get_spiffe_agent_cert_metadata_ws, get_spiffe_agent_identity_ws
from app.core.logging import get_logger
from app.models.herald.crud.herald_crud import get_herald, set_socket_presence
from app.models.container.container_model import Container
from app.models.container.crud.container_crud import upsert_container
from app.services.agent_registry import get_agent_registry
from app.services.browser_session_registry import get_browser_session_registry
from app.services.container_cache import get_container_cache
from app.services.container_identity import build_container_key
from app.services.container_runtime import get_container_runtime_service
from app.services.inventory_sync import get_inventory_sync_service
from app.services.monitoring_policy import get_monitoring_policy_service
from app.services.realtime_event_bus import get_realtime_event_bus
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

logger = get_logger("routes.agent.ws_handler")

router = APIRouter()


def _build_cached_container_payload(container: Any, host_id: str) -> dict[str, Any]:
    """Build a JSON-safe inventory payload for cache, browser fanout, and streams."""
    started_at = getattr(container, "started_at", None)
    if hasattr(started_at, "isoformat"):
        started_at = started_at.isoformat()
    elif started_at is not None and not isinstance(started_at, str):
        started_at = str(started_at)

    return {
        "container_key": container.container_key,
        "docker_container_id": container.docker_container_id,
        "name": container.name,
        "status": container.status,
        "image": container.image,
        "host_id": host_id,
        "labels": container.labels or {},
        "ports": container.ports or {},
        "started_at": started_at,
        "monitoring_enabled": bool(container.monitoring_enabled),
    }


def _container_name_from_key(container_key: str) -> str:
    return str(container_key or "").split(":", 1)[1] if ":" in str(container_key or "") else str(container_key or "")


async def _apply_inventory_reconciliation_side_effects(
    *,
    host_id: str,
    result: Any,
    cache: Any,
    realtime: Any,
) -> None:
    removed_keys = list(dict.fromkeys(getattr(result, "removed_container_keys", []) or []))
    disabled_keys = list(dict.fromkeys(getattr(result, "monitoring_disabled_container_keys", []) or []))

    for container_key in removed_keys:
        await cache.remove_container(host_id, container_key)

    for container_key in list(dict.fromkeys([*removed_keys, *disabled_keys])):
        await cache.clear_monitoring_state(container_key)
        await cache.clear_log_collection_state(host_id, container_key)

    for container_key in disabled_keys:
        name = _container_name_from_key(container_key)
        event_payload = {
            "type": "monitoring_state_changed",
            "herald_id": host_id,
            "host_id": host_id,
            "container_key": container_key,
            "name": name,
            "container_id": "",
            "image": "",
            "status": "removed" if container_key in removed_keys else "",
            "enabled": False,
        }
        try:
            from app.services.alerting.streams import publish_container_event

            await publish_container_event(event_payload)
        except Exception:
            logger.warning(
                "Failed to publish monitoring disable from inventory reconciliation",
                exc_info=True,
                extra={"host_id": host_id, "container_key": container_key},
            )
        await realtime.emit_monitoring_state_changed(
            container_key=container_key,
            host_id=host_id,
            monitoring_enabled=False,
        )

    for container_key in removed_keys:
        await realtime.emit_container_event(
            {
                "host_id": host_id,
                "container_key": container_key,
                "name": _container_name_from_key(container_key),
                "docker_container_id": None,
                "action": "destroy",
                "status": "removed",
            }
        )


async def _is_agent_unregistered(host_id: str) -> bool:
    """Check durable herald state for explicit deregistration."""
    try:
        async with session_ctx() as session:
            herald = await get_herald(session, host_id)
            return bool(herald and getattr(herald, "unregistered", False))
    except Exception:
        logger.warning("Failed to query herald deregistration state", exc_info=True, extra={"host_id": host_id})
        return False


async def _publish_container_event_safe(event_data: dict) -> None:
    """Publish container lifecycle event to Redis Stream with silent failure.

    Fire-and-forget: errors are logged but don't crash the WebSocket.
    Browser relay and DB writes are the critical path; Redis publishing
    to alert-engine is best-effort (matches log pipeline pattern).
    """
    try:
        from app.services.alerting.streams import publish_container_lifecycle_event
        await publish_container_lifecycle_event(event_data)
    except Exception as e:
        logger.warning(
            "Failed to publish container event to Redis Stream: %s",
            str(e),
            extra={"host_id": event_data.get("host_id")},
        )


async def _send_monitoring_sync_safe(host_id: str, websocket: WebSocket) -> None:
    """Push persisted monitoring state to an agent after it reconnects."""
    try:
        async with session_ctx() as session:
            stmt = select(Container).where(getattr(Container, "herald_id") == host_id)
            rows = [
                row
                for row in (await session.execute(stmt)).scalars().all()
                if getattr(row, "status", None) != "removed"
            ]

        states: dict[str, bool] = {row.container_key: bool(row.monitoring_enabled) for row in rows}
        cache = get_container_cache()
        await cache.prime_monitoring_states_for_host(host_id, states)
        containers: list[dict[str, Any]] = []

        for row in rows:
            containers.append(
                {
                    "container_key": row.container_key,
                    "name": row.name,
                    "enabled": bool(row.monitoring_enabled),
                }
            )

        await websocket.send_json(
            {
                "type": "monitoring_sync",
                "data": {"containers": containers},
            }
        )
        logger.info(
            "Monitoring sync sent to agent",
            extra={"host_id": host_id, "container_count": len(containers)},
        )
    except Exception as e:
        logger.warning(
            "Failed to send monitoring sync: %s",
            str(e),
            extra={"host_id": host_id},
        )


async def _send_fast_tail_replay_safe(host_id: str, websocket: WebSocket) -> None:
    """Replay active fast-lane subscriptions to an agent after reconnect."""
    try:
        session_registry = get_browser_session_registry()
        subscriptions = await session_registry.get_active_fast_log_containers(host_id)
        for subscription in subscriptions:
            await websocket.send_json(
                {
                    "type": "fast_tail_start",
                    "data": {
                        "container_key": subscription.container_key,
                        "source": subscription.source,
                        "history_tail": subscription.history_tail,
                        "history_since": subscription.history_since,
                    },
                }
            )
        if subscriptions:
            logger.info(
                "Fast-tail subscriptions replayed to agent",
                extra={"host_id": host_id, "container_count": len(subscriptions)},
            )
    except Exception as e:
        logger.warning(
            "Failed to replay fast-tail subscriptions: %s",
            str(e),
            extra={"host_id": host_id},
        )


async def _request_inventory_refresh_safe(host_id: str) -> None:
    """Ask a freshly connected agent to send a full inventory snapshot."""
    try:
        registry = get_agent_registry()
        sent = await registry.send_command(host_id, "request_inventory")
        if sent:
            logger.info(
                "Requested inventory refresh from agent",
                extra={"host_id": host_id},
            )
        else:
            logger.warning(
                "Unable to request inventory refresh from agent",
                extra={"host_id": host_id},
            )
    except Exception as e:
        logger.warning(
            "Failed to request inventory refresh from agent: %s",
            str(e),
            extra={"host_id": host_id},
        )


async def _send_agent_reconnect_replay_safe(host_id: str, websocket: WebSocket) -> None:
    """Replay Central state and request inventory after agent registration."""
    await _send_monitoring_sync_safe(host_id, websocket)
    await _send_fast_tail_replay_safe(host_id, websocket)
    await _request_inventory_refresh_safe(host_id)


async def _mark_socket_presence_safe(host_id: str, online: bool) -> None:
    """Best-effort DB socket presence update."""
    try:
        async with session_ctx() as session:
            await set_socket_presence(session, host_id, online)
    except Exception:
        logger.debug(
            "Failed to update socket presence",
            exc_info=True,
            extra={"host_id": host_id, "online": online},
        )


async def _ensure_herald_row(host_id: str) -> None:
    """Verify the Herald DB row exists for a connecting agent.

    The canonical registration path is POST /api/herald/register which
    validates the enrollment token before creating the row.  This check
    only logs a warning when the row is missing so operators can diagnose
    agents that skipped or failed the register call.
    """
    try:
        async with session_ctx() as session:
            existing = await get_herald(session, host_id)
            if existing is not None:
                return
        logger.warning(
            "Herald row missing for connected agent; inventory will be "
            "skipped until the agent completes POST /api/herald/register. "
            "Upgrade the agent image or re-enroll.",
            extra={"host_id": host_id},
        )
    except Exception:
        logger.debug(
            "Herald row check failed",
            exc_info=True,
            extra={"host_id": host_id},
        )


def _authenticate_mtls(websocket: WebSocket) -> Optional[str]:
    """Attempt mTLS authentication and extract agent identity.

    Returns:
        The agent_id (host_id) if mTLS authentication succeeds, None otherwise.
    """
    identity = get_spiffe_agent_identity_ws(websocket)
    if not identity:
        return None

    agent_id, workload_type = identity
    logger.debug(
        "mTLS identity extracted",
        extra={"agent_id": agent_id, "workload_type": workload_type}
    )
    return agent_id


def _authenticate(websocket: WebSocket) -> tuple[bool, Optional[str]]:
    """Validate agent WebSocket connection authentication.

    Auth method:
    1. mTLS client certificate with SPIFFE identity (returns agent_id from cert)

    Returns:
        Tuple of (authenticated: bool, mtls_host_id: Optional[str])
        - If mTLS succeeds: (True, agent_id)
        - If mTLS is missing or invalid: (False, None)
    """
    mtls_host_id = _authenticate_mtls(websocket)
    if mtls_host_id:
        return True, mtls_host_id

    client_host = websocket.client.host if websocket.client else None
    logger.warning(
        "Agent WS connection rejected: mTLS client certificate required",
        extra={"client": client_host},
    )
    return False, None


def _is_missing_herald_fk_error(exc: Exception) -> bool:
    raw = str(exc).lower()
    return (
        "container_herald_id_fkey" in raw
        or ("foreignkeyviolationerror" in raw and "herald" in raw)
    )


async def _process_inventory(
    host_id: str, containers_data: List[Dict[str, Any]]
) -> None:
    """Process a full inventory payload: PostgreSQL first, then Redis cache.

    Args:
        host_id: The agent host identifier
        containers_data: List of container dicts from the agent
    """
    cache = get_container_cache()
    sync_service = get_inventory_sync_service()
    realtime = get_realtime_event_bus()

    async with session_ctx() as session:
        upserts = []
        for container_data in containers_data:
            name = str(container_data.get("name") or "").strip()
            if not name:
                continue
            static = container_data.get("static") or {}
            if not isinstance(static, dict):
                static = {}

            # Backfill static metadata from top-level agent payload keys.
            # go-streamer inventory emits these top-level fields today.
            labels = container_data.get("labels")
            ports = container_data.get("ports")
            networks = container_data.get("networks")
            mounts = container_data.get("mounts")
            environment = container_data.get("environment")

            static.setdefault("image", container_data.get("image"))
            static.setdefault("image_id", container_data.get("image_id"))
            static.setdefault("labels", labels if isinstance(labels, dict) else {})
            static.setdefault("ports", ports if isinstance(ports, dict) else {})
            static.setdefault("networks", networks if isinstance(networks, dict) else {})
            static.setdefault("mounts", mounts if isinstance(mounts, list) else [])
            static.setdefault("environment", environment if isinstance(environment, list) else [])

            upserts.append(
                {
                    "name": name,
                    "docker_container_id": str(container_data.get("container_id") or "").strip() or None,
                    "status": container_data.get("status"),
                    "started_at": container_data.get("started_at"),
                    "monitoring_enabled": bool(container_data.get("monitoring_enabled", False)),
                    "group": container_data.get("group"),
                    "static": static,
                }
            )
        from unicron_shared import ContainerState

        payload = [ContainerState.model_validate(item) for item in upserts]
        try:
            result = await sync_service.sync_inventory(session, herald_id=host_id, containers=payload)
            await session.commit()
        except IntegrityError as exc:
            if not _is_missing_herald_fk_error(exc):
                raise
            await session.rollback()
            logger.warning(
                "Container inventory skipped due to missing herald row",
                extra={"host_id": host_id, "container_count": len(upserts)},
            )
            return

    cached_containers = [
        _build_cached_container_payload(container, host_id)
        for container in result.containers
    ]

    await _apply_inventory_reconciliation_side_effects(
        host_id=host_id,
        result=result,
        cache=cache,
        realtime=realtime,
    )
    await cache.cache_inventory(host_id, cached_containers)
    await cache.set_host_online(host_id, True)

    # Publish to container stream for alert-engine registry sync
    try:
        from app.services.alerting.streams import publish_container_event

        await publish_container_event({
            "type": "inventory_update",
            "herald_id": host_id,
            "host_id": host_id,
            "containers": cached_containers,
        })
    except Exception:
        logger.warning(
            "Failed to publish inventory_update to container stream",
            exc_info=True,
            extra={"host_id": host_id},
        )

    # Broadcast to browser clients
    await realtime.emit_inventory_update({"host_id": host_id, "containers": cached_containers})
    await realtime.emit_host_status(host_id=host_id, online=True)

    logger.info(
        "Inventory processed",
        extra={"host_id": host_id, "container_count": len(containers_data)},
    )


async def _process_container_event(
    host_id: str, event_data: Dict[str, Any]
) -> None:
    """Process a single container state change event.

    Args:
        host_id: The agent host identifier
        event_data: Container event dict with container_id, action, etc.
    """
    action = event_data.get("action", "")  # start, stop, die
    name = event_data.get("name", "unknown")
    if not name:
        logger.warning("Container event missing name", extra={"host_id": host_id})
        return

    # Prefer the agent-reported Docker state. Fall back to action->state mapping
    # only when the event payload omitted a status.
    status_map = {
        "start": "running",
        "stop": "exited",
        "die": "exited",
        "kill": "exited",
        "restart": "restarting",
        "create": "created",
        "destroy": "removed",
        "pause": "paused",
        "unpause": "running",
    }
    container_status = event_data.get("status") or status_map.get(action, "unknown")
    runtime_service = get_container_runtime_service()
    browser_payload = await runtime_service.apply_lifecycle_event(
        host_id,
        {**event_data, "status": container_status},
    )

    # Emit event for alert engine via Socket.IO internal namespace
    try:
        from app.socket.emitters.internal.alert_events import emit_container_event

        await emit_container_event(
            container_key=browser_payload["container_key"],
            action=action,
            herald_id=host_id,  # Use host_id as herald_id equivalent
            organization_id="",  # Organization context TBD in later plan
            metadata={"name": name, "source": "go-streamer"},
        )
    except Exception:
        logger.debug(
            "Could not emit container event (non-critical)",
            exc_info=True,
            extra={"container_key": browser_payload["container_key"], "action": action},
        )

    # Publish lifecycle updates to the container stream so alert-engine can keep
    # its monitored registry in sync on start/stop without waiting for a toggle.
    if action in {"start", "restart", "stop", "die", "kill"}:
        try:
            from app.services.alerting.streams import publish_container_event

            stream_event_type = "container_start" if action in {"start", "restart"} else "container_stop"
            await publish_container_event({
                "type": stream_event_type,
                "herald_id": host_id,
                "host_id": host_id,
                "container_key": browser_payload["container_key"],
                "name": name,
                "image": event_data.get("image", ""),
                "status": container_status,
                "timestamp": event_data.get("timestamp", ""),
            })
        except Exception:
            logger.warning(
                "Failed to publish %s to container stream",
                "container_start" if action in {"start", "restart"} else "container_stop",
                exc_info=True,
                extra={"host_id": host_id, "container_key": browser_payload["container_key"], "action": action},
            )

    # Publish to unicron:events Redis Stream for alert-engine stability rules.
    # Canonical identity is container_key={host_id}:{container_name}; Docker IDs
    # are runtime-only correlation and are not used as rule scope identity.
    lifecycle_event = {
        "host_id": host_id,
        "container_name": browser_payload["name"],
        "container_key": browser_payload["container_key"],
        "event_type": action,
        "timestamp": event_data.get("timestamp", ""),
        "exit_code": event_data.get("exit_code"),
        "image": event_data.get("image", ""),
    }
    asyncio.create_task(_publish_container_event_safe(lifecycle_event))

    logger.debug(
        "Container event processed",
        extra={"host_id": host_id, "container_key": browser_payload["container_key"], "action": action},
    )


async def _process_log_collection_state(host_id: str, state_data: Dict[str, Any]) -> None:
    """Persist and broadcast the current log-collection state for one monitored container."""
    name = str(state_data.get("name") or state_data.get("container_name") or "").strip()
    image = str(state_data.get("image") or "").strip()
    if not name or not image:
        logger.warning(
            "Log-collection state missing container identity",
            extra={"host_id": host_id, "container_name": name, "image": image},
        )
        return

    status = str(
        state_data.get("log_collection_status")
        or state_data.get("status")
        or ""
    ).strip().lower()
    if status not in {"ok", "unavailable"}:
        logger.debug(
            "Ignoring log-collection state with unknown status",
            extra={"host_id": host_id, "container_name": name, "image": image, "status": status},
        )
        return

    issue = str(
        state_data.get("log_collection_issue")
        or state_data.get("issue")
        or ""
    ).strip().lower() or None
    if status != "unavailable":
        issue = None

    container_name = str(state_data.get("container_name") or "").strip().lstrip("/") or None
    docker_container_id = str(
        state_data.get("docker_container_id")
        or state_data.get("container_id")
        or ""
    ).strip() or None
    container_key = str(state_data.get("container_key") or "").strip() or build_container_key(host_id, name)

    cache = get_container_cache()
    await cache.set_log_collection_state(
        host_id,
        container_key,
        name,
        image,
        status=status,
        issue=issue,
        docker_container_id=docker_container_id,
        container_name=container_name,
    )

    await get_realtime_event_bus().emit_log_collection_state_changed(
        {
            "host_id": host_id,
            "container_key": container_key,
            "name": name,
            "image": image,
            "log_collection_status": status,
            "log_collection_issue": issue,
            "container_name": container_name,
            "docker_container_id": docker_container_id,
        }
    )


async def _process_fast_logs_frame(host_id: str, frame_data: Dict[str, Any]) -> None:
    container_key = str(frame_data.get("container_key") or "").strip()
    row = frame_data.get("row")
    if not isinstance(row, dict):
        logger.debug("Ignoring fast_logs_frame without row payload", extra={"host_id": host_id})
        return

    row_container_key = str(row.get("container_key") or "").strip()
    if not container_key:
        container_key = row_container_key
    if not container_key:
        logger.debug("Ignoring fast_logs_frame without container_key", extra={"host_id": host_id})
        return
    if row_container_key and row_container_key != container_key:
        logger.warning(
            "Ignoring fast_logs_frame with mismatched container_key",
            extra={"host_id": host_id, "container_key": container_key, "row_container_key": row_container_key},
        )
        return

    payload = {
        "container_key": container_key,
        "row": row,
        "message": row.get("msg", ""),
        "timestamp": row.get("time", ""),
    }
    await get_browser_session_registry().append_recent_log_row(container_key, payload)
    await get_realtime_event_bus().emit_live_logs(container_key, payload)


async def _process_fast_logs_error(host_id: str, error_data: Dict[str, Any]) -> None:
    container_key = str(error_data.get("container_key") or "").strip()
    error_msg = str(error_data.get("error") or "").strip()
    if not container_key or not error_msg:
        logger.debug("Ignoring fast_logs_error without container_key/error", extra={"host_id": host_id})
        return
    await get_realtime_event_bus().emit_live_logs(
        container_key,
        {
            "type": "error",
            "container_key": container_key,
            "error": error_msg,
        },
    )


@router.websocket("/ws")
async def agent_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for go-streamer agent connections.

    Protocol:
        1. Agent connects to /api/agent/ws with auth token or mTLS certificate
        2. Agent sends inventory message with full container list
        3. Agent sends periodic heartbeats and event updates
        4. On disconnect, timeout-based offline detection (60s grace)

    Message envelope format:
        {"type": "inventory|container_event|heartbeat|stats", "host_id": str, "data": object}
    """
    # Authenticate before accepting
    authenticated, mtls_host_id = _authenticate(websocket)
    if not authenticated:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        logger.warning(
            "Agent WebSocket auth failed",
            extra={"client": websocket.client.host if websocket.client else "unknown"},
        )
        return

    await websocket.accept()

    registry = get_agent_registry()
    realtime = get_realtime_event_bus()
    host_id: Optional[str] = None
    connection_id: Optional[str] = None
    cert_fingerprint_sha256: Optional[str] = None
    cert_serial_hex: Optional[str] = None
    next_revocation_check = 0.0

    # If mTLS authentication provided host_id, use it immediately
    if mtls_host_id:
        host_id = mtls_host_id
        cert_meta = get_spiffe_agent_cert_metadata_ws(websocket)
        if cert_meta is not None:
            cert_fingerprint_sha256, cert_serial_hex = cert_meta
            if await registry.is_cert_revoked(
                cert_fingerprint_sha256=cert_fingerprint_sha256,
                cert_serial_hex=cert_serial_hex,
            ):
                await websocket.close(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason="Agent certificate revoked",
                )
                logger.info(
                    "Rejected connection for revoked agent certificate",
                    extra={"host_id": host_id},
                )
                return
        if await _is_agent_unregistered(host_id):
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Agent deregistered",
            )
            logger.info("Rejected connection for deregistered agent", extra={"host_id": host_id})
            return
        if await registry.is_revoked(host_id):
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Agent revoked",
            )
            logger.info("Rejected connection for revoked agent", extra={"host_id": host_id})
            return
        await _ensure_herald_row(host_id)
        connection_id = await registry.register(
            host_id,
            websocket,
            cert_fingerprint_sha256=cert_fingerprint_sha256,
            cert_serial_hex=cert_serial_hex,
        )
        if not connection_id:
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Agent revoked",
            )
            return
        cache = get_container_cache()
        await cache.set_host_online(host_id, True)
        await _mark_socket_presence_safe(host_id, True)
        await _send_agent_reconnect_replay_safe(host_id, websocket)
        await realtime.emit_host_status(host_id=host_id, online=True)
        logger.info(
            "Agent connected via mTLS",
            extra={"host_id": host_id}
        )

    try:
        while True:
            # Periodically check distributed revocation state without adding
            # per-message Redis/DB overhead.
            if host_id and time.time() >= next_revocation_check:
                next_revocation_check = time.time() + 5.0
                revoked = await registry.is_revoked(host_id)
                unregistered = await _is_agent_unregistered(host_id)
                if revoked or unregistered:
                    await websocket.close(
                        code=status.WS_1008_POLICY_VIOLATION,
                        reason="Agent revoked",
                    )
                    logger.info(
                        "Agent disconnected (revoked/unregistered)",
                        extra={"host_id": host_id, "revoked": revoked, "unregistered": unregistered},
                    )
                    break

            # Receive JSON envelope
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                import json
                message = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                logger.warning("Invalid JSON from agent", extra={"host_id": host_id})
                continue

            msg_type = message.get("type", "")
            msg_host_id = message.get("host_id", "")
            data = message.get("data", {})

            # First message must establish host_id (only for non-mTLS connections)
            if host_id is None:
                if not msg_host_id:
                    await websocket.close(
                        code=status.WS_1008_POLICY_VIOLATION,
                        reason="First message must include host_id",
                    )
                    return
                host_id = msg_host_id
                if await _is_agent_unregistered(host_id):
                    await websocket.close(
                        code=status.WS_1008_POLICY_VIOLATION,
                        reason="Agent deregistered",
                    )
                    logger.info("Rejected connection for deregistered agent", extra={"host_id": host_id})
                    return
                if await registry.is_revoked(host_id):
                    await websocket.close(
                        code=status.WS_1008_POLICY_VIOLATION,
                        reason="Agent revoked",
                    )
                    logger.info("Rejected connection for revoked agent", extra={"host_id": host_id})
                    return
                await _ensure_herald_row(host_id)
                connection_id = await registry.register(
                    host_id,
                    websocket,
                    cert_fingerprint_sha256=cert_fingerprint_sha256,
                    cert_serial_hex=cert_serial_hex,
                )
                if not connection_id:
                    await websocket.close(
                        code=status.WS_1008_POLICY_VIOLATION,
                        reason="Agent revoked",
                    )
                    return
                cache = get_container_cache()
                await cache.set_host_online(host_id, True)
                await _mark_socket_presence_safe(host_id, True)
                await _send_agent_reconnect_replay_safe(host_id, websocket)
                await realtime.emit_host_status(host_id=host_id, online=True)
                logger.info("Agent connected", extra={"host_id": host_id})

            # Handle message types
            if msg_type == "inventory":
                containers = data if isinstance(data, list) else data.get("containers", [])
                await _process_inventory(host_id, containers)

            elif msg_type == "container_event":
                await _process_container_event(host_id, data)

            elif msg_type == "heartbeat":
                await registry.heartbeat(host_id)
                cache = get_container_cache()
                await cache.touch_host_heartbeat(host_id)

            elif msg_type == "stats":
                container_key = str(data.get("container_key") or "").strip()
                if container_key:
                    await realtime.emit_stats(container_key, data)
                else:
                    logger.debug(
                        "Stats message missing container_key",
                        extra={"host_id": host_id},
                    )

            elif msg_type == "exec_started":
                session_id = data.get("session_id", "")
                if session_id:
                    await realtime.emit_terminal(session_id, {
                        "_relay_type": "exec_started",
                        "success": data.get("success", False),
                        "message": data.get("message", ""),
                    })

            elif msg_type == "exec_output":
                session_id = data.get("session_id", "")
                if session_id:
                    await realtime.emit_terminal(session_id, {
                        "_relay_type": "exec_output",
                        "data": data.get("data", ""),
                    })

            elif msg_type == "exec_exit":
                session_id = data.get("session_id", "")
                if session_id:
                    await realtime.emit_terminal(session_id, {
                        "_relay_type": "exec_exit",
                        "code": data.get("code", 0),
                        "message": data.get("message", ""),
                    })

            elif msg_type == "logs_output":
                session_id = data.get("session_id", "")
                if session_id:
                    await realtime.emit_log_session(session_id, {
                        "_relay_type": "logs_output",
                        "data": data.get("data", ""),
                    })

            elif msg_type == "logs_error":
                session_id = data.get("session_id", "")
                if session_id:
                    await realtime.emit_log_session(session_id, {
                        "_relay_type": "logs_error",
                        "error": data.get("error", ""),
                    })

            elif msg_type == "fast_logs_frame":
                await _process_fast_logs_frame(host_id, data)

            elif msg_type == "fast_logs_error":
                await _process_fast_logs_error(host_id, data)

            elif msg_type == "files_list_response":
                request_id = data.get("request_id", "")
                if request_id:
                    await realtime.emit_files_response(request_id, {
                        "request_id": request_id,
                        "action": "list",
                        "path": data.get("path", ""),
                        "entries": data.get("entries", []),
                        "error": data.get("error", ""),
                    })

            elif msg_type == "file_read_response":
                request_id = data.get("request_id", "")
                if request_id:
                    await realtime.emit_files_response(request_id, {
                        "request_id": request_id,
                        "action": "read",
                        "path": data.get("path", ""),
                        "content": data.get("content", ""),
                        "size": data.get("size", 0),
                        "error": data.get("error", ""),
                    })

            elif msg_type == "run_script_response":
                # Relay run_script response back to the alert-engine action system
                request_id = data.get("request_id", "")
                if request_id:
                    try:
                        from app.services.alerting.action_executor import relay_script_result

                        await relay_script_result(
                            request_id=request_id,
                            success=data.get("success", False),
                            output=data.get("output", ""),
                            exit_code=data.get("exit_code", -1),
                            error=data.get("error", ""),
                        )
                    except ImportError:
                        # Action executor may not exist yet - log and continue
                        logger.debug(
                            "run_script_response received but action_executor not available",
                            extra={"request_id": request_id, "host_id": host_id},
                        )
                    except Exception:
                        logger.exception(
                            "Error relaying run_script_response",
                            extra={"request_id": request_id, "host_id": host_id},
                        )
                else:
                    logger.warning(
                        "run_script_response missing request_id",
                        extra={"host_id": host_id},
                    )

            elif msg_type == "container_command_response":
                # Relay container command response to the internal action endpoint
                # Resolves the pending action slot (local Future + Redis result slot)
                request_id = data.get("request_id", "")
                if request_id:
                    try:
                        from app.services.alerting.action_executor import resolve_action_result

                        await resolve_action_result(
                            request_id=request_id,
                            success=data.get("success", False),
                            message=data.get("message", ""),
                            error=data.get("error", ""),
                        )
                    except ImportError:
                        logger.debug(
                            "container_command_response received but action_executor not available",
                            extra={"request_id": request_id, "host_id": host_id},
                        )
                    except Exception:
                        logger.exception(
                            "Error resolving container_command_response",
                            extra={"request_id": request_id, "host_id": host_id},
                        )
                else:
                    logger.warning(
                        "container_command_response missing request_id",
                        extra={"host_id": host_id},
                    )

            elif msg_type == "metrics":
                container_key = str(data.get("container_key") or "").strip()
                if container_key:
                    await realtime.emit_stats(container_key, data)
                else:
                    logger.debug(
                        "Metrics message missing container_key",
                        extra={"host_id": host_id},
                    )

            elif msg_type == "monitoring_toggle_ack":
                request_id = data.get("request_id", "")
                if request_id:
                    await get_monitoring_policy_service().resolve_ack(
                        request_id=request_id,
                        success=data.get("success", False),
                        error=data.get("error", ""),
                    )
                else:
                    logger.warning(
                        "monitoring_toggle_ack missing request_id",
                        extra={"host_id": host_id},
                    )

            elif msg_type == "agent_decommission_ack":
                logger.info(
                    "Agent acknowledged decommission command",
                    extra={
                        "host_id": host_id,
                        "request_id": data.get("request_id", ""),
                        "success": bool(data.get("success", False)),
                    },
                )

            elif msg_type == "log_collection_state_changed":
                await _process_log_collection_state(host_id, data if isinstance(data, dict) else {})

            elif msg_type == "telemetry_health":
                await realtime.emit_telemetry_health(
                    host_id=host_id,
                    healthy=data.get("healthy", True),
                    timestamp=data.get("timestamp", 0),
                )

            else:
                logger.debug(
                    "Unknown message type from agent",
                    extra={"host_id": host_id, "type": msg_type},
                )

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Error in agent WebSocket handler", extra={"host_id": host_id})
    finally:
        # Unregister but don't mark offline immediately (60s grace for reconnection)
        if host_id:
            await registry.unregister(host_id, connection_id=connection_id)
            logger.info("Agent disconnected", extra={"host_id": host_id})
