import asyncio
import hashlib
import hmac
from time import monotonic
from typing import Any, Dict, Optional

import httpx
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.utils.httpx_client import parse_response
from pydantic import BaseModel, Field

LOCAL_DEPLOYMENT_ID = "local"

logger = get_logger("backend.utils.central_auth_client")


class LocalAdminSession(BaseModel):
    user: Optional[Dict[str, Any]] = None
    session: Optional[Dict[str, Any]] = None
    isAdmin: bool = True
    deploymentId: str = LOCAL_DEPLOYMENT_ID
    requiresPasswordChange: bool = False
    team_ids: list[str] = Field(default_factory=list)
    role: str = "admin"

    @property
    def user_id(self) -> Optional[str]:
        return str(self.user.get("id")) if self.user and self.user.get("id") else None

    @property
    def username(self) -> str:
        if not self.user:
            return ""
        return str(
            self.user.get("username")
            or self.user.get("displayUsername")
            or self.user.get("name")
            or ""
        )

    @property
    def display_name(self) -> str:
        if not self.user:
            return ""
        return str(
            self.user.get("displayUsername")
            or self.user.get("name")
            or self.user.get("username")
            or ""
        )


class CentralAuthProfileResponse(BaseModel):
    status: Optional[str] = None
    data: Optional[LocalAdminSession] = None


_CACHE_VERSION = "v1"
_L1_MAX_ENTRIES = 4096
_l1_cache: Dict[str, tuple[float, float, LocalAdminSession]] = {}
_l1_cache_lock = asyncio.Lock()
_profile_client: Optional[httpx.AsyncClient] = None
_profile_client_base = ""
_profile_client_verify: Optional[bool] = None
_profile_client_lock = asyncio.Lock()


def _resolve_base_url() -> Optional[str]:
    base = settings.CENTRAL_AUTH_BASE_URL.strip()
    if not base:
        if settings.ENVIRONMENT != "production":
            return "http://central-auth:3020"
        return None
    return base.rstrip("/")


def _session_cache_enabled() -> bool:
    return (
        settings.CENTRAL_AUTH_SESSION_CACHE_ENABLED
        and int(settings.CENTRAL_AUTH_SESSION_CACHE_TTL_SECONDS) > 0
    )


def _session_l1_cache_enabled() -> bool:
    return (
        settings.CENTRAL_AUTH_SESSION_L1_CACHE_ENABLED
        and int(settings.CENTRAL_AUTH_SESSION_L1_CACHE_TTL_SECONDS) > 0
    )


