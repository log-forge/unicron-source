from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping, Sequence
from urllib.parse import urlsplit

from app.core.config import settings
from app.core.logging import get_logger
from app.models.settings.origin_policy_config_model import OriginPolicyConfig
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("backend.core.origin_policy")

OriginPolicySource = Literal["env", "env+db", "db", "default"]


@dataclass(frozen=True)
class OriginPolicySnapshot:
    effective_allowed_origins: tuple[str, ...]
    stored_allowed_origins: tuple[str, ...]
    source: OriginPolicySource
    env_managed: bool
    same_origin_only: bool
    protected_allowed_origins: tuple[str, ...] = ()
    ui_editable: bool = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "effective_allowed_origins": list(self.effective_allowed_origins),
            "stored_allowed_origins": list(self.stored_allowed_origins),
            "protected_allowed_origins": list(self.protected_allowed_origins),
            "origin_policy_source": self.source,
            "origin_policy_managed_by_env": self.env_managed,
            "origin_policy_ui_editable": self.ui_editable,
            "origin_policy_same_origin_only": self.same_origin_only,
        }


_CURRENT_POLICY = OriginPolicySnapshot(
    effective_allowed_origins=(),
    stored_allowed_origins=(),
    protected_allowed_origins=(),
    source="default",
    env_managed=False,
    ui_editable=True,
    same_origin_only=True,
)


def _first_csv_token(value: str | None) -> str | None:
    if not value:
        return None
    token = value.split(",")[0].strip()
    return token or None


def _normalize_forwarded_scheme(value: str | None) -> str | None:
    token = (_first_csv_token(value) or "").lower()
    if token == "wss":
        return "https"
    if token == "ws":
        return "http"
    if token in {"http", "https"}:
        return token
    return None


