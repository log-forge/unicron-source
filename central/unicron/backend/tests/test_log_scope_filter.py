import unittest

from app.services.alerting.log_scope_filter import LogScopeFilter


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _stmt):
        if not self._results:
            raise AssertionError("Unexpected extra execute() call")
        return _FakeResult(self._results.pop(0))


def _sample_logs():
    return [
        {
            "host_id": "host-a",
            "container_name": "web",
            "container_key": "host-a:web",
            "message": "alpha",
            "timestamp": "2026-03-10T00:00:00Z",
        },
        {
            "host_id": "host-b",
            "container_name": "api",
            "container_key": "host-b:api",
            "message": "beta",
            "timestamp": "2026-03-10T00:00:01Z",
        },
        {
            "host_id": "host-c",
            "container_name": "worker",
            "container_key": "host-c:worker",
            "message": "gamma",
            "timestamp": "2026-03-10T00:00:02Z",
        },
    ]


class LogScopeFilterMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_scope_matches_all_logs(self) -> None:
        session = _FakeSession([
            [("global", [])],
        ])
        filter_ = LogScopeFilter(refresh_interval_seconds=5)
        logs = _sample_logs()

        relevant = await filter_.filter_relevant(session, logs)
        self.assertEqual(len(relevant), len(logs))

    async def test_herald_scope_matches_target_host(self) -> None:
        session = _FakeSession([
            [("herald", ["host-b"])],
        ])
        filter_ = LogScopeFilter(refresh_interval_seconds=5)

        relevant = await filter_.filter_relevant(session, _sample_logs())
        self.assertEqual([entry["host_id"] for entry in relevant], ["host-b"])

    async def test_container_scope_matches_target_container_key(self) -> None:
        session = _FakeSession([
            [("container", ["host-c:worker"])],
        ])
        filter_ = LogScopeFilter(refresh_interval_seconds=5)

        relevant = await filter_.filter_relevant(session, _sample_logs())
        self.assertEqual([entry["container_key"] for entry in relevant], ["host-c:worker"])

    async def test_group_scope_resolves_group_to_container_keys(self) -> None:
        session = _FakeSession([
            [("group", ["group-1"])],
            [("host-a:web",)],
        ])
        filter_ = LogScopeFilter(refresh_interval_seconds=5)

        relevant = await filter_.filter_relevant(session, _sample_logs())
        self.assertEqual([entry["container_key"] for entry in relevant], ["host-a:web"])


if __name__ == "__main__":
    unittest.main()
