import os
import ssl
from typing import Any, Dict, Optional, Tuple, Type, TypeVar, Union

import httpx
from app.core.config import settings
from app.core.logging import get_logger
from pydantic import BaseModel, ValidationError

logger = get_logger("backend.utils.httpx_client")

# Simple module-level cache for a constructed SSLContext.
_cached_ssl_context: Optional[ssl.SSLContext] = None


T = TypeVar("T", bound=BaseModel)


def get_cached_ssl_context() -> Optional[ssl.SSLContext]:
    """Return a cached SSLContext or create one if needed.

    For Traefik calls we use one-way TLS only: the context loads
    `ROOT_CA` as the trust store and does NOT load any client
    certificate or key.
    """
    global _cached_ssl_context
    if _cached_ssl_context is not None:
        return _cached_ssl_context

    try:
        ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        if os.path.exists(settings.ROOT_CA):
            ctx.load_verify_locations(settings.ROOT_CA)
        else:
            logger.warning(
                "CA root not found at %s; TLS verification may fail",
                settings.ROOT_CA,
            )

        _cached_ssl_context = ctx
        return _cached_ssl_context
    except Exception as e:
        logger.error("Failed to construct SSLContext: %s", e, exc_info=True)
        return None


def build_async_client(use_standard_ca: bool = False, verify_tls: bool = True, **overrides) -> httpx.AsyncClient:
    """
    Async client pinned to the cached SSL context (or ROOT_CA fallback).
    Use this for VictoriaLogs/VictoriaMetrics calls (including streaming).

    Args:
        use_standard_ca: If True, use standard OS certificate store (verify=True).
                        If False, use Traefik SSL context from ROOT_CA.
        verify_tls: If False, disable TLS verification entirely (for self-signed certs in dev).
    """
    if not verify_tls:
        verify = False
    elif use_standard_ca:
        verify = True
    else:
        verify = get_cached_ssl_context() or settings.ROOT_CA
    return httpx.AsyncClient(verify=verify, **overrides)


async def send_tls_request(
    method: str,
    request_url: str,
    *,
    json: Optional[Union[Dict[str, Any], T]] = None,
    json_model: Optional[Type[T]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
    use_standard_ca: bool = False,
    verify_tls: bool = True,
    base_url: Optional[str] = None,
    expected_status_codes: Optional[Tuple[int, ...]] = None,
    request_name: str = "upstream request",
) -> Optional[httpx.Response]:
    """Send an async TLS (one-way) request using httpx.AsyncClient.

    This helper constructs an SSLContext using `settings.ROOT_CA` as the
    trust store and supplies it to httpx for server verification. No client
    certificate is presented. If constructing the SSLContext fails, it will
    fall back to using the `ROOT_CA` path for verification.

    Payload handling:
        - If `json_model` is provided: `json` may be a dict, None, or any Pydantic
            model instance. It will be coerced/validated into the target model and
            serialized via model_dump().
        - If `json_model` is not provided but `json` is a Pydantic model instance,
            it will be serialized via model_dump().
        - If `json` is a plain dict (and no model provided) it is sent as-is.

    Args:
        use_standard_ca: If True, use standard OS certificate store (verify=True).
                        If False, use Traefik SSL context from ROOT_CA.
        verify_tls: If False, disable TLS verification entirely (for self-signed certs in dev).
        base_url: Optional base URL for the request. If not provided, defaults to
                internal Traefik infrastructure URL.
        expected_status_codes: If provided, responses whose status_code is not in
            this tuple are logged and treated as failures (returns None).
        request_name: Human-friendly label used in error logs.

    Returns the httpx.Response on success, or None on error (all errors logged).
    """
    if not verify_tls:
        verify = False
    elif use_standard_ca:
        verify = True
    else:
        verify = get_cached_ssl_context() or settings.ROOT_CA

    if base_url is None:
        url = f"https://unicron-traefik{settings.API_BASE_URL}{request_url}"
    else:
        url = f"{base_url.rstrip('/')}{request_url}"

    # Normalize/validate outbound JSON payload.
    try:
        if json_model is not None:
            if isinstance(json, json_model):  # Already correct model instance
                json = json.model_dump(mode="json")
            elif isinstance(json, BaseModel):  # Different model type; revalidate via target
                json = json_model.model_validate(json.model_dump(mode="json")).model_dump(mode="json")
            else:  # Dict or None
                json = json_model(**(json or {})).model_dump(mode="json")
        elif isinstance(json, BaseModel):  # No explicit model type provided, serialize as-is
            json = json.model_dump(mode="json")
        else:
            # Accept None or dict. If it's not a dict/None raise a logged error.
            if json is not None and not isinstance(json, dict):
                raise TypeError(f"Unsupported json payload type: {type(json)!r}; expected dict, BaseModel, or None")
    except Exception as e:
        model_name = getattr(json_model, "__name__", "<pydantic>") if json_model else "<pydantic>"
        logger.error("Failed to prepare outbound JSON (%s): %s", model_name, e, exc_info=True)
        return None

    try:
        async with httpx.AsyncClient(verify=verify, timeout=timeout) as client:
            response = await client.request(method, url, json=json, headers=headers or {})
            if expected_status_codes is not None and response.status_code not in expected_status_codes:
                logger.warning(
                    "%s returned unexpected status %s for %s",
                    request_name,
                    response.status_code,
                    url,
                )
                return None
            return response
    except Exception as e:
        logger.error("%s failed: %s", request_name, e, exc_info=True)
        return None


def parse_response(response: Optional[httpx.Response], model: Type[T]) -> Optional[T]:
    """Validate an httpx.Response (if present) and parse its JSON into a Pydantic model.

    - If `response` is None: logs and returns None.
    - Logs and returns None for HTTP status errors.
    - Parses JSON and validates against `model`.
    """
    if response is None:
        logger.error("parse_response called with None response")
        return None

    try:
        response.raise_for_status()
    except Exception as e:
        logger.error("HTTP error from upstream: %s; body=%s", e, getattr(response, "text", "<no-body>"))
        return None

    try:
        data = response.json()
    except ValueError:
        logger.error("Response body is not valid JSON: %s", getattr(response, "text", "<no-body>"))
        return None

    try:
        parsed = model.model_validate(data)
        if parsed is None:
            logger.info(
                "Response did not validate as %s or had error; raw status=%s, body=%s",
                model.__name__,
                getattr(response, "status_code", getattr(response, "status", "?")),
                getattr(response, "text", "<no-body>"),
            )
        else:
            logger.info("parse_response validated payload: %s", parsed)
        return parsed
    except ValidationError as ve:
        logger.error("Response did not validate against model %s: %s; body=%s", model.__name__, ve, response.text)
        return None


__all__ = ["get_cached_ssl_context", "build_async_client", "send_tls_request", "parse_response"]
