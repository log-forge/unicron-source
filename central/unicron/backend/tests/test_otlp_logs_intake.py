import unittest
from unittest.mock import AsyncMock, patch

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
    ExportLogsServiceResponse,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue

from app.routes.internal.otlp_logs import (
    OTLP_PROTO_CONTENT_TYPE,
    decode_otlp_log_payload,
    ingest_otlp_logs,
)


def _kv(key: str, value: AnyValue) -> KeyValue:
    item = KeyValue()
    item.key = key
    item.value.CopyFrom(value)
    return item


class OtlpLogsIntakeTests(unittest.TestCase):
    def test_decode_otlp_log_payload_normalizes_alert_schema(self) -> None:
        request = ExportLogsServiceRequest()
        resource_logs = request.resource_logs.add()
        resource_logs.resource.attributes.extend(
            [
                _kv("herald_id", AnyValue(string_value="host-a")),
                _kv("herald_name", AnyValue(string_value="edge-a")),
                _kv("container_key", AnyValue(string_value="host-a:web")),
                _kv("container_name", AnyValue(string_value="web")),
                _kv("docker_container_id", AnyValue(string_value="abc123")),
                _kv("service_name", AnyValue(string_value="web")),
                _kv("service_namespace", AnyValue(string_value="unicron.herald")),
            ]
        )

        scope_logs = resource_logs.scope_logs.add()
        record = scope_logs.log_records.add()
        record.time_unix_nano = 1_763_000_000_123_000_000
        record.body.string_value = "hello world"
        msg_json_value = AnyValue()
        msg_json_value.kvlist_value.values.extend(
            [_kv("log", AnyValue(string_value="hello world"))]
        )
        record.attributes.extend(
            [
                _kv("msg", AnyValue(string_value="hello world")),
                _kv("stream", AnyValue(string_value="stdout")),
                _kv("severity", AnyValue(string_value="info")),
                _kv("msg_json", msg_json_value),
            ]
        )

        decoded = decode_otlp_log_payload(request.SerializeToString())
        self.assertEqual(len(decoded), 1)
        item = decoded[0]
        self.assertEqual(item["host_id"], "host-a")
        self.assertEqual(item["container_key"], "host-a:web")
        self.assertEqual(item["container_id"], "host-a:web")
        self.assertEqual(item["container_name"], "web")
        self.assertEqual(item["message"], "hello world")
        self.assertEqual(item["herald_name"], "edge-a")
        self.assertEqual(item["docker_container_id"], "abc123")
        self.assertEqual(item["service_namespace"], "unicron.herald")
        self.assertEqual(item["stream"], "stdout")
        self.assertEqual(item["severity"], "info")
        self.assertEqual(item["msg_json"], {"log": "hello world"})
        self.assertTrue(item["timestamp"].endswith("Z"))

    def test_decode_otlp_log_payload_derives_container_key_from_host_and_name(self) -> None:
        request = ExportLogsServiceRequest()
        resource_logs = request.resource_logs.add()
        resource_logs.resource.attributes.extend(
            [
                _kv("herald_id", AnyValue(string_value="host-b")),
                _kv("container_name", AnyValue(string_value="worker")),
            ]
        )

        scope_logs = resource_logs.scope_logs.add()
        record = scope_logs.log_records.add()
        record.body.string_value = "tick"

        decoded = decode_otlp_log_payload(request.SerializeToString())
        self.assertEqual(len(decoded), 1)
        self.assertEqual(decoded[0]["container_key"], "host-b:worker")
        self.assertEqual(decoded[0]["container_id"], "host-b:worker")


class OtlpLogsIntakeRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_ingest_otlp_logs_reuses_scope_filter_and_publish_batch(self) -> None:
        request = ExportLogsServiceRequest()
        resource_logs = request.resource_logs.add()
        resource_logs.resource.attributes.extend(
            [
                _kv("herald_id", AnyValue(string_value="host-a")),
                _kv("container_key", AnyValue(string_value="host-a:web")),
                _kv("container_name", AnyValue(string_value="web")),
            ]
        )
        scope_logs = resource_logs.scope_logs.add()
        record = scope_logs.log_records.add()
        record.body.string_value = "hello"

        class _FakeRequest:
            async def body(self):
                return request.SerializeToString()

        filter_mock = AsyncMock()
        filter_mock.filter_relevant.return_value = [
            {
                "host_id": "host-a",
                "container_key": "host-a:web",
                "container_id": "host-a:web",
                "container_name": "web",
                "message": "hello",
                "timestamp": "2026-03-20T01:02:03Z",
            }
        ]

        with (
            patch("app.routes.internal.otlp_logs.get_log_scope_filter", return_value=filter_mock),
            patch("app.routes.internal.otlp_logs.publish_log_batch", new=AsyncMock(return_value=1)) as publish_mock,
        ):
            response = await ingest_otlp_logs(_FakeRequest(), session=object(), _=None)

        filter_mock.filter_relevant.assert_awaited_once()
        publish_mock.assert_awaited_once()
        self.assertEqual(response.media_type, OTLP_PROTO_CONTENT_TYPE)

        parsed = ExportLogsServiceResponse()
        parsed.ParseFromString(response.body)
        self.assertEqual(parsed.partial_success.rejected_log_records, 0)


if __name__ == "__main__":
    unittest.main()
