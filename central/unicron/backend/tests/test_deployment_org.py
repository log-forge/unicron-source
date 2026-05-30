import unittest

from fastapi import HTTPException

from app.core.deps.deployment_org import (
    enforce_org_bound_access,
    get_active_org_id,
    require_deployment_organization,
    resolve_deployment_organization_id,
)


class DeploymentOrganizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_unbound_runtime_uses_local_deployment(self) -> None:
        org_id = await require_deployment_organization()

        self.assertEqual(org_id, "local")

    async def test_runtime_org_id_does_not_change_local_deployment(self) -> None:
        org_id = await require_deployment_organization()

        self.assertEqual(org_id, "local")

    def test_unbound_socket_context_uses_local_deployment(self) -> None:
        org_id = resolve_deployment_organization_id(deployment_org_id="")

        self.assertEqual(org_id, "local")

    def test_bound_local_deployment_is_allowed(self) -> None:
        org_id = resolve_deployment_organization_id(deployment_org_id="local")

        self.assertEqual(org_id, "local")

    def test_bound_external_deployment_resolves_to_local(self) -> None:
        org_id = resolve_deployment_organization_id(deployment_org_id="org-from-runtime")

        self.assertEqual(org_id, "local")

    def test_bound_deployment_rejects_non_local_value(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            enforce_org_bound_access(deployment_org_id="org-deployment")

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.detail, "Wrong deployment for this appliance")

    def test_active_org_is_local(self) -> None:
        self.assertEqual(get_active_org_id(), "local")


if __name__ == "__main__":
    unittest.main()
