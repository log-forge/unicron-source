"""Agent enrollment API endpoints for remote go-streamer agents.

Provides:
- POST /enroll: Generate enrollment token + docker run command for new agents
- GET /list: List all registered agents with online/offline status
"""

import os
import re
from glob import glob
from typing import Literal, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.deps.permissions import require_permission
from app.core.logging import get_logger
from app.models.herald.crud.herald_crud import list_registered_herald_ids_by_ids
from app.models.herald.crud.herald_token_crud import (
    create_herald_token,
)
from app.services.agent_registry import get_agent_registry
from app.services.container_cache import get_container_cache
from app.utils.pki.ca_fingerprint import CAFingerprintUnavailable, read_ca_fingerprint

logger = get_logger("routes.agent.enrollment")

router = APIRouter()

OTEL_QUEUE_UNITS_PER_MB = 250
OTEL_QUEUE_SIZE_MIN = 1000
OTEL_QUEUE_SIZE_MAX = 200000
DEFAULT_DOCKER_CONTAINERS_PATH = "/var/lib/docker/containers"
DEFAULT_REMOTE_AGENT_IMAGE = "logforge/unicron-agent:latest"
DOCKER_DESKTOP_WSL_CONTAINER_PATTERNS = (
    "/mnt/wsl/docker-desktop-bind-mounts/*/var/lib/docker/containers",
    "/mnt/wsl/docker-desktop-bind-mounts/*/*/var/lib/docker/containers",
    "/run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/*/var/lib/docker/containers",
    "/run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/*/*/var/lib/docker/containers",
)
CONTAINER_DIR_NAME_RE = re.compile(r"^[0-9a-f]{64}$")


def _derive_otel_queue_size(*, durable_queue: bool, memory_queue_mb: int, disk_queue_mb: int) -> int:
    """Derive OTel exporter queue size from the active queue budget.

    - memory mode: bounded by TELEMETRY_MEMORY_QUEUE_MB
    - durable mode: bounded by TELEMETRY_DISK_QUEUE_MB
    """
    budget_mb = disk_queue_mb if durable_queue else memory_queue_mb
    return max(
        OTEL_QUEUE_SIZE_MIN,
        min(OTEL_QUEUE_SIZE_MAX, budget_mb * OTEL_QUEUE_UNITS_PER_MB),
    )


def _derive_upstream_queue_config(*, memory_queue_mb: int) -> tuple[int, int, int]:
    """Derive upstream transport queue settings from memory budget.

    Returns:
        (critical_queue_size, telemetry_queue_size, critical_enqueue_timeout_ms)
    """
    critical = max(512, min(8192, memory_queue_mb * 4))
    telemetry = max(2048, min(65536, memory_queue_mb * 16))
    critical_timeout_ms = 5000
    return critical, telemetry, critical_timeout_ms


def _docker_container_dir_has_entries(path: str) -> bool:
    try:
        entries = os.listdir(path)
    except OSError:
        return False

    for entry in entries:
        if not CONTAINER_DIR_NAME_RE.fullmatch(entry):
            continue
        if os.path.isdir(os.path.join(path, entry)):
            return True
    return False


def _select_docker_containers_mount_source(candidates: list[str]) -> str:
    for candidate in candidates:
        if _docker_container_dir_has_entries(candidate):
            return candidate
    return DEFAULT_DOCKER_CONTAINERS_PATH


def _resolve_local_docker_containers_mount_source() -> str:
    candidates = [DEFAULT_DOCKER_CONTAINERS_PATH]
    for pattern in DOCKER_DESKTOP_WSL_CONTAINER_PATTERNS:
        candidates.extend(sorted(glob(pattern)))
    return _select_docker_containers_mount_source(candidates)


def _request_origin(request: Request) -> str | None:
    """Build origin from request/forwarded headers when available."""
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",")[0].strip()
    host = forwarded_host or request.headers.get("host")
    if not host:
        return None
    scheme = forwarded_proto or request.url.scheme or "https"
    return f"{scheme}://{host}"


def _normalize_central_url(raw_url: str | None, request: Request | None = None) -> str:
    """Normalize Central public URL for bootstrap endpoints.

    Expected shape is https://<host>/unicron so agent bootstrap hits:
    /unicron/api/pki/*
    """
    request_origin = _request_origin(request) if request else None
    default_origin = request_origin or f"https://{settings.UNICRON_CENTRAL_FQDN}"
    value = (raw_url or f"{default_origin}/unicron").strip().rstrip("/")
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    if not parsed.hostname:
        raise ValueError("central_url must include a hostname")
    # If caller provided only scheme+host, append the expected root path.
    if parsed.path in ("", "/"):
        return f"{value}/unicron"
    return value


