import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.core.docker_client import get_docker_client, reset_docker_client
from app.core.logging import get_logger
from docker.errors import DockerException

from unicron_shared import ContainerState, ContainerStaticMetrics

logger = get_logger("herald.tasks.inventory.collector")


def _parse_docker_timestamp(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None

    value = raw.strip()
    if not value or value in {"0001-01-01T00:00:00Z", "0001-01-01T00:00:00.000000Z"}:
        return None

    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        logger.debug("Unable to parse Docker timestamp: %s", raw)
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def _extract_cpu_limit(host_config: Dict[str, object]) -> Optional[float]:
    nano_cpus = host_config.get("NanoCpus")
    if isinstance(nano_cpus, (int, float)) and nano_cpus > 0:
        return float(nano_cpus) / 1_000_000_000

    cpu_quota = host_config.get("CpuQuota")
    cpu_period = host_config.get("CpuPeriod")
    if (
        isinstance(cpu_quota, (int, float))
        and isinstance(cpu_period, (int, float))
        and cpu_quota > 0
        and cpu_period > 0
    ):
        return float(cpu_quota) / float(cpu_period)

    return None


def _extract_memory_limit(host_config: Dict[str, object]) -> Optional[int]:
    memory_limit = host_config.get("Memory")
    if isinstance(memory_limit, int) and memory_limit > 0:
        return memory_limit
    if isinstance(memory_limit, float) and memory_limit > 0:
        return int(memory_limit)
    return None


def _coerce_command(parts: Optional[object]) -> Optional[str]:
    if parts is None:
        return None
    if isinstance(parts, str):
        return parts.strip() or None
    if isinstance(parts, (list, tuple)):
        cleaned = [str(part).strip() for part in parts if isinstance(part, (str, int, float))]
        return " ".join(item for item in cleaned if item) or None
    return None


def _collect_environment(config: Dict[str, object]) -> List[str]:
    env = config.get("Env")
    if not isinstance(env, list):
        return []
    values: List[str] = []
    for value in env:
        if isinstance(value, str):
            values.append(value)
    return values


def _collect_mounts(attrs: Dict[str, object]) -> List[Dict[str, object]]:
    raw_mounts = attrs.get("Mounts")
    if not isinstance(raw_mounts, list):
        return []

    allowed_keys = {"Type", "Name", "Source", "Destination", "Driver", "Mode", "RW", "Propagation"}
    mounts: List[Dict[str, object]] = []
    for mount in raw_mounts:
        if isinstance(mount, dict):
            mounts.append({key: mount.get(key) for key in allowed_keys})
    return mounts


def _collect_ports(network_settings: Dict[str, object]) -> Dict[str, List[Dict[str, Optional[str]]]]:
    raw_ports = network_settings.get("Ports")
    if not isinstance(raw_ports, dict):
        return {}

    ports: Dict[str, List[Dict[str, Optional[str]]]] = {}
    for port, bindings in raw_ports.items():
        if bindings is None:
            ports[port] = []
            continue
        if not isinstance(bindings, list):
            ports[port] = []
            continue
        cleaned: List[Dict[str, Optional[str]]] = []
        for binding in bindings:
            if isinstance(binding, dict):
                cleaned.append(
                    {
                        "HostIp": binding.get("HostIp"),
                        "HostPort": binding.get("HostPort"),
                    }
                )
        ports[port] = cleaned
    return ports


def _collect_networks(network_settings: Dict[str, object]) -> Dict[str, Dict[str, object]]:
    raw_networks = network_settings.get("Networks")
    if not isinstance(raw_networks, dict):
        return {}

    allowed_keys = {
        "IPAMConfig",
        "Links",
        "Aliases",
        "NetworkID",
        "EndpointID",
        "Gateway",
        "IPAddress",
        "IPPrefixLen",
        "IPv6Gateway",
        "GlobalIPv6Address",
        "GlobalIPv6PrefixLen",
        "MacAddress",
        "DriverOpts",
    }

    networks: Dict[str, Dict[str, object]] = {}
    for name, config in raw_networks.items():
        if isinstance(config, dict):
            networks[name] = {key: config.get(key) for key in allowed_keys if key in config}
    return networks


def _collect_container_states_sync() -> List[ContainerState]:
    client = get_docker_client()
    if client is None:
        return []

    try:
        docker_containers = client.containers.list(all=True)
    except DockerException as exc:
        logger.error("Failed to list Docker containers: %s", exc, exc_info=True)
        reset_docker_client()
        return []

    containers: List[ContainerState] = []
    for container in docker_containers:
        try:
            attrs = container.attrs or {}
        except DockerException as exc:
            logger.debug("Skipping container due to attrs fetch error: %s", exc)
            continue

        state = attrs.get("State") or {}
        name = (container.name or attrs.get("Name") or "").lstrip("/")
        container_id = container.id or attrs.get("Id")
        status = state.get("Status") or getattr(container, "status", None)

        if not name or not container_id:
            logger.debug("Skipping container with missing name/id: %s", attrs)
            continue

        # Herald currently treats skip_checks as a backend concern; default to True.
        skip_checks = True

        started_at = _parse_docker_timestamp(state.get("StartedAt") or attrs.get("Created"))

        config = attrs.get("Config") or {}
        host_config = attrs.get("HostConfig") or {}
        restart_policy = (host_config.get("RestartPolicy") or {}).get("Name")

        network_settings = attrs.get("NetworkSettings") or {}

        static_metrics = ContainerStaticMetrics(
            image=config.get("Image") or attrs.get("Config", {}).get("Image"),
            image_id=attrs.get("Image"),
            labels={
                k: v for k, v in (config.get("Labels") or {}).items() if isinstance(k, str) and isinstance(v, str)
            },
            cpu_limit=_extract_cpu_limit(host_config),
            memory_limit_bytes=_extract_memory_limit(host_config),
            restart_policy=restart_policy,
            created_at=_parse_docker_timestamp(attrs.get("Created")),
            command=_coerce_command(config.get("Cmd") or attrs.get("Config", {}).get("Cmd")),
            entrypoint=_coerce_command(config.get("Entrypoint") or attrs.get("Config", {}).get("Entrypoint")),
            working_dir=config.get("WorkingDir") or None,
            environment=_collect_environment(config),
            mounts=_collect_mounts(attrs),
            ports=_collect_ports(network_settings),
            networks=_collect_networks(network_settings),
        )

        containers.append(
            ContainerState(
                name=name,
                container_id=container_id,
                status=status,
                started_at=started_at,
                skip_checks=skip_checks,
                group=None,
                static=static_metrics,
            )
        )

    return containers


async def collect_container_states() -> List[ContainerState]:
    try:
        return await asyncio.to_thread(_collect_container_states_sync)
    except DockerException as exc:
        logger.error("Docker error while collecting inventory: %s", exc, exc_info=True)
    except Exception as exc:  # pragma: no cover - defensive guardrail
        logger.error("Unexpected error while collecting inventory: %s", exc, exc_info=True)
    return []
