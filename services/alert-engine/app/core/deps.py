"""Authentication dependencies for alert-engine service.

Alert-engine validates browser sessions directly against Central Auth. This
service doesn't have its own user database.
"""

import asyncio
import hashlib
import hmac
from time import monotonic
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger("alert-engine.deps")

_CACHE_VERSION = "v2"
_L1_MAX_ENTRIES = 4096
_l1_cache: dict[str, tuple[float, float, "UserContext"]] = {}
_l1_cache_lock = asyncio.Lock()
_central_auth_client: Optional[httpx.AsyncClient] = None
_central_auth_client_base = ""
_central_auth_client_verify: Optional[bool] = None
_central_auth_client_lock = asyncio.Lock()

class UserContext(BaseModel):
    """Authenticated user context from Central session."""

    user_id: str
    email: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    organization_id: str
    roles: list[str] = []


def _cache_enabled() -> bool:
    return (
        settings.CENTRAL_SESSION_CACHE_ENABLED
        and int(settings.CENTRAL_SESSION_CACHE_TTL_SECONDS) > 0
    )


def _l1_cache_enabled() -> bool:
    return (
        settings.CENTRAL_SESSION_L1_CACHE_ENABLED
        and int(settings.CENTRAL_SESSION_L1_CACHE_TTL_SECONDS) > 0
    )


