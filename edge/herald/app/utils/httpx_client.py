# httpx_client.py  (now aiohttp-backed, preserves your public API shape)
import json
import os
import ssl
from typing import Any, Dict, Optional, Type, TypeVar, Union

import aiohttp
from app.core.config import settings
from app.core.logging import get_logger
from pydantic import BaseModel, ValidationError

logger = get_logger("herald.utils.http_client")

_cached_ssl_context: Optional[ssl.SSLContext] = None
T = TypeVar("T", bound=BaseModel)


def get_cached_ssl_context() -> Optional[ssl.SSLContext]:
    """Build/cache an SSLContext with CA + client cert for mTLS."""
    global _cached_ssl_context
    if _cached_ssl_context is not None:
        return _cached_ssl_context
    try:
        ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        if os.path.exists(settings.HERALD_CA_ROOT):
            ctx.load_verify_locations(settings.HERALD_CA_ROOT)
        else:
            logger.warning("CA root not found at %s; TLS verification may fail", settings.HERALD_CA_ROOT)

        if os.path.exists(settings.HERALD_CERT) and os.path.exists(settings.HERALD_KEY):
            try:
                ctx.load_cert_chain(certfile=settings.HERALD_CERT, keyfile=settings.HERALD_KEY)
            except Exception as e:
                logger.warning("Failed to load client cert/key into SSLContext: %s", e, exc_info=True)
        else:
            logger.warning("Client cert or key not found (%s, %s)", settings.HERALD_CERT, settings.HERALD_KEY)

        _cached_ssl_context = ctx
        return _cached_ssl_context
    except Exception as e:
        logger.error("Failed to construct SSLContext: %s", e, exc_info=True)
        return None


class _ResponseAdapter:
    """Tiny adapter so existing parse_response() keeps working sync."""

    def __init__(self, status: int, text: str):
        self.status_code = status
        self._text = text

    @property
    def text(self) -> str:
        return self._text

    def json(self) -> Any:
        return json.loads(self._text)

    def raise_for_status(self) -> None:
        if not (200 <= self.status_code < 400):
            # Simple error with status code
            raise RuntimeError(f"HTTP error {self.status_code}")


async def send_mtls_request(
    method: str,
    request_url: str,
    *,
    json: Optional[Union[Dict[str, Any], T]] = None,
    json_model: Optional[Type[T]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
) -> Optional[_ResponseAdapter]:
    """Send an async mTLS request using aiohttp and return an adapter."""
    # Prepare/validate JSON payload (same logic you had)
    try:
        if json_model is not None:
            if isinstance(json, json_model):
                json = json.model_dump(mode="json")
            elif isinstance(json, BaseModel):
                json = json_model.model_validate(json.model_dump(mode="json")).model_dump(mode="json")
            else:
                json = json_model(**(json or {})).model_dump(mode="json")
        elif isinstance(json, BaseModel):
            json = json.model_dump(mode="json")
        else:
            if json is not None and not isinstance(json, dict):
                raise TypeError(f"Unsupported json payload type: {type(json)!r}")
    except Exception as e:
        model_name = getattr(json_model, "__name__", "<pydantic>") if json_model else "<pydantic>"
        logger.error("Failed to prepare outbound JSON (%s): %s", model_name, e, exc_info=True)
        return None

    ssl_ctx = get_cached_ssl_context()
    if ssl_ctx is None:
        logger.error("No SSL context available for mTLS request")
        return None

    url = f"{settings.CENTRAL_MTLS_URL}{settings.API_BASE_URL}{request_url}"
    try:
        timeout_cfg = aiohttp.ClientTimeout(total=timeout)
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        async with aiohttp.ClientSession(timeout=timeout_cfg, connector=connector) as session:
            async with session.request(method, url, json=json, headers=headers or {}) as resp:
                body = await resp.text()
                return _ResponseAdapter(resp.status, body)
    except Exception as e:
        logger.error("send_mtls_request (aiohttp) failed: %s", e, exc_info=True)
        return None


def parse_response(response: _ResponseAdapter, model: Type[T]) -> Optional[T]:
    """Validate adapter response and parse JSON into a Pydantic model (sync)."""
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
    except Exception:
        logger.error("Response body is not valid JSON: %s", getattr(response, "text", "<no-body>"))
        return None

    try:
        parsed = model.model_validate(data)
        logger.info("parse_response validated payload: %s", parsed)
        return parsed
    except ValidationError as ve:
        logger.error("Response did not validate against model %s: %s; body=%s", model.__name__, ve, response.text)
        return None
