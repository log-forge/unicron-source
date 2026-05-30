from app.core.database import get_session
from app.core.deps import require_spiffe_id
from app.core.deps.spiffe import get_spiffe_cert_metadata
from app.core.logging import get_logger
from app.models.herald.crud.herald_crud import get_herald
from app.services.agent_registry import get_agent_registry
from app.utils.pki.cert_utils import coerce_not_after_seconds, sign_csr
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import CertResponse, CSRRequest

logger = get_logger(__name__)

router = APIRouter()


@router.post("/cert/sign", response_model=CertResponse)
async def cert_sign(
    body: CSRRequest,
    request: Request,
    herald_id: str = Depends(require_spiffe_id),
    session: AsyncSession = Depends(get_session),
):
    cert_meta = get_spiffe_cert_metadata(request)
    if cert_meta is not None:
        cert_fingerprint_sha256, cert_serial_hex = cert_meta
        registry = get_agent_registry()
        if await registry.is_cert_revoked(
            cert_fingerprint_sha256=cert_fingerprint_sha256,
            cert_serial_hex=cert_serial_hex,
        ):
            logger.warning("Rejected cert/sign for revoked client certificate", extra={"herald_id": herald_id})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Client certificate revoked")

    herald = await get_herald(session, herald_id)
    if not herald or getattr(herald, "unregistered", False):
        logger.warning(f"Herald {herald_id} attempted to sign cert but is not registered")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Herald not registered")

    not_after_seconds = coerce_not_after_seconds(body.not_after_seconds)
    cert_pem, chain_pem, not_after = sign_csr(
        csr_pem=body.csr_pem,
        not_after_seconds=not_after_seconds,
        expected_spiffe_uris=[
            f"spiffe://unicron/herald/{herald_id}",
            f"spiffe://unicron/streamer/{herald_id}",
        ],
    )
    return CertResponse(cert_pem=cert_pem, chain_pem=chain_pem, not_after=not_after)
