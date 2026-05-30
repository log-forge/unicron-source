from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from app.core.database import session_ctx
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.models.container.crud.container_crud import get_container_by_key
from app.services.agent_registry import get_agent_registry

logger = get_logger("services.browser_session_registry")

SID_LEASE_TTL_SECONDS = 90
SWEEP_INTERVAL_SECONDS = 30
SWEEP_LOCK_KEY = "browser:sessions:sweep:lock"

KEY_SID_LEASE = "browser:sid:{sid}:lease"
KEY_SID_LOGS = "browser:sid:{sid}:logs"
KEY_SID_TERMS = "browser:sid:{sid}:terms"
KEY_SID_STATS = "browser:sid:{sid}:stats"
KEY_LOG_SESSION = "browser:log_session:{session_id}"
KEY_TERM_SESSION = "browser:terminal:{session_id}"
KEY_STATS_SUBSCRIBERS = "browser:stats:container:{container_key}"
KEY_LOG_VIEWERS = "browser:log_viewers:{container_key}"
KEY_HOST_FAST_LOGS = "browser:log_host:{host_id}"
KEY_HOST_FAST_LOG_SUB = "browser:log_host_sub:{host_id}:{container_key}"
KEY_RECENT_LOG_ROWS = "browser:log_recent:{container_key}"
RECENT_LOG_ROWS_LIMIT = 500
RECENT_LOG_ROWS_TTL_SECONDS = 300


@dataclass
class SessionRecord:
    sid: str
    host_id: str
    container_key: str
    source: str = "monitored"
    history_tail: str = ""
    history_since: str = ""


@dataclass
class LogSubscription:
    container_key: str
    source: str
    history_tail: str = ""
    history_since: str = ""


@dataclass
class SidCleanup:
    logs: list[tuple[str, SessionRecord]]
    stopped_logs: list[tuple[str, str, str]]
    terms: list[tuple[str, SessionRecord]]
    stopped_stats: list[tuple[str, str]]


