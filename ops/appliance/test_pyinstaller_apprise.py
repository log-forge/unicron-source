from __future__ import annotations

import ast
import pathlib
import pkgutil
import unittest


DOCKERFILE_PATH = pathlib.Path(__file__).with_name("Dockerfile")
NOTIFIER_WORKER_ENTRYPOINT_PATH = (
    pathlib.Path(__file__).with_name("python-entrypoints") / "notifier_worker.py"
)
BACKEND_MIGRATE_ENTRYPOINT_PATH = (
    pathlib.Path(__file__).with_name("python-entrypoints") / "backend_migrate.py"
)
BACKEND_APP_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "central" / "unicron" / "backend" / "app"
)


def _pyinstaller_command(dockerfile: str, binary_name: str) -> str:
    name_marker = f"--name {binary_name}"
    name_index = dockerfile.find(name_marker)
    if name_index == -1:
        raise AssertionError(f"missing PyInstaller command for {binary_name}")

    command_start = dockerfile.rfind("pyinstaller ", 0, name_index)
    if command_start == -1:
        raise AssertionError(f"missing PyInstaller command start for {binary_name}")

    next_command = dockerfile.find("\n    pyinstaller ", name_index)
    next_stage = dockerfile.find("\n\nFROM ", name_index)
    candidates = [index for index in (next_command, next_stage) if index != -1]
    command_end = min(candidates) if candidates else len(dockerfile)
    return dockerfile[command_start:command_end]


class PyInstallerApprisePackagingTests(unittest.TestCase):
    def test_notifier_binaries_collect_all_apprise_package_files(self) -> None:
        dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")

        for binary_name in ("notifier-api", "notifier-worker"):
            with self.subTest(binary_name=binary_name):
                command = _pyinstaller_command(dockerfile, binary_name)
                self.assertIn("--collect-all apprise", command)
                self.assertNotIn("--collect-submodules apprise", command)

    def test_appliance_does_not_use_apprise_submodule_only_collection(self) -> None:
        dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")

        self.assertNotIn("--collect-submodules apprise", dockerfile)

    def test_notifier_binaries_collect_celery_runtime_for_stream_dispatch(self) -> None:
        dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")

        for binary_name in ("notifier-api", "notifier-worker"):
            command = _pyinstaller_command(dockerfile, binary_name)

            for package_name in ("celery", "kombu", "billiard", "vine"):
                with self.subTest(binary_name=binary_name, package_name=package_name):
                    self.assertIn(f"--collect-submodules {package_name}", command)

            for hidden_import in (
                "app.tasks",
                "app.tasks.notification_tasks",
                "celery_app",
            ):
                with self.subTest(binary_name=binary_name, hidden_import=hidden_import):
                    self.assertIn(f"--hidden-import {hidden_import}", command)

    def test_notifier_worker_entrypoint_uses_prefork_with_four_processes(self) -> None:
        source = NOTIFIER_WORKER_ENTRYPOINT_PATH.read_text(encoding="utf-8")

        self.assertIn('"--pool=prefork"', source)
        self.assertNotIn("--pool=gevent", source)
        self.assertRegex(source, r"NOTIFIER_WORKER_CONCURRENCY['\"],\s*['\"]4['\"]")
        self.assertNotRegex(source, r"NOTIFIER_WORKER_CONCURRENCY['\"],\s*['\"]50['\"]")

    def test_notifier_worker_does_not_collect_gevent_for_prefork(self) -> None:
        dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
        command = _pyinstaller_command(dockerfile, "notifier-worker")

        self.assertNotIn("--collect-submodules gevent", command)


class PyInstallerBackendPackagingTests(unittest.TestCase):
    def test_backend_models_are_visible_to_collect_submodules(self) -> None:
        discovered = {module.name for module in pkgutil.iter_modules([str(BACKEND_APP_PATH)])}

        self.assertIn("models", discovered)
        self.assertTrue((BACKEND_APP_PATH / "models" / "__init__.py").is_file())

    def test_backend_migrate_collects_backend_app_submodules(self) -> None:
        dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
        command = _pyinstaller_command(dockerfile, "backend-migrate")

        self.assertIn("--paths /build/backend", command)
        self.assertIn("--collect-submodules app", command)

    def test_backend_migrate_imports_alembic_models_for_pyinstaller(self) -> None:
        source = BACKEND_MIGRATE_ENTRYPOINT_PATH.read_text(encoding="utf-8")
        module = ast.parse(source)
        import_modules = {
            node.module
            for node in ast.walk(module)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }

        expected_modules = {
            "app.models.alerting",
            "app.models.container",
            "app.models.group",
            "app.models.herald.herald_model",
            "app.models.herald.herald_token_model",
            "app.models.notifications",
            "app.models.settings",
        }
        self.assertTrue(expected_modules <= import_modules)


if __name__ == "__main__":
    unittest.main()
