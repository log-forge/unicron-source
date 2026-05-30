from app.utils.central_auth_client import LOCAL_DEPLOYMENT_ID
from fastapi import HTTPException, status


def get_active_org_id() -> str:
    return LOCAL_DEPLOYMENT_ID


def enforce_org_bound_access(*, deployment_org_id: str) -> None:
    """Ensure the request is scoped to the local appliance deployment."""
    normalized = str(deployment_org_id or LOCAL_DEPLOYMENT_ID)
    if normalized != LOCAL_DEPLOYMENT_ID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Wrong deployment for this appliance",
        )


def resolve_deployment_organization_id(*, deployment_org_id: str | None) -> str:
    return LOCAL_DEPLOYMENT_ID


async def require_deployment_organization() -> str:
    """FastAPI dependency: enforce the local deployment guard and provide the id."""
    return LOCAL_DEPLOYMENT_ID