def _cache_key(token: str) -> str:
    prefix = (settings.CENTRAL_SESSION_CACHE_PREFIX or "").strip() or "unicron:auth:central_session"
    # Use HMAC so Redis keys never contain raw cookie headers.
    secret = (settings.CENTRAL_INTERNAL_SECRET or "alert-engine-session-cache").encode("utf-8")
    digest = hmac.new(secret, token.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{prefix}:{_CACHE_VERSION}:{digest}"


def _cache_lock_key(token: str) -> str:
    return f"{_cache_key(token)}:refresh-lock"


async def _load_l1_user_context(token: str, *, allow_stale: bool = False) -> Optional[UserContext]:
    if not _l1_cache_enabled():
        return None
    key = _cache_key(token)
    entry = _l1_cache.get(key)
    if entry is None:
        return None
    fresh_until, stale_until, user_context = entry
    now = monotonic()
    if fresh_until > now:
        return user_context
    if allow_stale and stale_until > now:
        return user_context
    _l1_cache.pop(key, None)
    return None


async def _store_l1_user_context(token: str, user: UserContext) -> None:
    if not _l1_cache_enabled():
        return
    ttl = max(1, int(settings.CENTRAL_SESSION_L1_CACHE_TTL_SECONDS))
    stale_grace = max(0, int(settings.CENTRAL_SESSION_L1_STALE_GRACE_SECONDS))
    key = _cache_key(token)
    async with _l1_cache_lock:
        now = monotonic()
        _l1_cache[key] = (now + ttl, now + ttl + stale_grace, user)
        if len(_l1_cache) <= _L1_MAX_ENTRIES:
            return
        stale_keys = [k for k, (_fresh_until, stale_until, _) in _l1_cache.items() if stale_until <= now]
        for stale_key in stale_keys:
            _l1_cache.pop(stale_key, None)
        while len(_l1_cache) > _L1_MAX_ENTRIES:
            oldest_key = next(iter(_l1_cache))
            _l1_cache.pop(oldest_key, None)


async def _get_central_auth_client() -> httpx.AsyncClient:
    global _central_auth_client, _central_auth_client_base, _central_auth_client_verify
    base = settings.CENTRAL_AUTH_BASE_URL.rstrip("/")
    verify = bool(settings.CENTRAL_AUTH_VERIFY_TLS)
    async with _central_auth_client_lock:
        if (
            _central_auth_client is not None
            and _central_auth_client_base == base
            and _central_auth_client_verify == verify
        ):
            return _central_auth_client

        if _central_auth_client is not None:
            await _central_auth_client.aclose()
            _central_auth_client = None

        _central_auth_client = httpx.AsyncClient(
            base_url=base,
            verify=verify,
            timeout=10.0,
        )
        _central_auth_client_base = base
        _central_auth_client_verify = verify
        return _central_auth_client


async def _reset_central_auth_client() -> None:
    global _central_auth_client, _central_auth_client_base, _central_auth_client_verify
    async with _central_auth_client_lock:
        if _central_auth_client is not None:
            await _central_auth_client.aclose()
        _central_auth_client = None
        _central_auth_client_base = ""
        _central_auth_client_verify = None


async def _load_cached_user_context(token: str) -> Optional[UserContext]:
    if not _cache_enabled():
        return None
    try:
        redis = await get_redis()
        payload = await redis.get(_cache_key(token))
    except Exception as exc:
        logger.debug("Session cache read failed: %s", exc)
        return None

    if not payload:
        return None

    try:
        user = UserContext.model_validate_json(payload)
        await _store_l1_user_context(token, user)
        return user
    except Exception as exc:
        logger.warning("Session cache parse failed, evicting key: %s", exc)
        try:
            await redis.delete(_cache_key(token))
        except Exception:
            pass
        return None


async def _store_cached_user_context(token: str, user: UserContext) -> None:
    await _store_l1_user_context(token, user)
    if not _cache_enabled():
        return

    ttl = max(1, int(settings.CENTRAL_SESSION_CACHE_TTL_SECONDS))
    try:
        redis = await get_redis()
        await redis.set(_cache_key(token), user.model_dump_json(), ex=ttl)
    except Exception as exc:
        logger.debug("Session cache write failed: %s", exc)


async def _try_acquire_refresh_lock(token: str) -> bool:
    if not _cache_enabled():
        return False
    try:
        redis = await get_redis()
        return bool(await redis.set(_cache_lock_key(token), "1", nx=True, ex=3))
    except Exception as exc:
        logger.debug("Session cache lock acquire failed: %s", exc)
        return False


async def _release_refresh_lock(token: str) -> None:
    if not _cache_enabled():
        return
    try:
        redis = await get_redis()
        await redis.delete(_cache_lock_key(token))
    except Exception as exc:
        logger.debug("Session cache lock release failed: %s", exc)


async def _wait_for_cached_user_context(token: str) -> Optional[UserContext]:
    for _ in range(40):
        await asyncio.sleep(0.05)
        l1_cached = await _load_l1_user_context(token)
        if l1_cached is not None:
            return l1_cached
        l1_stale = await _load_l1_user_context(token, allow_stale=True)
        if l1_stale is not None:
            return l1_stale
        cached = await _load_cached_user_context(token)
        if cached is not None:
            return cached
    return None


async def _refresh_user_context_from_upstream(cookie_header: str) -> Optional[UserContext]:
    try:
        client = await _get_central_auth_client()
        resp = await client.get(
            "/api/v1/profile",
            headers={"Cookie": cookie_header},
        )
        if resp.status_code != 200:
            logger.debug("Central Auth profile returned %d", resp.status_code)
            return None

        data = resp.json().get("data", {})
        user_data = data.get("user", {})
        user_id = str(user_data.get("id") or "")
        username = str(
            user_data.get("username")
            or user_data.get("displayUsername")
            or user_data.get("name")
            or ""
        )
        if not user_id:
            return None
        user_context = UserContext(
            user_id=user_id,
            email=username,
            username=username,
            display_name=str(user_data.get("displayUsername") or user_data.get("name") or username),
            organization_id=str(data.get("deploymentId") or "local"),
            roles=["admin"],
        )
        await _store_cached_user_context(cookie_header, user_context)
        return user_context
    except httpx.RequestError as e:
        logger.warning("Central Auth profile request failed: %s", e)
        await _reset_central_auth_client()
        return None
    except (KeyError, ValueError) as e:
        logger.warning("Central Auth profile response parse error: %s", e)
        return None


async def get_user_context(request: Request) -> Optional[UserContext]:
    """
    Validate session by calling Central Auth with the incoming cookie header.

    Returns None if authentication fails (no valid session).
    """
    cookie_header = request.headers.get("cookie", "")
    if not cookie_header:
        return None

    l1_cached = await _load_l1_user_context(cookie_header)
    if l1_cached is not None:
        return l1_cached
    l1_stale = await _load_l1_user_context(cookie_header, allow_stale=True)

    cached = await _load_cached_user_context(cookie_header)
    if cached is not None:
        return cached

    if l1_stale is not None:
        lock_acquired = await _try_acquire_refresh_lock(cookie_header)
        if not lock_acquired:
            return l1_stale
        try:
            refreshed = await _refresh_user_context_from_upstream(cookie_header)
            return refreshed or l1_stale
        finally:
            await _release_refresh_lock(cookie_header)

    lock_acquired = await _try_acquire_refresh_lock(cookie_header)
    if not lock_acquired:
        waited = await _wait_for_cached_user_context(cookie_header)
        if waited is not None:
            return waited

    try:
        return await _refresh_user_context_from_upstream(cookie_header)
    finally:
        if lock_acquired:
            await _release_refresh_lock(cookie_header)


async def require_authenticated_user(
    request: Request,
    user: Optional[UserContext] = Depends(get_user_context),
) -> UserContext:
    """
    Require authenticated user or raise 401.

    Use as a dependency in protected routes:
        @router.get("/rules")
        async def list_rules(user: UserContext = Depends(require_authenticated_user)):
            ...
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


async def require_admin_or_above(
    user: UserContext = Depends(require_authenticated_user),
) -> UserContext:
    """
    Require user with admin role or above.

    Use for admin-only endpoints:
        @router.post("/templates/activate")
        async def activate_template(user: UserContext = Depends(require_admin_or_above)):
            ...
    """
    admin_roles = {"admin", "super_admin", "org_admin"}
    if not any(role in admin_roles for role in user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


__all__ = [
    "UserContext",
    "get_user_context",
    "require_authenticated_user",
    "require_admin_or_above",
]
