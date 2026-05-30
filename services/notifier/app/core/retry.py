"""Retry utilities for infrastructure connection resilience.

Provides exponential backoff retry logic for database and Redis connections.
Configured for 2-minute timeout with increasing delays.
"""

import asyncio
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from app.core.logging import get_logger

logger = get_logger("notifier.core.retry")

# Default retry configuration
DEFAULT_MAX_ATTEMPTS = 12  # ~2 minutes with exponential backoff
DEFAULT_BASE_DELAY = 1.0  # Initial delay in seconds
DEFAULT_MAX_DELAY = 30.0  # Cap delay at 30 seconds
DEFAULT_TIMEOUT = 120.0  # 2 minute total timeout

T = TypeVar("T")


class ConnectionError(Exception):
    """Raised when connection cannot be established after retries."""
    pass


async def retry_connection(
    connect_fn: Callable[[], Any],
    service_name: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
) -> Any:
    """
    Retry a connection function with exponential backoff.

    Args:
        connect_fn: Async function that attempts connection.
        service_name: Name for logging (e.g., "PostgreSQL", "Redis").
        max_attempts: Maximum retry attempts before giving up.
        base_delay: Initial delay between attempts (doubles each retry).
        max_delay: Maximum delay cap.

    Returns:
        Result of successful connect_fn call.

    Raises:
        ConnectionError: If all retry attempts fail.
    """
    last_error: Optional[Exception] = None
    delay = base_delay

    for attempt in range(1, max_attempts + 1):
        try:
            result = await connect_fn()
            if attempt > 1:
                logger.info(
                    "%s connected successfully after %d attempts",
                    service_name,
                    attempt,
                )
            return result
        except Exception as e:
            last_error = e
            if attempt < max_attempts:
                logger.warning(
                    "%s connection attempt %d/%d failed: %s. Retrying in %.1fs...",
                    service_name,
                    attempt,
                    max_attempts,
                    str(e),
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
            else:
                logger.error(
                    "%s connection failed after %d attempts: %s",
                    service_name,
                    max_attempts,
                    str(e),
                )

    raise ConnectionError(
        f"Failed to connect to {service_name} after {max_attempts} attempts: {last_error}"
    )


def with_reconnect(service_name: str):
    """
    Decorator for auto-reconnect on mid-operation failures.

    Retries the operation once on connection errors, triggering reconnection.
    """
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        async def wrapper(*args, **kwargs) -> T:
            try:
                return await fn(*args, **kwargs)
            except (ConnectionRefusedError, OSError, IOError) as e:
                logger.warning(
                    "%s connection lost during operation, retrying: %s",
                    service_name,
                    str(e),
                )
                # One retry after brief delay
                await asyncio.sleep(0.5)
                return await fn(*args, **kwargs)
        return wrapper
    return decorator


__all__ = ["retry_connection", "with_reconnect", "ConnectionError"]
