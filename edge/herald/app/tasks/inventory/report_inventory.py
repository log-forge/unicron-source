import importlib.metadata
import os
import platform
import socket
from datetime import datetime, timezone
from itertools import count
from typing import Optional

from app.core.config import settings
from app.core.docker_client import get_docker_client
from app.core.logging import get_logger
from app.utils.httpx_client import parse_response, send_mtls_request
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from docker.errors import DockerException

from unicron_shared import HeraldInventoryPayload, HeraldInventoryResponse, HeraldStaticMetrics

from .collector import collect_container_states

logger = get_logger("herald.tasks.inventory.report")
_SEQUENCE_COUNTER = count(1)

INVENTORY_INTERVAL = getattr(settings, "INVENTORY_INTERVAL", 300)
JITTER_PERCENT = 0.2
JITTER_SECONDS = max(1, int(INVENTORY_INTERVAL * JITTER_PERCENT)) if INVENTORY_INTERVAL >= 1 else 0


def _next_sequence() -> int:
    return next(_SEQUENCE_COUNTER)


async def submit_inventory() -> None:
    if not settings.HERALD_ID:
        logger.debug("HERALD_ID missing; skipping inventory submission")
        return

    containers = await collect_container_states()
    herald_static = _collect_herald_static_metrics()
    payload = HeraldInventoryPayload(
        herald_id=settings.HERALD_ID,
        reported_at=datetime.now(timezone.utc),
        sequence=_next_sequence(),
        containers=containers,
        herald_static=herald_static,
    )

    response = await send_mtls_request(
        "POST",
        "/herald/inventory",
        json=payload,
        json_model=HeraldInventoryPayload,
        timeout=15.0,
    )
    if response is None:
        logger.warning("submit_inventory: No response returned from POST /herald/inventory")
        return

    ack = parse_response(response, HeraldInventoryResponse)
    if ack is None:
        logger.info("submit_inventory: Response did not validate as HeraldInventoryResponse")
        return
    if not ack.accepted:
        logger.warning("Inventory payload was rejected; accepted_sequence=%s", ack.accepted_sequence)
    else:
        logger.debug(
            "Inventory posted successfully; accepted_sequence=%s, processed_at=%s",
            ack.accepted_sequence,
            ack.processed_at,
        )


def register_jobs(sched: AsyncIOScheduler, *, immediate_first_run: bool = False) -> None:
    """Register inventory jobs on the provided scheduler.

    If `immediate_first_run` is True, the job will be scheduled to run immediately
    once by setting `next_run_time` to now in UTC. The default behavior preserves
    the existing semantics (first run after the configured interval).
    """
    if INVENTORY_INTERVAL <= 0:
        logger.warning("Inventory interval <= 0; skipping inventory scheduler setup")
        return

    if immediate_first_run:
        sched.add_job(
            submit_inventory,
            "interval",
            seconds=INVENTORY_INTERVAL,
            id="inventory_submit",
            max_instances=1,
            replace_existing=True,
            jitter=JITTER_SECONDS,
            next_run_time=datetime.now(timezone.utc),
        )
    else:
        sched.add_job(
            submit_inventory,
            "interval",
            seconds=INVENTORY_INTERVAL,
            id="inventory_submit",
            max_instances=1,
            replace_existing=True,
            jitter=JITTER_SECONDS,
        )


# Convenience wrapper for other modules to start job immediately if needed
async def trigger_once() -> None:
    await submit_inventory()


def _collect_herald_static_metrics() -> Optional[HeraldStaticMetrics]:
    hostname = None
    try:
        hostname = socket.gethostname()
    except Exception:
        logger.debug("Unable to determine hostname", exc_info=True)

    cpu_count = os.cpu_count()

    total_memory = None
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as meminfo:
            for line in meminfo:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        total_memory = int(parts[1]) * 1024
                        break
    except FileNotFoundError:
        logger.debug("/proc/meminfo not available for total memory detection")
    except Exception:
        logger.debug("Failed to parse /proc/meminfo", exc_info=True)

    herald_version = _detect_herald_version_from_image(hostname)
    if herald_version is None:
        herald_version = os.getenv("HERALD_herald_version") or None
    if herald_version is None:
        try:
            herald_version = importlib.metadata.version("backend")
        except importlib.metadata.PackageNotFoundError:
            logger.debug("Unable to resolve herald agent package version")
        except Exception:
            logger.debug("Unexpected error while fetching agent version", exc_info=True)

    return HeraldStaticMetrics(
        hostname=hostname,
        os=platform.system() or None,
        os_version=platform.version() or None,
        architecture=platform.machine() or None,
        cpu_count=cpu_count,
        total_memory_bytes=total_memory,
        herald_version=herald_version,
    )


def _detect_herald_version_from_image(hostname: Optional[str]) -> Optional[str]:
    if not hostname:
        return None

    client = get_docker_client()
    if client is None:
        return None

    container = None
    try:
        container = client.containers.get(hostname)
    except DockerException:
        container = None

    if container is None:
        try:
            for candidate in client.containers.list(all=True):
                attrs = getattr(candidate, "attrs", {}) or {}
                config = attrs.get("Config") or {}
                config_hostname = config.get("Hostname")
                if hostname in {candidate.id, candidate.short_id, candidate.name, config_hostname}:
                    container = candidate
                    break
        except DockerException as exc:
            logger.debug("Unable to enumerate containers for agent version detection: %s", exc)
            return None

    if container is None:
        return None

    try:
        image_obj = getattr(container, "image", None)
        tags = []
        if image_obj is not None:
            tags = list(getattr(image_obj, "tags", []) or [])
            if tags:
                return tags[0]
            image_id = getattr(image_obj, "id", None)
            if image_id:
                return image_id

        attrs = getattr(container, "attrs", {}) or {}
        config = attrs.get("Config") or {}
        image = config.get("Image")
        return image or None
    except DockerException as exc:
        logger.debug("Unable to resolve agent image for container %s: %s", hostname, exc)
    except Exception as exc:  # pragma: no cover - defensive guardrail
        logger.debug("Unexpected error while resolving agent image: %s", exc, exc_info=True)
    return None
