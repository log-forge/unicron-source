import unittest

from app.routes.internal.logs import _decode_ingest_envelope


class LogIngestEnvelopeContractTests(unittest.TestCase):
    def test_decode_rejects_non_object_payload(self) -> None:
        source, logs = _decode_ingest_envelope(["not", "an", "object"])
        self.assertEqual(source, "unknown")
        self.assertEqual(logs, [])

    def test_decode_accepts_strict_source_logs_envelope(self) -> None:
        source, logs = _decode_ingest_envelope(
            {
                "source": "Agent",
                "logs": [
                    {"host_id": "h1", "container_name": "web", "message": "ok"},
                    "bad-entry",
                ],
            }
        )
        self.assertEqual(source, "agent")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["host_id"], "h1")

    def test_decode_rejects_legacy_envelope_shape(self) -> None:
        source, logs = _decode_ingest_envelope(
            {
                "source": "agent",
                "entries": [
                    {"host_id": "h1", "container_name": "web", "message": "legacy"},
                ],
            }
        )
        self.assertEqual(source, "unknown")
        self.assertEqual(logs, [])


if __name__ == "__main__":
    unittest.main()