def normalize_origin(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None

    parsed = urlsplit(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None
    if parsed.path not in {"", "/"}:
        return None
    if parsed.query or parsed.fragment:
        return None

    host = parsed.hostname
    if not host:
        return None
    host = host.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    try:
        port = parsed.port
    except ValueError:
        return None
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None

    host_port = f"{host}:{port}" if port else host
    return f"{scheme}://{host_port}"


def normalize_origin_list(values: Iterable[str]) -> tuple[list[str], list[str]]:
    cleaned: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()

    for value in values:
        token = (value or "").strip()
        if not token:
            continue
        normalized = normalize_origin(token)
        if not normalized:
            invalid.append(token)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)

    return cleaned, invalid


def parse_origin_csv(value: str | None) -> tuple[list[str], list[str]]:
    if not value:
        return [], []
    tokens = []
    for chunk in value.split(","):
        tokens.extend(chunk.splitlines())
    return normalize_origin_list(tokens)


def _merge_origin_lists(*origin_lists: Iterable[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for origin_list in origin_lists:
        for origin in origin_list:
            if origin in seen:
                continue
            seen.add(origin)
            merged.append(origin)
    return merged


def protected_env_origins() -> tuple[list[str], list[str], bool]:
    env_raw = (settings.UNICRON_ALLOWED_ORIGINS or "").strip()
    legacy_raw = (settings.CORS_ORIGINS or "").strip()
    env_tokens_raw = env_raw or legacy_raw
    env_allowed, env_invalid = parse_origin_csv(env_tokens_raw)
    return env_allowed, env_invalid, bool(env_tokens_raw)


def filter_ui_managed_origins(
    origins: Iterable[str],
    protected_origins: Iterable[str],
) -> list[str]:
    protected = set(protected_origins)
    return [origin for origin in origins if origin not in protected]


def derive_request_origin(request: Request) -> str | None:
    proto = _first_csv_token(request.headers.get("x-forwarded-proto")) or request.url.scheme
    host = (
        _first_csv_token(request.headers.get("x-forwarded-host"))
        or _first_csv_token(request.headers.get("host"))
        or request.url.netloc
    )
    if not proto or not host:
        return None
    return normalize_origin(f"{proto}://{host}")


def derive_socket_origin(environ: Mapping[str, Any]) -> str | None:
    proto = _normalize_forwarded_scheme(str(environ.get("HTTP_X_FORWARDED_PROTO", "")))
    if not proto:
        origin_header = str(environ.get("HTTP_ORIGIN", "")).strip()
        normalized_origin = normalize_origin(origin_header) if origin_header else None
        if normalized_origin:
            proto = urlsplit(normalized_origin).scheme
    if not proto:
        proto = _normalize_forwarded_scheme(str(environ.get("wsgi.url_scheme", "")))
    host = _first_csv_token(str(environ.get("HTTP_X_FORWARDED_HOST", ""))) or _first_csv_token(
        str(environ.get("HTTP_HOST", ""))
    )

    if not host:
        server_name = str(environ.get("SERVER_NAME", "")).strip()
        server_port = str(environ.get("SERVER_PORT", "")).strip()
        if server_name:
            host = f"{server_name}:{server_port}" if server_port else server_name

    if not proto or not host:
        return None
    return normalize_origin(f"{proto}://{host}")


def get_origin_policy() -> OriginPolicySnapshot:
    return _CURRENT_POLICY


def set_origin_policy(snapshot: OriginPolicySnapshot) -> OriginPolicySnapshot:
    global _CURRENT_POLICY
    _CURRENT_POLICY = snapshot
    return _CURRENT_POLICY


def _is_missing_table_error(exc: ProgrammingError, table_name: str) -> bool:
    target = table_name.lower()
    orig = getattr(exc, "orig", None)
    if orig is not None:
        if orig.__class__.__name__ == "UndefinedTableError":
            return True
        message = str(orig).lower()
        if f'relation "{target}" does not exist' in message:
            return True
    return f'relation "{target}" does not exist' in str(exc).lower()


async def resolve_origin_policy(session: AsyncSession) -> OriginPolicySnapshot:
    env_allowed, env_invalid, env_configured = protected_env_origins()
    if env_invalid:
        logger.warning("Ignoring invalid origins from environment: %s", env_invalid)

    stored_allowed: list[str] = []
    try:
        result = await session.execute(select(OriginPolicyConfig).limit(1))
        cfg = result.scalars().first()
        stored_allowed, stored_invalid = normalize_origin_list((cfg.allowed_origins if cfg else []) or [])
        if stored_invalid:
            logger.warning("Ignoring invalid stored origins in DB config: %s", stored_invalid)
    except ProgrammingError as exc:
        if not _is_missing_table_error(exc, "originpolicyconfig"):
            raise
        logger.warning(
            "OriginPolicyConfig table is not available yet; using env/default origin policy until migrations complete."
        )

    stored_additions = filter_ui_managed_origins(stored_allowed, env_allowed)

    if env_configured and not settings.UNICRON_ALLOW_UI_ORIGIN_ADDITIONS:
        return OriginPolicySnapshot(
            effective_allowed_origins=tuple(env_allowed),
            stored_allowed_origins=tuple(stored_additions),
            protected_allowed_origins=tuple(env_allowed),
            source="env",
            env_managed=True,
            ui_editable=False,
            same_origin_only=not env_allowed,
        )

    if env_allowed:
        effective = _merge_origin_lists(env_allowed, stored_additions)
        return OriginPolicySnapshot(
            effective_allowed_origins=tuple(effective),
            stored_allowed_origins=tuple(stored_additions),
            protected_allowed_origins=tuple(env_allowed),
            source="env+db" if stored_additions else "env",
            env_managed=False,
            ui_editable=True,
            same_origin_only=not effective,
        )

    if stored_allowed:
        return OriginPolicySnapshot(
            effective_allowed_origins=tuple(stored_allowed),
            stored_allowed_origins=tuple(stored_allowed),
            protected_allowed_origins=(),
            source="db",
            env_managed=False,
            ui_editable=True,
            same_origin_only=False,
        )

    return OriginPolicySnapshot(
        effective_allowed_origins=(),
        stored_allowed_origins=(),
        protected_allowed_origins=(),
        source="default",
        env_managed=False,
        ui_editable=True,
        same_origin_only=True,
    )


async def refresh_origin_policy(session: AsyncSession) -> OriginPolicySnapshot:
    snapshot = await resolve_origin_policy(session)
    set_origin_policy(snapshot)
    return snapshot


def _matches_effective(origin: str, effective_allowed_origins: Sequence[str]) -> bool:
    return origin in effective_allowed_origins


def _is_local_dev_origin(origin: str) -> bool:
    parsed = urlsplit(origin)
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    if host.endswith(".localhost") or host.endswith(".localtest.me"):
        return True
    return False


def is_http_origin_allowed(origin_header: str | None, request: Request) -> bool:
    if not origin_header:
        return True

    origin = normalize_origin(origin_header)
    if not origin:
        return False

    policy = get_origin_policy()
    if policy.effective_allowed_origins:
        return _matches_effective(origin, policy.effective_allowed_origins)

    request_origin = derive_request_origin(request)
    if request_origin and origin == request_origin:
        return True
    if settings.ENVIRONMENT != "production" and _is_local_dev_origin(origin):
        return True
    return False


def is_socket_origin_allowed(origin_header: str | None, environ: Mapping[str, Any]) -> bool:
    if not origin_header:
        return True

    origin = normalize_origin(origin_header)
    if not origin:
        return False

    policy = get_origin_policy()
    if policy.effective_allowed_origins:
        return _matches_effective(origin, policy.effective_allowed_origins)

    socket_origin = derive_socket_origin(environ)
    if socket_origin and origin == socket_origin:
        return True
    if settings.ENVIRONMENT != "production" and _is_local_dev_origin(origin):
        return True
    return False


def build_cors_headers(
    origin_header: str,
    *,
    request_headers: str | None = None,
    preflight: bool = False,
) -> dict[str, str]:
    normalized = normalize_origin(origin_header)
    if not normalized:
        return {}

    headers: dict[str, str] = {
        "Access-Control-Allow-Origin": normalized,
        "Vary": "Origin",
    }

    if settings.CORS_ALLOW_CREDENTIALS:
        headers["Access-Control-Allow-Credentials"] = "true"

    if preflight:
        headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
        headers["Access-Control-Max-Age"] = str(int(settings.CORS_MAX_AGE))
        headers["Access-Control-Allow-Headers"] = request_headers or "Authorization,Content-Type,X-CSRF-Token"

    return headers


__all__ = [
    "OriginPolicySnapshot",
    "build_cors_headers",
    "derive_request_origin",
    "filter_ui_managed_origins",
    "get_origin_policy",
    "is_http_origin_allowed",
    "is_socket_origin_allowed",
    "normalize_origin",
    "normalize_origin_list",
    "parse_origin_csv",
    "protected_env_origins",
    "refresh_origin_policy",
    "set_origin_policy",
]