def _format_url_host(host: str) -> str:
    """Format hostname for URL construction (supports IPv6 literals)."""
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def _central_mtls_port_for_install_target(install_target: Literal["local", "remote"]) -> int:
    if install_target == "remote":
        return settings.UNICRON_PUBLIC_CENTRAL_MTLS_PORT or settings.UNICRON_CENTRAL_MTLS_PORT
    return settings.UNICRON_CENTRAL_MTLS_PORT


def _derive_central_mtls_url(central_url: str, *, install_target: Literal["local", "remote"] = "remote") -> str:
    """Derive the mTLS origin from the normalized public Central URL."""
    parsed = urlparse(central_url)
    if not parsed.hostname:
        raise ValueError("central_url must include a hostname")
    central_host = _format_url_host(parsed.hostname)
    mtls_port = _central_mtls_port_for_install_target(install_target)
    return f"https://{central_host}:{mtls_port}"


def _derive_central_ws_url(central_url: str, *, install_target: Literal["local", "remote"] = "remote") -> str:
    parsed = urlparse(central_url)
    if not parsed.hostname:
        raise ValueError("central_url must include a hostname")
    central_host = _format_url_host(parsed.hostname)
    mtls_port = _central_mtls_port_for_install_target(install_target)
    return f"wss://{central_host}:{mtls_port}/unicron/api/agent/ws"


def _resolve_local_central_endpoint() -> tuple[str, str, str]:
    central_url = _normalize_central_url(settings.LOCAL_AGENT_CENTRAL_URL)
    parsed = urlparse(central_url)
    central_host = _format_url_host(parsed.hostname or settings.UNICRON_CENTRAL_FQDN)
    docker_network = (settings.LOCAL_AGENT_DOCKER_NETWORK or "").strip()
    return central_url, central_host, docker_network


class EnrollAgentRequest(BaseModel):
    """Request payload for agent enrollment."""
    agent_name: str  # Required: becomes SPIFFE identity and display name
    central_url: Optional[str] = None  # Override Central URL
    install_target: Literal["local", "remote"] = "remote"
    queue_mode: Literal["durable", "memory"] = "memory"
    memory_queue_mb: int = Field(default=256, ge=32, le=4096)
    disk_queue_mb: int = Field(default=1024, ge=128, le=65536)
    flb_storage_sync: Literal["normal", "full"] = "normal"
    flb_storage_max_chunks_up: Optional[int] = Field(default=None, ge=1, le=65536)

    @field_validator("agent_name")
    @classmethod
    def validate_agent_name(cls, v: str) -> str:
        """Validate agent_name format: lowercase alphanumeric with .-_ separators."""
        if not v or len(v) < 1 or len(v) > 63:
            raise ValueError("agent_name must be between 1 and 63 characters")
        if not re.match(r"^[a-z0-9._-]+$", v):
            raise ValueError("agent_name must be lowercase alphanumeric with ._- separators")
        return v


class EnrollAgentResponse(BaseModel):
    """Response payload for agent enrollment."""
    ok: bool
    agent_name: str
    token: str
    docker_run_command: str
    expires_at: float  # Unix timestamp (10 minutes from now)


class AgentFailureInfo(BaseModel):
    code: str
    message: Optional[str] = None


class AgentInfo(BaseModel):
    """Information about a registered agent."""
    agent_id: str
    agent_name: str
    status: str  # "online", "offline", or "blocked"
    container_count: int
    last_seen: Optional[float] = None
    last_status_change: Optional[float] = None
    failure: Optional[AgentFailureInfo] = None


class AgentListResponse(BaseModel):
    """Response payload for agent list."""
    agents: list[AgentInfo]
    total: int = 0
    limit: int = 0
    offset: int = 0


