from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.database import get_session
from app.core.deps.deps import require_bearer_token
from app.core.logging import get_logger
from app.models.herald.crud.herald_token_crud import get_herald_token
from app.services.agent_registry import get_agent_registry
from app.routes.security.pki.schemas import CertResponse, CSRRequest, RootCAResponse
from app.utils.pki.cert_utils import coerce_not_after_seconds, sign_csr
from app.utils.pki.ca_fingerprint import CARootUnavailable, read_root_ca_pem
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

router = APIRouter()


@router.get("/ca/root", response_model=RootCAResponse)
async def get_root_ca() -> RootCAResponse:
    try:
        root_pem = read_root_ca_pem()
    except CARootUnavailable as e:
        logger.error(
            "Failed to read root CA",
            extra={"checked_paths": e.checked_paths},
            exc_info=True,
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Root CA unavailable") from e
    return RootCAResponse(root_ca_pem=root_pem)


@router.post("/cert/bootstrap", response_model=CertResponse)
async def cert_bootstrap(
    body: CSRRequest,
    session: AsyncSession = Depends(get_session),
    token: str = Depends(require_bearer_token),
):
    herald_token = await get_herald_token(session, token)
    expiry_time = datetime.now(timezone.utc) - timedelta(seconds=settings.TOKEN_EXPIRY_SECONDS)
    if not herald_token or herald_token.status != "pending" or herald_token.created_at < expiry_time:
        logger.error("Invalid or expired enroll token during cert bootstrap")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired enroll token, generate a new herald token",
        )

    tags = {str(tag).lower() for tag in (herald_token.tags or [])}
    # go-streamer enrollment tokens are keyed by token id, but CSR identity is streamer/<agent_name>.
    if "go-streamer" in tags:
        expected_spiffe_uris = [f"spiffe://unicron/streamer/{herald_token.herald_name}"]
    else:
        expected_spiffe_uris = [f"spiffe://unicron/herald/{herald_token.id}"]

    not_after_seconds = coerce_not_after_seconds(body.not_after_seconds)
    cert_pem, chain_pem, not_after = sign_csr(
        csr_pem=body.csr_pem,
        not_after_seconds=not_after_seconds,
        expected_spiffe_uris=expected_spiffe_uris,
    )

    # Fresh bootstrap proves possession of a new enrollment token and cert, so
    # host-level revocation can be cleared. Registration remains the point that
    # reactivates any durable decommissioned Herald row after admission checks.
    host_id = herald_token.herald_name if "go-streamer" in tags else herald_token.id
    registry = get_agent_registry()
    await registry.unrevoke(host_id, reason="Fresh bootstrap certificate issued")

    # Mark token as consumed after successful bootstrap (prevents reuse - RMOT-03)
    herald_token.status = "consumed"
    await session.commit()
    logger.info("Bootstrap certificate issued and token consumed", extra={"host_id": host_id})

    return CertResponse(cert_pem=cert_pem, chain_pem=chain_pem, not_after=not_after)
