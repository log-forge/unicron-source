from typing import Mapping, Optional, Sequence

from app.core.deps.central_auth import require_admin_user
from app.utils.central_auth_client import LocalAdminSession
from fastapi import Depends

PermissionShape = Mapping[str, Sequence[str]]


def require_permission(permissions: PermissionShape, *, organization_id: Optional[str] = None):
    async def _require_permission(
        session: LocalAdminSession = Depends(require_admin_user),
    ) -> LocalAdminSession:
        return session

    return _require_permission


__all__ = ["PermissionShape", "require_permission"]