def _session_cache_key(cookie_header: str) -> str:
    prefix = (
        settings.CENTRAL_AUTH_SESSION_CACHE_PREFIX or ""
    ).strip() or "unicron:auth:central_auth_session"
    secret = (settings.INTERNAL_API_SECRET or "dev-session-cache").encode("utf-8")
    digest = hmac.new(secret, cookie_header.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{prefix}:{_CACHE_VERSION}:{digest}"


def _session_cache_lock_key(cookie_header: str) -> str:
    return f"{_session_cache_key(cookie_header)}:refresh-lock"


async def _load_l1_session(cookie_header: str, *, allow_stale: bool = False) -> Optional[LocalAdminSession]:
    if not _session_l1_cache_enabled():
        return None
    key = _session_cache_key(cookie_header)
    entry = _l1_cache.get(key)
    if entry is None:
        return None
    fresh_until, stale_until, session = entry
    now = monotonic()
    if fresh_until > now:
        return session
    if allow_stale and stale_until > now:
        return session
    _l1_cache.pop(key, None)
    return None


async def _store_l1_session(cookie_header: str, session: LocalAdminSession) -> None:
    if not _session_l1_cache_enabled() or not session.user:
        return
    ttl = max(1, int(settings.CENTRAL_AUTH_SESSION_L1_CACHE_TTL_SECONDS))
    stale_grace = max(0, int(settings.CENTRAL_AUTH_SESSION_L1_STALE_GRACE_SECONDS))
    key = _session_cache_key(cookie_header)
    async with _l1_cache_lock:
        now = monotonic()
        _l1_cache[key] = (now + ttl, now + ttl + stale_grace, session)
        if len(_l1_cache) <= _L1_MAX_ENTRIES:
            return
        stale_keys = [k for k, (_fresh_until, stale_until, _) in _l1_cache.items() if stale_until <= now]
        for stale_key in stale_keys:
            _l1_cache.pop(stale_key, None)
        while len(_l1_cache) > _L1_MAX_ENTRIES:
            oldest_key = next(iter(_l1_cache))
            _l1_cache.pop(oldest_key, None)


async def _get_profile_client(base_url: str) -> httpx.AsyncClient:
    global _profile_client, _profile_client_base, _profile_client_verify
    verify = bool(settings.CENTRAL_AUTH_VERIFY_TLS)
    async with _profile_client_lock:
        if (
            _profile_client is not None
            and _profile_client_base == base_url
            and _profile_client_verify == verify
        ):
            return _profile_client

        if _profile_client is not None:
            await _profile_client.aclose()
            _profile_client = None

        _profile_client = httpx.AsyncClient(base_url=base_url, verify=verify, timeout=10.0)
        _profile_client_base = base_url
        _profile_client_verify = verify
        return _profile_client


async def _reset_profile_client() -> None:
    global _profile_client, _profile_client_base, _profile_client_verify
    async with _profile_client_lock:
        if _profile_client is not None:
            await _profile_client.aclose()
        _profile_client = None
        _profile_client_base = ""
        _profile_client_verify = None


async def _load_cached_session(cookie_header: str) -> Optional[LocalAdminSession]:
    if not _session_cache_enabled():
        return None
    try:
        client = await get_redis()
        payload = await client.get(_session_cache_key(cookie_header))
    except Exception as exc:
        logger.debug("Central Auth session cache read failed: %s", exc)
        return None

    if not payload:
        return None

    try:
        session = LocalAdminSession.model_validate_json(payload)
        await _store_l1_session(cookie_header, session)
        return session
    except Exception as exc:
        logger.warning("Central Auth session cache parse failed, evicting key: %s", exc)
        try:
            await client.delete(_session_cache_key(cookie_header))
        except Exception:
            pass
        return None


async def _store_cached_session(cookie_header: str, session: LocalAdminSession) -> None:
    await _store_l1_session(cookie_header, session)
    if not _session_cache_enabled() or not session.user:
        return

    ttl = max(1, int(settings.CENTRAL_AUTH_SESSION_CACHE_TTL_SECONDS))
    try:
        client = await get_redis()
        await client.set(_session_cache_key(cookie_header), session.model_dump_json(), ex=ttl)
    except Exception as exc:
        logger.debug("Central Auth session cache write failed: %s", exc)


async def _try_acquire_refresh_lock(cookie_header: str) -> bool:
    if not _session_cache_enabled():
        return False
    try:
        client = await get_redis()
        return bool(await client.set(_session_cache_lock_key(cookie_header), "1", nx=True, ex=3))
    except Exception as exc:
        logger.debug("Central Auth session cache lock acquire failed: %s", exc)
        return False


async def _release_refresh_lock(cookie_header: str) -> None:
    if not _session_cache_enabled():
        return
    try:
        client = await get_redis()
        await client.delete(_session_cache_lock_key(cookie_header))
    except Exception as exc:
        logger.debug("Central Auth session cache lock release failed: %s", exc)


async def _wait_for_cached_session(cookie_header: str) -> Optional[LocalAdminSession]:
    for _ in range(40):
        await asyncio.sleep(0.05)
        l1_cached = await _load_l1_session(cookie_header)
        if l1_cached is not None:
            return l1_cached
        l1_stale = await _load_l1_session(cookie_header, allow_stale=True)
        if l1_stale is not None:
            return l1_stale
        cached = await _load_cached_session(cookie_header)
        if cached is not None:
            return cached
    return None


async def _refresh_session_from_upstream(cookie_header: str, base: str) -> Optional[LocalAdminSession]:
    try:
        client = await _get_profile_client(base)
        response = await client.get("/api/v1/profile", headers={"Cookie": cookie_header})
        if response.status_code != 200:
            logger.debug("Central Auth profile returned %d", response.status_code)
            return None

        parsed = parse_response(response, CentralAuthProfileResponse)
        if parsed and parsed.data is not None:
            if not parsed.data.isAdmin:
                return None
            parsed.data.deploymentId = parsed.data.deploymentId or LOCAL_DEPLOYMENT_ID
            parsed.data.role = "admin"
            parsed.data.team_ids = []
            await _store_cached_session(cookie_header, parsed.data)
            return parsed.data

        session = parse_response(response, LocalAdminSession)
        if session is not None and session.isAdmin:
            session.deploymentId = session.deploymentId or LOCAL_DEPLOYMENT_ID
            session.role = "admin"
            session.team_ids = []
            await _store_cached_session(cookie_header, session)
            return session
        return None
    except httpx.RequestError as exc:
        logger.warning("Central Auth profile request failed: %s", exc)
        await _reset_profile_client()
        return None


async def fetch_local_admin_session_from_cookie(cookie_header: str) -> Optional[LocalAdminSession]:
    base = _resolve_base_url()
    cookie_value = str(cookie_header or "").strip()
    if not base or not cookie_value:
        return None

    l1_cached = await _load_l1_session(cookie_value)
    if l1_cached is not None:
        return l1_cached
    l1_stale = await _load_l1_session(cookie_value, allow_stale=True)

    cached = await _load_cached_session(cookie_value)
    if cached is not None:
        return cached

    if l1_stale is not None:
        lock_acquired = await _try_acquire_refresh_lock(cookie_value)
        if not lock_acquired:
            return l1_stale
        try:
            refreshed = await _refresh_session_from_upstream(cookie_value, base)
            return refreshed or l1_stale
        finally:
            await _release_refresh_lock(cookie_value)

    lock_acquired = await _try_acquire_refresh_lock(cookie_value)
    if not lock_acquired:
        waited = await _wait_for_cached_session(cookie_value)
        if waited is not None:
            return waited

    try:
        return await _refresh_session_from_upstream(cookie_value, base)
    finally:
        if lock_acquired:
            await _release_refresh_lock(cookie_value)


__all__ = [
    "LOCAL_DEPLOYMENT_ID",
    "LocalAdminSession",
    "CentralAuthProfileResponse",
    "fetch_local_admin_session_from_cookie",
]