class BrowserSessionRegistry:
    _instance: "BrowserSessionRegistry | None" = None

    def __new__(cls) -> "BrowserSessionRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._sweeper_task: asyncio.Task[None] | None = None

    async def _get_client(self):
        return await get_redis()

    async def start_monitor(self) -> None:
        if self._sweeper_task is not None and not self._sweeper_task.done():
            return
        self._sweeper_task = asyncio.create_task(self._sweeper_loop())
        logger.info("Browser session registry monitor started")

    async def stop_monitor(self) -> None:
        if self._sweeper_task is None:
            return
        self._sweeper_task.cancel()
        try:
            await self._sweeper_task
        except asyncio.CancelledError:
            pass
        self._sweeper_task = None
        logger.info("Browser session registry monitor stopped")

    async def refresh_sid_lease(self, sid: str) -> None:
        sid = str(sid or "").strip()
        if not sid:
            return
        client = await self._get_client()
        await client.set(KEY_SID_LEASE.format(sid=sid), "1", ex=SID_LEASE_TTL_SECONDS)

    async def remove_sid_lease(self, sid: str) -> None:
        sid = str(sid or "").strip()
        if not sid:
            return
        client = await self._get_client()
        await client.delete(KEY_SID_LEASE.format(sid=sid))

    async def is_sid_active(self, sid: str) -> bool:
        client = await self._get_client()
        return bool(await client.exists(KEY_SID_LEASE.format(sid=sid)))

    async def register_log_session(
        self,
        *,
        sid: str,
        session_id: str,
        host_id: str,
        container_key: str,
        source: str,
        history_tail: str = "",
        history_since: str = "",
    ) -> bool:
        client = await self._get_client()
        await self.refresh_sid_lease(sid)
        source = str(source or "monitored").strip() or "monitored"
        history_tail = str(history_tail or "").strip() if source == "live_only" else ""
        history_since = str(history_since or "").strip() if source == "live_only" else ""
        payload = json.dumps(
            {
                "sid": sid,
                "host_id": host_id,
                "container_key": container_key,
                "source": source,
                "history_tail": history_tail,
                "history_since": history_since,
            }
        )
        subscription_payload = json.dumps(
            {
                "container_key": container_key,
                "source": source,
                "history_tail": history_tail,
                "history_since": history_since,
            }
        )
        viewers_key = KEY_LOG_VIEWERS.format(container_key=container_key)
        host_key = KEY_HOST_FAST_LOGS.format(host_id=host_id)
        host_subscription_key = self._host_subscription_key(host_id, container_key)
        async with client.pipeline(transaction=True) as pipe:
            await pipe.set(KEY_LOG_SESSION.format(session_id=session_id), payload)
            await pipe.sadd(KEY_SID_LOGS.format(sid=sid), session_id)
            await pipe.scard(viewers_key)
            await pipe.sadd(viewers_key, session_id)
            await pipe.sadd(host_key, container_key)
            await pipe.set(host_subscription_key, subscription_payload, nx=True)
            results = await pipe.execute()
        return int(results[2]) == 0

    async def get_log_session(self, session_id: str) -> SessionRecord | None:
        return await self._get_session(KEY_LOG_SESSION.format(session_id=session_id))

    async def remove_log_session(self, session_id: str) -> tuple[SessionRecord | None, bool]:
        record = await self._get_session(KEY_LOG_SESSION.format(session_id=session_id))
        client = await self._get_client()
        is_last = False
        async with client.pipeline(transaction=True) as pipe:
            await pipe.delete(KEY_LOG_SESSION.format(session_id=session_id))
            if record is not None:
                await pipe.srem(KEY_SID_LOGS.format(sid=record.sid), session_id)
                await pipe.srem(KEY_LOG_VIEWERS.format(container_key=record.container_key), session_id)
                await pipe.scard(KEY_LOG_VIEWERS.format(container_key=record.container_key))
            results = await pipe.execute()
        if record is None:
            return None, False
        remaining = int(results[-1]) if results else 0
        if remaining == 0:
            viewers_key = KEY_LOG_VIEWERS.format(container_key=record.container_key)
            host_key = KEY_HOST_FAST_LOGS.format(host_id=record.host_id)
            host_subscription_key = self._host_subscription_key(record.host_id, record.container_key)
            recent_key = KEY_RECENT_LOG_ROWS.format(container_key=record.container_key)
            encoded_sub = self._encode_host_subscription(record.container_key, record.source)
            # Re-check viewer count to guard against a concurrent register.
            async with client.pipeline(transaction=True) as pipe:
                await pipe.scard(viewers_key)
                recheck = await pipe.execute()
            if int(recheck[0]) == 0:
                async with client.pipeline(transaction=True) as pipe:
                    await pipe.delete(viewers_key)
                    await pipe.srem(host_key, record.container_key)
                    await pipe.srem(host_key, encoded_sub)
                    await pipe.delete(host_subscription_key)
                    await pipe.delete(recent_key)
                    await pipe.execute()
                is_last = True
        return record, is_last

    async def sid_has_log_subscription(self, sid: str, container_key: str) -> bool:
        client = await self._get_client()
        session_ids = sorted(await client.smembers(KEY_SID_LOGS.format(sid=sid)))
        for session_id in session_ids:
            record = await self.get_log_session(session_id)
            if record is not None and record.container_key == container_key:
                return True
        return False

    async def get_active_fast_log_containers(self, host_id: str) -> list[LogSubscription]:
        client = await self._get_client()
        entries = sorted(await client.smembers(KEY_HOST_FAST_LOGS.format(host_id=host_id)))
        subscriptions: list[LogSubscription] = []
        for entry in entries:
            raw_entry = str(entry or "").strip()
            if not raw_entry:
                continue
            if "|" in raw_entry:
                container_key, source = self._decode_host_subscription(raw_entry)
                if container_key:
                    subscriptions.append(LogSubscription(container_key=container_key, source=source))
                continue
            raw_payload = await client.get(self._host_subscription_key(host_id, raw_entry))
            if raw_payload:
                subscription = self._decode_log_subscription(raw_payload, default_container_key=raw_entry)
                if subscription is not None:
                    subscriptions.append(subscription)
                    continue
            subscriptions.append(LogSubscription(container_key=raw_entry, source="monitored"))
        return subscriptions

    async def append_recent_log_row(self, container_key: str, payload: dict) -> None:
        container_key = str(container_key or "").strip()
        if not container_key:
            return
        client = await self._get_client()
        async with client.pipeline(transaction=True) as pipe:
            await pipe.lpush(KEY_RECENT_LOG_ROWS.format(container_key=container_key), json.dumps(payload))
            await pipe.ltrim(KEY_RECENT_LOG_ROWS.format(container_key=container_key), 0, RECENT_LOG_ROWS_LIMIT - 1)
            await pipe.expire(KEY_RECENT_LOG_ROWS.format(container_key=container_key), RECENT_LOG_ROWS_TTL_SECONDS)
            await pipe.execute()

    async def get_recent_log_rows(self, container_key: str) -> list[dict]:
        container_key = str(container_key or "").strip()
        if not container_key:
            return []
        client = await self._get_client()
        rows = list(await client.lrange(KEY_RECENT_LOG_ROWS.format(container_key=container_key), 0, -1))
        payloads: list[dict] = []
        for raw in reversed(rows):
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            if isinstance(payload, dict):
                payloads.append(payload)
        return payloads

    @staticmethod
    def _encode_host_subscription(container_key: str, source: str) -> str:
        return f"{str(source or 'monitored').strip() or 'monitored'}|{str(container_key or '').strip()}"

    @staticmethod
    def _decode_host_subscription(value: str) -> tuple[str, str]:
        raw = str(value or "").strip()
        if not raw:
            return "", "monitored"
        source, sep, container_key = raw.partition("|")
        if not sep:
            return raw, "monitored"
        return container_key.strip(), source.strip() or "monitored"

    @staticmethod
    def _host_subscription_key(host_id: str, container_key: str) -> str:
        return KEY_HOST_FAST_LOG_SUB.format(host_id=host_id, container_key=container_key)

    @staticmethod
    def _decode_log_subscription(raw: str, *, default_container_key: str = "") -> LogSubscription | None:
        try:
            data = json.loads(raw)
        except Exception:
            logger.warning("Failed to decode fast-tail subscription payload")
            return None
        if not isinstance(data, dict):
            return None
        container_key = str(data.get("container_key") or default_container_key).strip()
        source = str(data.get("source") or "monitored").strip() or "monitored"
        history_tail = str(data.get("history_tail") or "").strip()
        history_since = str(data.get("history_since") or "").strip()
        if not container_key:
            return None
        return LogSubscription(
            container_key=container_key,
            source=source,
            history_tail=history_tail,
            history_since=history_since,
        )

    async def register_terminal_session(self, *, sid: str, session_id: str, host_id: str, container_key: str) -> None:
        client = await self._get_client()
        await self.refresh_sid_lease(sid)
        payload = json.dumps(
            {
                "sid": sid,
                "host_id": host_id,
                "container_key": container_key,
            }
        )
        async with client.pipeline(transaction=True) as pipe:
            await pipe.set(KEY_TERM_SESSION.format(session_id=session_id), payload)
            await pipe.sadd(KEY_SID_TERMS.format(sid=sid), session_id)
            await pipe.execute()

    async def get_terminal_session(self, session_id: str) -> SessionRecord | None:
        return await self._get_session(KEY_TERM_SESSION.format(session_id=session_id))

    async def remove_terminal_session(self, session_id: str) -> SessionRecord | None:
        return await self._remove_session(KEY_TERM_SESSION.format(session_id=session_id), KEY_SID_TERMS)

    async def add_stats_subscription(self, *, sid: str, container_key: str) -> bool:
        client = await self._get_client()
        await self.refresh_sid_lease(sid)
        sid_stats_key = KEY_SID_STATS.format(sid=sid)
        subscriber_key = KEY_STATS_SUBSCRIBERS.format(container_key=container_key)
        if container_key in set(await client.smembers(sid_stats_key)):
            return False
        async with client.pipeline(transaction=True) as pipe:
            await pipe.sadd(sid_stats_key, container_key)
            await pipe.sadd(subscriber_key, sid)
            await pipe.execute()
        return int(await client.scard(subscriber_key)) == 1

    async def remove_stats_subscription(self, *, sid: str, container_key: str) -> bool:
        client = await self._get_client()
        sid_stats_key = KEY_SID_STATS.format(sid=sid)
        subscriber_key = KEY_STATS_SUBSCRIBERS.format(container_key=container_key)
        if container_key not in set(await client.smembers(sid_stats_key)):
            return False
        async with client.pipeline(transaction=True) as pipe:
            await pipe.srem(sid_stats_key, container_key)
            await pipe.srem(subscriber_key, sid)
            await pipe.execute()
        remaining = int(await client.scard(subscriber_key))
        if remaining == 0:
            await client.delete(subscriber_key)
            return True
        return False

    async def cleanup_sid(self, sid: str) -> SidCleanup:
        client = await self._get_client()
        sid = str(sid or "").strip()
        if not sid:
            return SidCleanup(logs=[], stopped_logs=[], terms=[], stopped_stats=[])

        log_session_ids = sorted(await client.smembers(KEY_SID_LOGS.format(sid=sid)))
        term_session_ids = sorted(await client.smembers(KEY_SID_TERMS.format(sid=sid)))
        stats_container_keys = sorted(await client.smembers(KEY_SID_STATS.format(sid=sid)))

        logs: list[tuple[str, SessionRecord]] = []
        stopped_logs: list[tuple[str, str, str]] = []
        for session_id in log_session_ids:
            record, is_last = await self.remove_log_session(session_id)
            if record is not None:
                logs.append((session_id, record))
                if is_last:
                    stopped_logs.append((record.host_id, record.container_key, record.source))

        terms: list[tuple[str, SessionRecord]] = []
        for session_id in term_session_ids:
            record = await self.remove_terminal_session(session_id)
            if record is not None:
                terms.append((session_id, record))

        stopped_stats: list[tuple[str, str]] = []
        for container_key in stats_container_keys:
            is_last = await self.remove_stats_subscription(sid=sid, container_key=container_key)
            if is_last:
                stopped_stats.append((container_key.split(":", 1)[0], container_key))

        async with client.pipeline(transaction=True) as pipe:
            await pipe.delete(KEY_SID_LEASE.format(sid=sid))
            await pipe.delete(KEY_SID_LOGS.format(sid=sid))
            await pipe.delete(KEY_SID_TERMS.format(sid=sid))
            await pipe.delete(KEY_SID_STATS.format(sid=sid))
            await pipe.execute()

        return SidCleanup(logs=logs, stopped_logs=stopped_logs, terms=terms, stopped_stats=stopped_stats)

    async def _get_session(self, key: str) -> SessionRecord | None:
        client = await self._get_client()
        raw = await client.get(key)
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except Exception:
            logger.warning("Failed to decode browser session payload", extra={"key": key})
            return None
        sid = str(data.get("sid") or "").strip()
        host_id = str(data.get("host_id") or "").strip()
        container_key = str(data.get("container_key") or "").strip()
        source = str(data.get("source") or "monitored").strip() or "monitored"
        history_tail = str(data.get("history_tail") or "").strip()
        history_since = str(data.get("history_since") or "").strip()
        if not sid or not host_id or not container_key:
            return None
        return SessionRecord(
            sid=sid,
            host_id=host_id,
            container_key=container_key,
            source=source,
            history_tail=history_tail,
            history_since=history_since,
        )

    async def _remove_session(self, key: str, sid_index_pattern: str) -> SessionRecord | None:
        record = await self._get_session(key)
        client = await self._get_client()
        async with client.pipeline(transaction=True) as pipe:
            await pipe.delete(key)
            if record is not None:
                session_id = key.rsplit(":", 1)[-1]
                await pipe.srem(sid_index_pattern.format(sid=record.sid), session_id)
            await pipe.execute()
        return record

    async def _acquire_sweep_lock(self) -> bool:
        client = await self._get_client()
        return bool(await client.set(SWEEP_LOCK_KEY, "1", ex=SWEEP_INTERVAL_SECONDS, nx=True))

    async def _sweeper_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
                if not await self._acquire_sweep_lock():
                    continue
                await self._reap_stale_sessions()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Browser session sweep failed")

    async def _reap_stale_sessions(self) -> None:
        client = await self._get_client()
        registry = get_agent_registry()

        async for key in client.scan_iter(match="browser:log_session:*"):
            session_id = key.rsplit(":", 1)[-1]
            record = await self._get_session(key)
            if record is None or await self.is_sid_active(record.sid):
                continue
            _, is_last = await self.remove_log_session(session_id)
            if is_last:
                await registry.send_command(
                    record.host_id,
                    "fast_tail_stop",
                    {"container_key": record.container_key, "source": record.source},
                )

        async for key in client.scan_iter(match="browser:terminal:*"):
            session_id = key.rsplit(":", 1)[-1]
            record = await self._get_session(key)
            if record is None or await self.is_sid_active(record.sid):
                continue
            await self.remove_terminal_session(session_id)
            await registry.send_command(record.host_id, "exec_stop", {"session_id": session_id})

        async for key in client.scan_iter(match="browser:stats:container:*"):
            container_key = key.split("browser:stats:container:", 1)[-1]
            subscribers = set(await client.smembers(key))
            stale_sids = [sid for sid in subscribers if not await self.is_sid_active(sid)]
            if stale_sids:
                async with client.pipeline(transaction=True) as pipe:
                    for sid in stale_sids:
                        await pipe.srem(key, sid)
                        await pipe.srem(KEY_SID_STATS.format(sid=sid), container_key)
                    await pipe.execute()
            remaining = int(await client.scard(key))
            if remaining == 0:
                await client.delete(key)
                async with session_ctx() as session:
                    container = await get_container_by_key(session, container_key)
                if container is not None:
                    await registry.send_command(
                        container.herald_id or container_key.split(":", 1)[0],
                        "command",
                        {
                            "action": "stop_stats",
                            "container_id": container.docker_container_id or container.name,
                            "container_key": container.container_key,
                        },
                    )


_REGISTRY = BrowserSessionRegistry()


def get_browser_session_registry() -> BrowserSessionRegistry:
    return _REGISTRY


__all__ = [
    "BrowserSessionRegistry",
    "KEY_HOST_FAST_LOGS",
    "KEY_HOST_FAST_LOG_SUB",
    "KEY_RECENT_LOG_ROWS",
    "KEY_LOG_SESSION",
    "KEY_LOG_VIEWERS",
    "LogSubscription",
    "KEY_SID_LEASE",
    "KEY_SID_LOGS",
    "KEY_SID_STATS",
    "KEY_SID_TERMS",
    "KEY_STATS_SUBSCRIBERS",
    "KEY_TERM_SESSION",
    "SessionRecord",
    "SidCleanup",
    "get_browser_session_registry",
]
