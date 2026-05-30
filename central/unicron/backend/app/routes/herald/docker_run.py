import re
import uuid

from app.core.config import settings
from app.core.database import get_session
from app.core.deps import require_permission
from app.core.logging import get_logger
from app.models.herald.crud.herald_token_crud import create_herald_token
from app.routes.herald.schemas import DockerRunRequest, DockerRunResponse
from app.utils.pki.ca_fingerprint import CAFingerprintUnavailable, read_ca_fingerprint
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/docker-run",
    response_model=DockerRunResponse,
    dependencies=[Depends(require_permission({"herald": ["update"]}))],
)
async def docker_run(
    body: DockerRunRequest,
    session: AsyncSession = Depends(get_session),
):
    try:
        herald_id = uuid.uuid4().hex
        herald_name = body.herald_name or f"herald-{herald_id}"
        central_url = body.central_url or f"https://{settings.UNICRON_CENTRAL_FQDN}"

        herald_token = await create_herald_token(
            session,
            organization_id="local",
            herald_name=herald_name,
            herald_id=herald_id,
            central_url=central_url,
        )

        # Accept comma-separated SANs with or without spaces
        herald_cert_subjects = body.herald_cert_subjects or "localhost, 127.0.0.1, host.docker.internal"
        spiffe_id = f"spiffe://unicron/herald/{herald_id}"
        spiffe_cn = f"spiffe://unicron/herald/herald-{herald_id}"
        herald_cert_subjects = f"unicron.central, {herald_cert_subjects}, herald-{herald_id}, {spiffe_id}, {spiffe_cn}"

        herald_port = body.herald_port or 9443
        central_mtls_port = int(settings.UNICRON_CENTRAL_MTLS_PORT) or 8443

        herald_cors_origins = (settings.HERALD_CORS_ORIGINS or "").strip()
        herald_cors_origin_regex = (settings.HERALD_CORS_ORIGIN_REGEX or "").strip()
        if not herald_cors_origin_regex:
            herald_cors_origin_regex = r"^https?://.+$"
        herald_cors_allow_credentials = "true" if settings.HERALD_CORS_ALLOW_CREDENTIALS else "false"
        herald_cors_max_age = int(settings.HERALD_CORS_MAX_AGE)

        try:
            # Prepare SANs for the token
            # Split on commas with optional surrounding whitespace
            herald_sans = [s.strip() for s in re.split(r"\s*,\s*", herald_cert_subjects) if s.strip()]
            seen: set[str] = set()
            deduped: list[str] = []
            for s in herald_sans:
                if s not in seen:
                    seen.add(s)
                    deduped.append(s)
            herald_sans = deduped
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to process SANs: {e}")

        # Read CA fingerprint for TOFU verification.
        try:
            ca_fingerprint = read_ca_fingerprint()
        except CAFingerprintUnavailable as e:
            logger.error(
                "Failed to read CA fingerprint",
                extra={"checked_paths": e.checked_paths},
                exc_info=True,
            )
            raise HTTPException(status_code=500, detail="CA fingerprint unavailable") from e

        selinux_suffix = ":ro,Z" if body.selinux_relabel else ":ro"

        cmd = (
            f"docker run -d --name herald-{herald_id} "
            f"--restart=unless-stopped "
            f"--privileged "
            f"--pid=host "  # allow OTel hostmetrics 'process' scraper to see host PIDs
            f"-p {herald_port}:{herald_port} "
            f"-v /var/run/docker.sock:/var/run/docker.sock:ro "
            f"-v /var/lib/docker/containers:/var/lib/docker/containers:ro "
            f"-v /proc:/host/proc{selinux_suffix} "
            f"-v /sys:/host/sys{selinux_suffix} "
            f"-v /:/host/root{selinux_suffix} "
            f"-v herald-{herald_id}-data:/herald-data "
            f"-e DOCKER_ENDPOINT=unix:///var/run/docker.sock "
            f"-e HOST_PROC=/host/proc "
            f"-e HOST_SYS=/host/sys "
            f"-e HOST_ROOT=/host/root "
            f"-e ENVIRONMENT=production "
            f"-e PING_INTERVAL={body.check_in_interval or 60} "
            f"-e INVENTORY_INTERVAL={300} "
            f"-e CA_FINGERPRINT='{ca_fingerprint}' "
            f"-e HERALD_ENROLL_TOKEN='{herald_token.id}' "
            f"-e HERALD_ID={herald_id} "
            f"-e HERALD_NAME={herald_name} "
            f"-e HERALD_PORT={herald_port} "
            f"-e HERALD_CERT_SUBJECTS='{herald_cert_subjects}' "
            f"-e HERALD_CERT_NOT_AFTER_SECONDS={43200} "  # 12 hours
            f"-e HERALD_CERT_RENEW_EXPIRES_IN_SECONDS={3600} "  # 60 minutes
            f"-e HERALD_CORS_ORIGINS='{herald_cors_origins}' "
            f"-e HERALD_CORS_ORIGIN_REGEX='{herald_cors_origin_regex}' "
            f"-e HERALD_CORS_ALLOW_CREDENTIALS='{herald_cors_allow_credentials}' "
            f"-e HERALD_CORS_MAX_AGE='{herald_cors_max_age}' "
            f"-e CENTRAL_URL={central_url} "
            f"-e CENTRAL_MTLS_URL={central_url}:{central_mtls_port} "
            f"-e API_BASE_URL='{settings.API_BASE_URL}' "
            f"-e UNICRON_CENTRAL_FQDN='{settings.UNICRON_CENTRAL_FQDN}' "
            f"registry:5000/unicron-herald:latest"
        )

        return DockerRunResponse(ok=True, command=cmd, herald_name=body.herald_name, herald_id=herald_token.id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating docker run command: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate docker command: {e}")