@router.post("/enroll", response_model=EnrollAgentResponse)
async def enroll_agent(
    body: EnrollAgentRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _auth: None = Depends(require_permission({"herald": ["update"]})),
) -> EnrollAgentResponse:
    """Generate enrollment token and docker run command for a new go-streamer agent.

    The returned enrollment token is single-use and expires in 10 minutes.
    After the agent bootstraps its certificate, the token is marked as consumed.

    Args:
        body: Enrollment request with agent_name
        session: Database session

    Returns:
        EnrollAgentResponse with token and docker run command
    """
    import time

    agent_name = body.agent_name
    install_target = body.install_target
    if install_target == "local":
        # Local enrollment assumes the agent runs on the same Docker host as Unicron.
        # Use a shared Docker network endpoint to avoid localhost-in-container failures.
        central_url, _, docker_network = _resolve_local_central_endpoint()
        docker_containers_source = _resolve_local_docker_containers_mount_source()
    else:
        try:
            central_url = _normalize_central_url(body.central_url, request=request)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
        docker_network = ""
        docker_containers_source = DEFAULT_DOCKER_CONTAINERS_PATH
    durable_queue = body.queue_mode == "durable"
    memory_queue_mb = body.memory_queue_mb
    disk_queue_mb = body.disk_queue_mb
    otel_queue_size = _derive_otel_queue_size(
        durable_queue=durable_queue,
        memory_queue_mb=memory_queue_mb,
        disk_queue_mb=disk_queue_mb,
    )
    upstream_critical_q, upstream_telemetry_q, upstream_critical_timeout_ms = _derive_upstream_queue_config(
        memory_queue_mb=memory_queue_mb
    )
    flb_tail_db_path = "/tmp/flb/flb_monitored.db" if durable_queue else "/dev/shm/flb_monitored.db"

    # Create enrollment token in database (reuse herald_token model, status='pending')
    herald_token = await create_herald_token(
        session=session,
        organization_id="",  # Organization context TBD
        herald_name=agent_name,
        central_url=central_url,
        check_in_interval=60,
        tags=["go-streamer", install_target],
    )

    # Read CA fingerprint for TOFU verification
    try:
        ca_fingerprint = read_ca_fingerprint()
    except CAFingerprintUnavailable as e:
        logger.error(
            "Failed to read CA fingerprint",
            extra={"checked_paths": e.checked_paths},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CA fingerprint unavailable"
        ) from e

    # Build Central URLs
    central_ws_url = _derive_central_ws_url(central_url, install_target=install_target)
    central_mtls_url = _derive_central_mtls_url(central_url, install_target=install_target)

    # Generate an idempotent install command. Docker reserves names for stopped
    # containers, so a reinstall after decommission must clear the old container
    # name before `docker run`. Reset the data volume so a fresh enrollment does
    # not reuse stale certificate or root CA material. Durable telemetry queue
    # volumes are only mounted in durable mode and are intentionally preserved.
    container_name = f"unicron-agent-{agent_name}"
    docker_cmd_parts: list[str] = [
        "# Reinstall is idempotent: remove any old container with this agent name.",
        "# Reset only the agent identity/trust volume for this fresh enrollment.",
        "# Durable telemetry queue volumes are preserved when explicitly enabled.",
        f"docker rm -f {container_name} 2>/dev/null || true",
        f"docker volume rm {container_name}-data 2>/dev/null || true",
        f"docker run -d --name {container_name} \\",
        "  --restart unless-stopped \\",
    ]
    if install_target == "local" and docker_network:
        docker_cmd_parts.append(f"  --network {docker_network} \\")
    docker_cmd_parts.extend([
        "  -p 24224:24224 \\",
        "  -p 9880:9880 \\",
        "  -p 4317:4317 \\",
        "  -p 4318:4318 \\",
        "  -v /var/run/docker.sock:/var/run/docker.sock \\",
        "  -v /:/host/root:ro \\",
        f"  -v {docker_containers_source}:/var/lib/docker/containers:ro \\",
    ])
    if durable_queue:
        docker_cmd_parts.extend([
            f"  -v unicron-agent-{agent_name}-otel-queue:/var/lib/otelcol/queue \\",
            f"  -v unicron-agent-{agent_name}-flb-db:/tmp/flb \\",
        ])
    docker_cmd_parts.extend([
        f"  -v unicron-agent-{agent_name}-data:/agent-data \\",
        f"  -e AGENT_NAME={agent_name} \\",
        f"  -e CENTRAL_WS_URL={central_ws_url} \\",
        f"  -e CENTRAL_URL={central_url} \\",
        f"  -e CENTRAL_MTLS_URL={central_mtls_url} \\",
        f"  -e ENROLL_TOKEN={herald_token.id} \\",
        f"  -e CA_FINGERPRINT={ca_fingerprint} \\",
        f"  -e HOST_ID={agent_name} \\",
        f"  -e HERALD_NAME={agent_name} \\",
        f"  -e HERALD_ID={agent_name} \\",
        "  -e HERALD_CA_ROOT=/agent-data/certs/root_ca.crt \\",
        "  -e HERALD_CERT=/agent-data/certs/agent.crt \\",
        "  -e HERALD_KEY=/agent-data/certs/agent.key \\",
        "  -e TELEMETRY_MODE=hybrid \\",
        f"  -e TELEMETRY_QUEUE_MODE={body.queue_mode} \\",
        f"  -e TELEMETRY_MEMORY_QUEUE_MB={memory_queue_mb} \\",
        f"  -e OTEL_SENDING_QUEUE_SIZE={otel_queue_size} \\",
        f"  -e FLB_MEM_BUF_LIMIT={memory_queue_mb}MB \\",
        f"  -e FLB_TAIL_DB_PATH={flb_tail_db_path} \\",
        f"  -e UPSTREAM_CRITICAL_QUEUE_SIZE={upstream_critical_q} \\",
        f"  -e UPSTREAM_TELEMETRY_QUEUE_SIZE={upstream_telemetry_q} \\",
        f"  -e UPSTREAM_CRITICAL_ENQUEUE_TIMEOUT_MS={upstream_critical_timeout_ms} \\",
        "  -e ENVIRONMENT=production \\",
    ])
    if durable_queue:
        docker_cmd_parts.extend(
            [
                f"  -e TELEMETRY_DISK_QUEUE_MB={disk_queue_mb} \\",
                f"  -e FLB_STORAGE_BACKLOG_MEM_LIMIT={memory_queue_mb}MB \\",
                f"  -e FLB_STORAGE_TOTAL_LIMIT={disk_queue_mb}MB \\",
                f"  -e FLB_STORAGE_SYNC={body.flb_storage_sync} \\",
            ]
        )
        if body.flb_storage_max_chunks_up is not None:
            docker_cmd_parts.append(f"  -e FLB_STORAGE_MAX_CHUNKS_UP={body.flb_storage_max_chunks_up} \\")
    agent_image = (settings.REMOTE_AGENT_IMAGE or "").strip() or DEFAULT_REMOTE_AGENT_IMAGE
    docker_cmd_parts.append(f"  {agent_image}")
    docker_cmd = "\n".join(docker_cmd_parts)

    # Token expires in 10 minutes
    expires_at = time.time() + 600

    logger.info(
        "Generated enrollment token for agent",
        extra={"agent_name": agent_name, "install_target": install_target, "queue_mode": body.queue_mode},
    )

    return EnrollAgentResponse(
        ok=True,
        agent_name=agent_name,
        token=herald_token.id,
        docker_run_command=docker_cmd,
        expires_at=expires_at,
    )


