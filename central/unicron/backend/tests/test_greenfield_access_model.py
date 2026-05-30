import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from sqlmodel import SQLModel

from app.core.access.herald_visibility import list_visible_herald_ids
from app.core.access.role_resolver import (
    ActorContext,
    list_accessible_container_keys,
    resolve_container_role,
    resolve_group_role,
)
from app.core.deps.central_auth import require_admin_user
from app.core.deps.scope import get_actor_context
from app.models.container import Container
from app.models.group.crud.group_crud import list_groups
from app.models.group import Group
from app.models.notifications import AISettings
from app.utils.central_auth_client import LocalAdminSession


class _FakeScalarResult:
    def __init__(self, values):
        self._values = list(values)

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


class _FakeSession:
    def __init__(self, scalar_results):
        self._scalar_results = list(scalar_results)
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        if not self._scalar_results:
            raise AssertionError("Unexpected extra execute() call")
        return _FakeScalarResult(self._scalar_results.pop(0))


class GreenfieldAccessModelTests(unittest.IsolatedAsyncioTestCase):
    def test_bootstrap_metadata_has_grouping_without_access_grant_tables(self) -> None:
        # Ensure the relevant models are registered in SQLModel metadata.
        self.assertIsNotNone(Container)
        self.assertIsNotNone(Group)

        tables = SQLModel.metadata.tables
        self.assertIn("container", tables)
        self.assertIn("group", tables)
        self.assertIn("group_id", tables["container"].columns)

        grant_tables = [name for name in tables if "accessgrant" in name.lower()]
        self.assertEqual(grant_tables, [])

    def test_bootstrap_metadata_has_notification_ai_settings(self) -> None:
        self.assertIsNotNone(AISettings)

        table = AISettings.__table__
        self.assertEqual(table.schema, "notifications")
        self.assertEqual(table.name, "ai_settings")
        self.assertIn("notifications.ai_settings", SQLModel.metadata.tables)
        self.assertIn("organization_id", table.columns)
        self.assertIn("ollama_model", table.columns)

    def test_model_packages_do_not_export_access_grants(self) -> None:
        import app.models.container as container_models
        import app.models.group as group_models

        self.assertFalse(hasattr(container_models, "ContainerAccessGrant"))
        self.assertFalse(hasattr(group_models, "GroupAccessGrant"))
        self.assertIsNone(importlib.util.find_spec("app.models.container.container_access_grant_model"))
        self.assertIsNone(importlib.util.find_spec("app.models.group.group_access_grant_model"))

    def test_runtime_app_code_has_no_grant_model_or_crud_imports(self) -> None:
        app_root = Path(__file__).resolve().parents[1] / "app"
        patterns = (
            "ContainerAccessGrant",
            "GroupAccessGrant",
            "container_access_grant",
            "group_access_grant",
            "containeraccessgrant",
            "groupaccessgrant",
        )

        offenders = []
        for path in app_root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if any(pattern in text for pattern in patterns):
                offenders.append(str(path.relative_to(app_root)))

        self.assertEqual(offenders, [])

    async def test_actor_context_is_local_admin_with_no_teams(self) -> None:
        session = LocalAdminSession(user={"id": "admin-user", "username": "admin"})

        actor = await get_actor_context(session=session)

        self.assertEqual(actor.user_id, "admin-user")
        self.assertEqual(actor.team_ids, [])
        self.assertEqual(actor.org_role, "admin")

    async def test_unauthenticated_admin_dependency_fails(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await require_admin_user(session=LocalAdminSession(user=None))

        self.assertEqual(raised.exception.status_code, 401)

    async def test_local_admin_sees_all_container_keys(self) -> None:
        session = _FakeSession([["host-a:web", "host-b:api"]])
        actor = ActorContext(user_id="admin-user", team_ids=[], org_role="admin")

        self.assertEqual(await resolve_group_role(session, actor, "group-1"), "admin")
        self.assertEqual(await resolve_container_role(session, actor, "host-a:web"), "admin")
        self.assertEqual(
            await list_accessible_container_keys(session, actor),
            ["host-a:web", "host-b:api"],
        )
        self.assertIn("unregistered", str(session.executed[0]))

    async def test_local_admin_visibility_includes_all_groups_and_heralds(self) -> None:
        groups = [SimpleNamespace(id="group-1"), SimpleNamespace(id="group-2")]
        group_session = _FakeSession([groups])

        self.assertEqual(await list_groups(group_session), groups)

        herald_session = _FakeSession([["host-a", "host-b"]])

        actor = ActorContext(user_id="admin-user", team_ids=[], org_role="admin")
        self.assertEqual(await list_visible_herald_ids(herald_session, actor), ["host-a", "host-b"])
        self.assertIn("unregistered", str(herald_session.executed[0]))


if __name__ == "__main__":
    unittest.main()
