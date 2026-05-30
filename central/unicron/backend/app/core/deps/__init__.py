from .central_auth import get_central_auth_session, require_admin_user
from .deployment_org import enforce_org_bound_access, require_deployment_organization
from .deps import ensure_client_cert, get_socketio_server
from .herald import require_registered_herald
from .permissions import require_permission
from .scope import (
    enforce_container_access,
    enforce_group_access,
    get_actor_context,
    require_container_access,
    require_group_access,
)
from .spiffe import require_spiffe_common_name  # socket variants
from .spiffe import (
    require_spiffe_common_name_socket,
    require_spiffe_id,
    require_spiffe_id_socket,
    require_spiffe_pair,
    require_spiffe_pair_socket,
)

__all__ = [
    # General dependencies
    "get_socketio_server",
    "ensure_client_cert",
    "require_registered_herald",
    "get_actor_context",
    "require_group_access",
    "enforce_group_access",
    "require_container_access",
    "enforce_container_access",
    "get_central_auth_session",
    "require_admin_user",
    "require_permission",
    "enforce_org_bound_access",
    "require_deployment_organization",
    # SPIFFE helpers
    "require_spiffe_id",
    "require_spiffe_common_name",
    "require_spiffe_pair",
    "require_spiffe_pair_socket",
    "require_spiffe_id_socket",
    "require_spiffe_common_name_socket",
]