@router.get("/list", response_model=AgentListResponse)
async def list_agents(
    status_filter: Literal["all", "online", "offline", "blocked"] = Query(
        default="all",
        alias="status",
        description="Filter returned agents by status.",
    ),
    limit: int = Query(default=200, ge=1, le=1000, description="Maximum agents per page."),
    offset: int = Query(default=0, ge=0, description="Offset into filtered agent list."),
    session: AsyncSession = Depends(get_session),
    _auth: None = Depends(require_permission({"herald": ["read"]})),
) -> AgentListResponse:
    """List all registered agents with online/offline status and container counts.

    Combines data from:
    - AgentRegistry: Currently connected agents
    - ContainerCache: Cached agent data (includes recently offline agents)

    Returns:
        AgentListResponse with list of all known agents
    """
    registry = get_agent_registry()
    cache = get_container_cache()

    registry_hosts = registry.list_hosts()
    host_ids: list[str] = list(registry_hosts.keys())

    try:
        cached_hosts = await cache.get_all_hosts()
        host_ids.extend(
            host_id.decode("utf-8") if isinstance(host_id, bytes) else str(host_id)
            for host_id in cached_hosts
        )
    except Exception:
        logger.debug("Failed to get hosts from cache", exc_info=True)

    deduped_host_ids = sorted(set(host_ids))
    deduped_host_ids = await list_registered_herald_ids_by_ids(session, deduped_host_ids)

    (
        cache_host_statuses,
        cache_host_last_seen,
        cache_host_status_changed,
        cache_host_container_counts,
    ) = await cache.get_host_status_snapshot(deduped_host_ids)

    agents_dict: dict[str, AgentInfo] = {}

    for host_id in deduped_host_ids:
        conn = registry_hosts.get(host_id)
        cached_online = cache_host_statuses.get(host_id)
        is_online = cached_online if cached_online is not None else (conn.online if conn is not None else False)
        cache_last_seen = cache_host_last_seen.get(host_id)
        registry_last_seen = conn.last_seen if conn is not None else None

        agents_dict[host_id] = AgentInfo(
            agent_id=host_id,
            agent_name=host_id,
            status="online" if is_online else "offline",
            container_count=int(cache_host_container_counts.get(host_id, 0)),
            last_seen=(
                float(cache_last_seen)
                if cache_last_seen is not None
                else registry_last_seen
            ),
            last_status_change=float(cache_host_status_changed.get(host_id))
            if cache_host_status_changed.get(host_id) is not None
            else None,
        )

    # Convert to list and sort by agent_name.
    agents_list = sorted(agents_dict.values(), key=lambda a: a.agent_name)
    if status_filter != "all":
        agents_list = [agent for agent in agents_list if agent.status == status_filter]

    total = len(agents_list)
    paged_agents = agents_list[offset : offset + limit]

    return AgentListResponse(
        agents=paged_agents,
        total=total,
        limit=limit,
        offset=offset,
    )
