import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.routes.agent.enrollment import (
    EnrollAgentRequest,
    _derive_central_mtls_url,
    _derive_central_ws_url,
    _resolve_local_central_endpoint,
    _select_docker_containers_mount_source,
    enroll_agent,
    list_agents,
)
from app.utils.pki.cert_utils import sign_csr
from app.utils.pki.ca_fingerprint import (
    ca_fingerprint_candidate_paths,
    read_ca_fingerprint,
    read_root_ca_pem,
    root_ca_candidate_paths,
)
from fastapi import HTTPException


class AgentEnrollmentTests(unittest.TestCase):
    def test_enrollment_defaults_to_memory_queue(self) -> None:
        request = EnrollAgentRequest(agent_name="edge-a")

        self.assertEqual(request.queue_mode, "memory")
        self.assertEqual(request.flb_storage_sync, "normal")
        self.assertIsNone(request.flb_storage_max_chunks_up)

    @patch("app.routes.agent.enrollment.settings.UNICRON_PUBLIC_CENTRAL_MTLS_PORT", None)
    @patch("app.routes.agent.enrollment.settings.UNICRON_CENTRAL_MTLS_PORT", 8443)
    def test_derive_central_mtls_url_uses_host_only_origin(self) -> None:
        self.assertEqual(
            _derive_central_mtls_url("https://unicron.central/unicron"),
            "https://unicron.central:8443",
        )

    @patch("app.routes.agent.enrollment.settings.UNICRON_PUBLIC_CENTRAL_MTLS_PORT", 9443)
    @patch("app.routes.agent.enrollment.settings.UNICRON_CENTRAL_MTLS_PORT", 8443)
    def test_remote_agent_urls_use_public_mtls_port(self) -> None:
        central_url = "https://unicron.central:8444/unicron"

        self.assertEqual(
            _derive_central_ws_url(central_url, install_target="remote"),
            "wss://unicron.central:9443/unicron/api/agent/ws",
        )
        self.assertEqual(
            _derive_central_mtls_url(central_url, install_target="remote"),
            "https://unicron.central:9443",
        )

    @patch("app.routes.agent.enrollment.settings.UNICRON_PUBLIC_CENTRAL_MTLS_PORT", 9443)
    @patch("app.routes.agent.enrollment.settings.UNICRON_CENTRAL_MTLS_PORT", 8443)
    def test_local_agent_urls_keep_internal_mtls_port(self) -> None:
        central_url = "https://traefik/unicron"

        self.assertEqual(
            _derive_central_ws_url(central_url, install_target="local"),
            "wss://traefik:8443/unicron/api/agent/ws",
        )
        self.assertEqual(
            _derive_central_mtls_url(central_url, install_target="local"),
            "https://traefik:8443",
        )

    def test_select_docker_containers_mount_source_prefers_populated_default_path(self) -> None:
        with tempfile.TemporaryDirectory() as default_dir, tempfile.TemporaryDirectory() as alt_dir:
            os.mkdir(os.path.join(default_dir, "a" * 64))
            os.mkdir(os.path.join(alt_dir, "b" * 64))

            self.assertEqual(
                _select_docker_containers_mount_source([default_dir, alt_dir]),
                default_dir,
            )

    def test_select_docker_containers_mount_source_falls_back_to_populated_wsl_path(self) -> None:
        with tempfile.TemporaryDirectory() as default_dir, tempfile.TemporaryDirectory() as alt_dir:
            os.mkdir(os.path.join(alt_dir, "b" * 64))

            self.assertEqual(
                _select_docker_containers_mount_source([default_dir, alt_dir]),
                alt_dir,
            )

    def test_resolve_local_central_endpoint_uses_configured_appliance_alias(self) -> None:
        with patch(
            "app.routes.agent.enrollment.settings.LOCAL_AGENT_CENTRAL_URL",
            "https://unicron.central/unicron",
        ), patch(
            "app.routes.agent.enrollment.settings.LOCAL_AGENT_DOCKER_NETWORK",
            "unicron-network",
        ):
            self.assertEqual(
                _resolve_local_central_endpoint(),
                ("https://unicron.central/unicron", "unicron.central", "unicron-network"),
            )

    def test_read_ca_fingerprint_uses_file_next_to_configured_root_ca(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trust_dir = os.path.join(temp_dir, "pki", "trust")
            os.makedirs(trust_dir)
            fingerprint_path = os.path.join(trust_dir, "root_ca_fingerprint.txt")
            with open(fingerprint_path, "w", encoding="utf-8") as f:
                f.write("abc123\n")

            with patch(
                "app.utils.pki.ca_fingerprint.settings.ROOT_CA",
                os.path.join(trust_dir, "root_ca.crt"),
            ), patch(
                "app.utils.pki.ca_fingerprint.settings.UNICRON_DATA_DIR",
                os.path.join(temp_dir, "backend"),
            ):
                self.assertEqual(read_ca_fingerprint(), "abc123")

    def test_read_root_ca_uses_configured_root_ca(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trust_dir = os.path.join(temp_dir, "pki", "trust")
            os.makedirs(trust_dir)
            root_ca_path = os.path.join(trust_dir, "root_ca.crt")
            with open(root_ca_path, "w", encoding="utf-8") as f:
                f.write("-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----\n")

            with patch(
                "app.utils.pki.ca_fingerprint.settings.ROOT_CA",
                root_ca_path,
            ), patch(
                "app.utils.pki.ca_fingerprint.settings.UNICRON_DATA_DIR",
                os.path.join(temp_dir, "backend"),
            ):
                self.assertIn("BEGIN CERTIFICATE", read_root_ca_pem())

    def test_read_ca_fingerprint_uses_appliance_parent_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            certs_dir = os.path.join(temp_dir, "pki", "certs")
            os.makedirs(certs_dir)
            fingerprint_path = os.path.join(certs_dir, "root_ca_fingerprint.txt")
            with open(fingerprint_path, "w", encoding="utf-8") as f:
                f.write("def456\n")

            with patch(
                "app.utils.pki.ca_fingerprint.settings.ROOT_CA",
                os.path.join(temp_dir, "backend", "missing_root_ca.crt"),
            ), patch(
                "app.utils.pki.ca_fingerprint.settings.UNICRON_DATA_DIR",
                os.path.join(temp_dir, "backend"),
            ):
                self.assertEqual(read_ca_fingerprint(), "def456")

    def test_ca_fingerprint_candidates_use_greenfield_paths_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "app.utils.pki.ca_fingerprint.settings.ROOT_CA",
                os.path.join(temp_dir, "pki", "trust", "root_ca.crt"),
            ), patch(
                "app.utils.pki.ca_fingerprint.settings.UNICRON_DATA_DIR",
                os.path.join(temp_dir, "backend"),
            ):
                candidates = ca_fingerprint_candidate_paths()

            self.assertEqual(candidates[0], os.path.join(temp_dir, "pki", "trust", "root_ca_fingerprint.txt"))
            self.assertIn(os.path.join(temp_dir, "pki", "certs", "root_ca_fingerprint.txt"), candidates)
            self.assertNotIn("/ca/certs/root_ca_fingerprint.txt", candidates)

    def test_root_ca_candidates_use_greenfield_paths_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_ca_path = os.path.join(temp_dir, "pki", "trust", "root_ca.crt")
            with patch(
                "app.utils.pki.ca_fingerprint.settings.ROOT_CA",
                root_ca_path,
            ), patch(
                "app.utils.pki.ca_fingerprint.settings.UNICRON_DATA_DIR",
                os.path.join(temp_dir, "backend"),
            ):
                candidates = root_ca_candidate_paths()

            self.assertEqual(candidates[0], root_ca_path)
            self.assertIn(os.path.join(temp_dir, "pki", "certs", "root_ca.crt"), candidates)
            self.assertNotIn("/ca/certs/root_ca.crt", candidates)


class AgentEnrollmentCommandTests(unittest.IsolatedAsyncioTestCase):
    async def generate_command(self, body: EnrollAgentRequest) -> str:
        request = SimpleNamespace(headers={}, url=SimpleNamespace(scheme="https"))
        token = SimpleNamespace(id="token-123")

        with (
            patch("app.routes.agent.enrollment.create_herald_token", new=AsyncMock(return_value=token)),
            patch("app.routes.agent.enrollment.read_ca_fingerprint", return_value="fingerprint-123"),
            patch("app.routes.agent.enrollment.settings.REMOTE_AGENT_IMAGE", "agent:latest"),
            patch("app.routes.agent.enrollment.settings.UNICRON_PUBLIC_CENTRAL_MTLS_PORT", None),
            patch("app.routes.agent.enrollment.settings.UNICRON_CENTRAL_MTLS_PORT", 8443),
        ):
            response = await enroll_agent(
                body,
                request,
                session=object(),
                _auth=None,
            )

        return response.docker_run_command

    async def test_default_command_uses_memory_queue_without_durable_mounts(self) -> None:
        command = await self.generate_command(
            EnrollAgentRequest(agent_name="edge-a", central_url="https://central.example/unicron")
        )

        self.assertIn("-e TELEMETRY_QUEUE_MODE=memory", command)
        self.assertIn("-e FLB_TAIL_DB_PATH=/dev/shm/flb_monitored.db", command)
        self.assertNotIn("otel-queue", command)
        self.assertNotIn("flb-db", command)
        self.assertNotIn("TELEMETRY_DISK_QUEUE_MB", command)
        self.assertNotIn("FLB_STORAGE_", command)
        self.assertNotIn("/var/lib/otelcol/queue", command)
        self.assertNotIn(":/tmp/flb", command)

    async def test_durable_command_keeps_durable_queue_mounts_and_storage_env(self) -> None:
        command = await self.generate_command(
            EnrollAgentRequest(
                agent_name="edge-a",
                central_url="https://central.example/unicron",
                queue_mode="durable",
                flb_storage_max_chunks_up=64,
            )
        )

        self.assertIn("-e TELEMETRY_QUEUE_MODE=durable", command)
        self.assertIn("-v unicron-agent-edge-a-otel-queue:/var/lib/otelcol/queue", command)
        self.assertIn("-v unicron-agent-edge-a-flb-db:/tmp/flb", command)
        self.assertIn("-e TELEMETRY_DISK_QUEUE_MB=1024", command)
        self.assertIn("-e FLB_STORAGE_BACKLOG_MEM_LIMIT=256MB", command)
        self.assertIn("-e FLB_STORAGE_TOTAL_LIMIT=1024MB", command)
        self.assertIn("-e FLB_STORAGE_SYNC=normal", command)
        self.assertIn("-e FLB_STORAGE_MAX_CHUNKS_UP=64", command)
        self.assertIn("-e FLB_TAIL_DB_PATH=/tmp/flb/flb_monitored.db", command)

    async def test_generated_command_removes_data_volume_before_docker_run(self) -> None:
        command = await self.generate_command(
            EnrollAgentRequest(agent_name="edge-a", central_url="https://central.example/unicron")
        )
        volume_rm = "docker volume rm unicron-agent-edge-a-data 2>/dev/null || true"

        self.assertIn(volume_rm, command)
        self.assertLess(command.index(volume_rm), command.index("docker run -d --name unicron-agent-edge-a"))
        self.assertIn("-v unicron-agent-edge-a-data:/agent-data", command)


class AgentListTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_agents_excludes_ordinary_expired_enrollment_tokens(self) -> None:
        cache = SimpleNamespace(
            get_all_hosts=AsyncMock(return_value=[]),
            get_host_status_snapshot=AsyncMock(return_value=({}, {}, {}, {})),
        )

        with (
            patch("app.routes.agent.enrollment.get_agent_registry", return_value=Mock(list_hosts=Mock(return_value={}))),
            patch("app.routes.agent.enrollment.get_container_cache", return_value=cache),
            patch("app.routes.agent.enrollment.list_registered_herald_ids_by_ids", new=AsyncMock(return_value=[])),
        ):
            response = await list_agents(status_filter="all", limit=200, offset=0, session=object(), _auth=None)

        self.assertEqual(response.total, 0)
        self.assertEqual(response.agents, [])

    def test_sign_csr_requires_configured_ra_password_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = os.path.join(temp_dir, "ra.jwk.json")
            password_path = os.path.join(temp_dir, "missing-ra.jwk.pw")
            with open(key_path, "w", encoding="utf-8") as f:
                f.write("{}")

            with patch(
                "app.utils.pki.cert_utils._parse_csr_and_validate",
                return_value=("local", ["spiffe://unicron/streamer/local"]),
            ), patch(
                "app.utils.pki.cert_utils.settings.RA_PROVISIONER_KEY",
                key_path,
            ), patch(
                "app.utils.pki.cert_utils.settings.RA_PROVISIONER_PASSWORD_FILE",
                password_path,
            ):
                with self.assertRaises(HTTPException) as raised:
                    sign_csr(
                        csr_pem="",
                        not_after_seconds=60,
                        expected_spiffe_uris=["spiffe://unicron/streamer/local"],
                    )

            self.assertEqual(raised.exception.detail, "RA provisioner password unavailable")


if __name__ == "__main__":
    unittest.main()
