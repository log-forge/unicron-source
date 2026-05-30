import threading
from typing import Optional

import docker
from app.core.config import settings
from app.core.logging import get_logger
from docker import DockerClient
from docker.errors import DockerException

logger = get_logger("herald.core.docker_client")

_client_lock = threading.Lock()
_client: Optional[DockerClient] = None


def _build_client() -> Optional[DockerClient]:
    try:
        client = (
            docker.DockerClient(base_url=settings.DOCKER_ENDPOINT) if settings.DOCKER_ENDPOINT else docker.from_env()
        )
        client.ping()
        return client
    except DockerException as exc:
        logger.warning("Failed to initialize Docker client: %s", exc, exc_info=True)
    except Exception as exc:  # pragma: no cover - defensive guardrail
        logger.error("Unexpected error creating Docker client: %s", exc, exc_info=True)
    return None


def get_docker_client(recreate: bool = False) -> Optional[DockerClient]:
    global _client
    with _client_lock:
        if recreate and _client is not None:
            _dispose_locked()
        if _client is None:
            _client = _build_client()
        return _client


def reset_docker_client() -> None:
    with _client_lock:
        _dispose_locked()


def _dispose_locked() -> None:
    global _client
    if _client is None:
        return
    try:
        _client.close()
    except Exception:
        pass
    _client = None


__all__ = ["get_docker_client", "reset_docker_client"]
