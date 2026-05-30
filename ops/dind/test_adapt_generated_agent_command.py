from __future__ import annotations

import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).with_name("adapt_generated_agent_command.py")
SPEC = importlib.util.spec_from_file_location("adapt_generated_agent_command", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


GENERATED_COMMAND = """
# Reinstall is idempotent: remove any old container with this agent name.
# Reset only the agent identity/trust volume for this fresh enrollment.
# Durable telemetry queue volumes are preserved when explicitly enabled.
docker rm -f unicron-agent-herald 2>/dev/null || true
docker volume rm unicron-agent-herald-data 2>/dev/null || true
docker run -d --name unicron-agent-herald \\
  --restart unless-stopped \\
  -p 24224:24224 \\
  -p 9880:9880 \\
  -p 4317:4317 \\
  -p 4318:4318 \\
  -v /var/run/docker.sock:/var/run/docker.sock \\
  -v /:/host/root:ro \\
  -v /var/lib/docker/containers:/var/lib/docker/containers:ro \\
  -v unicron-agent-herald-data:/agent-data \\
  -e AGENT_NAME=herald \\
  -e CENTRAL_WS_URL=wss://unicron.central:8443/unicron/api/agent/ws \\
  -e CENTRAL_URL=https://unicron.central/unicron \\
  -e CENTRAL_MTLS_URL=https://unicron.central:8443 \\
  -e ENROLL_TOKEN=token-123 \\
  -e CA_FINGERPRINT=fingerprint-123 \\
  -e HOST_ID=herald \\
  -e HERALD_NAME=herald \\
  -e HERALD_ID=herald \\
  -e HERALD_CA_ROOT=/agent-data/certs/root_ca.crt \\
  -e HERALD_CERT=/agent-data/certs/agent.crt \\
  -e HERALD_KEY=/agent-data/certs/agent.key \\
  -e TELEMETRY_MODE=hybrid \\
  -e TELEMETRY_QUEUE_MODE=memory \\
  -e TELEMETRY_MEMORY_QUEUE_MB=256 \\
  -e OTEL_SENDING_QUEUE_SIZE=64000 \\
  -e FLB_MEM_BUF_LIMIT=256MB \\
  -e FLB_TAIL_DB_PATH=/dev/shm/flb_monitored.db \\
  -e UPSTREAM_CRITICAL_QUEUE_SIZE=1024 \\
  -e UPSTREAM_TELEMETRY_QUEUE_SIZE=4096 \\
  -e UPSTREAM_CRITICAL_ENQUEUE_TIMEOUT_MS=5000 \\
  -e DOCKER_API_VERSION=1.44 \\
  -e ENVIRONMENT=production \\
  localhost:5000/unicron-go-streamer:latest
"""


class AdaptGeneratedAgentCommandTests(unittest.TestCase):
    def test_extract_container_name_reads_canonical_name(self) -> None:
        self.assertEqual(
            MODULE.extract_container_name(GENERATED_COMMAND),
            "unicron-agent-herald",
        )

    def test_rewrite_swaps_image_and_injects_add_host(self) -> None:
        rewritten = MODULE.rewrite_generated_agent_command(
            GENERATED_COMMAND,
            image_ref="registry:5000/unicron-go-streamer:latest",
            hostname="unicron.central",
            resolved_ip="203.0.113.10",
        )

        self.assertIn("docker rm -f unicron-agent-herald 2>/dev/null;", rewritten)
        self.assertIn("docker volume rm unicron-agent-herald-data 2>/dev/null || true;", rewritten)
        self.assertLess(
            rewritten.index("docker volume rm unicron-agent-herald-data"),
            rewritten.index("docker run -d --name unicron-agent-herald"),
        )
        self.assertIn("--add-host=unicron.central:203.0.113.10", rewritten)
        self.assertTrue(rewritten.endswith("registry:5000/unicron-go-streamer:latest"))
        self.assertIn("-e ENVIRONMENT=production", rewritten)

    def test_rewrite_replaces_loopback_central_urls_with_dind_hostname(self) -> None:
        localhost_command = GENERATED_COMMAND.replace(
            "wss://unicron.central:8443/unicron/api/agent/ws",
            "wss://localhost:8443/unicron/api/agent/ws",
        ).replace(
            "https://unicron.central/unicron",
            "https://localhost/unicron",
        ).replace(
            "https://unicron.central:8443",
            "https://localhost:8443",
        )

        rewritten = MODULE.rewrite_generated_agent_command(
            localhost_command,
            image_ref="registry:5000/unicron-go-streamer:latest",
            hostname="unicron.central",
            resolved_ip="203.0.113.10",
        )

        self.assertIn("-e CENTRAL_WS_URL=wss://unicron.central:8443/unicron/api/agent/ws", rewritten)
        self.assertIn("-e CENTRAL_URL=https://unicron.central/unicron", rewritten)
        self.assertIn("-e CENTRAL_MTLS_URL=https://unicron.central:8443", rewritten)
        self.assertNotIn("https://localhost/unicron", rewritten)
        self.assertNotIn("wss://localhost:8443/unicron/api/agent/ws", rewritten)

    def test_rewrite_replaces_existing_add_host_for_same_hostname(self) -> None:
        rewritten = MODULE.rewrite_generated_agent_command(
            GENERATED_COMMAND.replace(
                "--restart unless-stopped \\",
                "--restart unless-stopped \\\n  --add-host=unicron.central:198.51.100.20 \\",
            ),
            image_ref="registry:5000/unicron-go-streamer:latest",
            hostname="unicron.central",
            resolved_ip="203.0.113.10",
        )

        self.assertIn("--add-host=unicron.central:203.0.113.10", rewritten)
        self.assertNotIn("--add-host=unicron.central:198.51.100.20", rewritten)

    def test_validation_rejects_noncanonical_input(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.rewrite_generated_agent_command(
                "echo hello",
                image_ref="registry:5000/unicron-go-streamer:latest",
                hostname="unicron.central",
                resolved_ip="203.0.113.10",
            )


if __name__ == "__main__":
    unittest.main()
