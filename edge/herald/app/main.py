import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse
from starlette.middleware.cors import CORSMiddleware

from .core.config import settings
from .socket.mtls_tunnel import open_control_channel, stop_control_channel
from .tasks import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    # start the Herald control channel as a background task
    control_task = asyncio.create_task(open_control_channel())
    try:
        yield
    finally:
        # graceful shutdown: stop control channel cleanly
        await stop_control_channel(control_task)


app = FastAPI(
    title="Herald",
    default_response_class=ORJSONResponse,
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

"""
CORS configuration (Herald)

Self-host friendly behavior:
- If HERALD_CORS_ORIGINS is set (comma-separated), only those exact origins are allowed.
- Else if HERALD_CORS_ORIGIN_REGEX is set, any origin matching the regex is allowed.
- Else default to a permissive regex that reflects any http/https Origin (credentials-compatible).
"""

raw_origins = (settings.HERALD_CORS_ORIGINS or "").strip()
allow_origins: list[str] = []
if raw_origins:
    allow_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

allow_origin_regex = (settings.HERALD_CORS_ORIGIN_REGEX or "").strip()
if not allow_origins and not allow_origin_regex:
    allow_origin_regex = r"^https?://.+$"

allow_credentials = bool(settings.HERALD_CORS_ALLOW_CREDENTIALS)
max_age = int(settings.HERALD_CORS_MAX_AGE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=max_age,
)


@app.get("/status")
def status():
    return {
        "herald_id": settings.HERALD_ID,
        "herald_name": settings.HERALD_NAME,
        "central_mtls_url": settings.CENTRAL_MTLS_URL,
        "herald_cert_subjects": settings.HERALD_CERT_SUBJECTS,
        "ok": True,
    }


@app.middleware("http")
async def secure_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
        }
    )
    return resp


@app.middleware("http")
async def enforce_mtls(request: Request, call_next):
    # List of paths that do NOT require mTLS
    exceptions = ["/status", "/health", "/ping"]
    if not any(request.url.path.startswith(exc) for exc in exceptions):
        ssl_obj = request.scope.get("ssl_object")
        if not ssl_obj or not ssl_obj.getpeercert():
            return ORJSONResponse({"detail": "mTLS client certificate required"}, status_code=401)
    return await call_next(request)
