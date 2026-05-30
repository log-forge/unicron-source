"""Configuration settings for alert-engine service."""

from typing import Any, Dict, List, Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Alert-engine service configuration."""

    # Service identification
    ENVIRONMENT: str = "production"
    SERVICE_NAME: str = "alert-engine"
    SERVICE_VERSION: str = "1.0.0"
    ROOT_PATH: str = "/alert-engine"
    API_PREFIX: str = "/api"

    # Central connection
    CENTRAL_URL: str = "http://unicron-central:8000"
    CENTRAL_VERIFY_TLS: bool = True
    CENTRAL_AUTH_BASE_URL: str = "http://central-auth:3020"
    CENTRAL_AUTH_VERIFY_TLS: bool = True
    # Cache validated user context from Central Auth in Redis with short TTL
    # to reduce auth hot-path latency.
    CENTRAL_SESSION_CACHE_ENABLED: bool = True
    CENTRAL_SESSION_CACHE_TTL_SECONDS: int = 10
    CENTRAL_SESSION_CACHE_PREFIX: str = "unicron:auth:central_session"
    CENTRAL_SESSION_L1_CACHE_ENABLED: bool = True
    CENTRAL_SESSION_L1_CACHE_TTL_SECONDS: int = 2
    CENTRAL_SESSION_L1_STALE_GRACE_SECONDS: int = 2

    # Central Socket.IO (for event subscription)
    CENTRAL_SOCKETIO_URL: str = "http://unicron-central:8000"
    CENTRAL_SOCKETIO_PATH: str = "/unicron/api/socket.io"
    CENTRAL_INTERNAL_NAMESPACE: str = "/internal"

    # Central internal API (for context lookups)
    CENTRAL_INTERNAL_SECRET: str = Field(
        default="",
        validation_alias=AliasChoices("CENTRAL_INTERNAL_SECRET", "INTERNAL_API_SECRET"),
    )
    INTERNAL_API_TIMEOUT: int = 5  # Seconds

    # PostgreSQL (shared with Central - alerting schema)
    POSTGRES_USER: str = "unicron"
    POSTGRES_PASSWORD: str = "unicron_password"
    POSTGRES_DB: str = "unicron_db"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50

    # Victoria (for log queries)
    VLOGS_BASE: str = "http://unicron-victoria-logs:9428"
    VMETRICS_BASE: str = "http://unicron-victoria-metrics:8428"

    # Evaluation scheduler
    EVALUATION_INTERVAL_SECONDS: int = 60
    REALTIME_RULE_EVAL_ENABLED: bool = True
    REALTIME_RULE_EVAL_DUAL_RUN: bool = False
    REALTIME_RULE_INDEX_VERSION_KEY: str = "unicron:alert-engine:rule-index:version"
    REALTIME_RULE_INDEX_VERSION_CHECK_SECONDS: float = 1.0
    REALTIME_RULE_WINDOW_BUCKET_SECONDS: int = 5
    REALTIME_RULE_WINDOW_MAX_SECONDS: int = 3600
    REALTIME_RULE_LATE_EVENT_GRACE_SECONDS: int = 30

    # Alert grouping
    GROUP_WAIT_SECONDS: int = 30
    GROUP_INTERVAL_SECONDS: int = 300

    # Redis Streams (for alert-to-notifier pipeline)
    REDIS_STREAM_ALERTS: str = "unicron:alerts"
    REDIS_STREAM_MAX_LEN: int = 10000
    REDIS_NOTIFIER_CONSUMER_GROUP: str = "notifier-workers"
    REDIS_STREAM_ALERTS_DLQ: str = "unicron:alerts:dlq"

    # Redis Streams (for log processing pipeline - real-time rule evaluation)
    REDIS_STREAM_LOGS: str = "unicron:logs"
    REDIS_LOG_CONSUMER_GROUP: str = "alert-engine-workers"
    REDIS_LOG_CONSUMER_BATCH_SIZE: int = 100  # Process 100 logs per batch
    REDIS_LOG_CONSUMER_BLOCK_MS: int = 1000  # Block for 1 second
    REDIS_LOG_STREAM_MAX_LEN: int = 500000  # ~500K entries max (~5 min at 50K logs/sec)
    REDIS_LOG_STREAM_TRIM_APPROX: bool = True  # Use approximate trimming for performance

    # Redis Streams (for container inventory updates from Herald via Central)
    REDIS_STREAM_CONTAINERS: str = "unicron:containers"
    REDIS_CONTAINER_CONSUMER_GROUP: str = "alert-engine-containers"
    REDIS_CONTAINER_CONSUMER_BATCH_SIZE: int = 50  # Container updates less frequent than logs
    REDIS_CONTAINER_CONSUMER_BLOCK_MS: int = 1000  # Block for 1 second

    # Redis Streams (for container lifecycle events - stability rule evaluation)
    REDIS_STREAM_EVENTS: str = "unicron:events"
    REDIS_EVENT_CONSUMER_GROUP: str = "alert-engine-events"
    REDIS_EVENT_CONSUMER_BATCH_SIZE: int = 50
    REDIS_EVENT_CONSUMER_BLOCK_MS: int = 1000
    REDIS_RECLAIM_ENABLED: bool = True
    REDIS_RECLAIM_IDLE_MS: int = 60000
    REDIS_RECLAIM_BATCH_SIZE: int = 100
    REDIS_RECLAIM_INTERVAL_SECONDS: int = 5
    REDIS_DLQ_ENABLED: bool = True
    REDIS_DLQ_MAX_LEN: int = 50000
    REDIS_STREAM_LOGS_DLQ: str = "unicron:logs:dlq"
    REDIS_STREAM_CONTAINERS_DLQ: str = "unicron:containers:dlq"
    REDIS_STREAM_EVENTS_DLQ: str = "unicron:events:dlq"
    INGEST_LOG_COUNTER_KEY: str = "unicron:ingest:logs:counters"
    INGEST_HEALTH_WINDOW_SECONDS: int = 300

    # Backpressure health thresholds
    STREAM_PENDING_WARN: int = 1000
    STREAM_PENDING_CRITICAL: int = 5000
    STREAM_LAG_WARN: int = 2000
    STREAM_LAG_CRITICAL: int = 10000
    STREAM_DLQ_WARN: int = 10
    STREAM_DLQ_CRITICAL: int = 100

    # OTel Collector self-metrics (OTLP metrics ingest path health)
    OTEL_COLLECTOR_METRICS_URL: str = "http://unicron-otel-collector:8888/metrics"
    OTEL_COLLECTOR_METRICS_TIMEOUT_SECONDS: int = 3
    OTEL_QUEUE_SATURATION_WARN: float = 0.8
    OTEL_QUEUE_SATURATION_CRITICAL: float = 0.95

    # Alert history partition maintenance
    ALERT_HISTORY_PARTITION_MAINTENANCE_ENABLED: bool = True
    ALERT_HISTORY_PARTITION_LOOKAHEAD_MONTHS: int = 3
    ALERT_HISTORY_PARTITION_RETENTION_MONTHS: int = 12

    # CORS
    CORS_ORIGINS: str = ""
    CORS_ALLOW_CREDENTIALS: bool = True

    # Gatekeeper configuration (for action rate limiting and backoff)
    GATEKEEPER_COOLDOWN_RESTART: int = 5
    GATEKEEPER_COOLDOWN_STOP: int = 3
    GATEKEEPER_COOLDOWN_START: int = 3
    GATEKEEPER_COOLDOWN_KILL: int = 5
    GATEKEEPER_COOLDOWN_RUN_SCRIPT: int = 10
    GATEKEEPER_MAX_BACKOFF_MINUTES: int = 30
    GATEKEEPER_DISABLE_AFTER_FAILURES: int = 3
    GATEKEEPER_DISABLE_DURATION_MINUTES: int = 60
    GATEKEEPER_MAX_ACTIONS_PER_RULE_PER_HOUR: int = 3
    GATEKEEPER_MAX_ACTIONS_PER_CONTAINER_PER_HOUR: int = 10
    GATEKEEPER_VERIFICATION_DELAY_SECONDS: int = 30
    GATEKEEPER_TRIGGER_SUPPRESSION_ENABLED: bool = True
    GATEKEEPER_TRIGGER_SUPPRESSION_MINUTES: int = 10
    GATEKEEPER_TRIGGER_SUPPRESSION_ACTIONS: str = "stop,kill,restart,start,notify"
    GATEKEEPER_TRIGGER_SUPPRESSION_RULE_TYPES: str = "all"
    GATEKEEPER_DEDUP_ENABLED: bool = True
    GATEKEEPER_DEDUP_WINDOW_SECONDS: int = 900

    @property
    def gatekeeper_settings(self) -> Dict[str, Any]:
        """Get gatekeeper settings as dict for ActionGatekeeper.apply_settings()."""
        return {
            "cooldown_minutes": {
                "restart": self.GATEKEEPER_COOLDOWN_RESTART,
                "stop": self.GATEKEEPER_COOLDOWN_STOP,
                "start": self.GATEKEEPER_COOLDOWN_START,
                "kill": self.GATEKEEPER_COOLDOWN_KILL,
                "run_script": self.GATEKEEPER_COOLDOWN_RUN_SCRIPT,
            },
            "backoff_delays": [2, 5, 15],  # Fixed delays in minutes
            "max_backoff_minutes": self.GATEKEEPER_MAX_BACKOFF_MINUTES,
            "disable_after_failures": self.GATEKEEPER_DISABLE_AFTER_FAILURES,
            "disable_duration_minutes": self.GATEKEEPER_DISABLE_DURATION_MINUTES,
            "max_actions_per_rule_per_hour": self.GATEKEEPER_MAX_ACTIONS_PER_RULE_PER_HOUR,
            "max_actions_per_container_per_hour": self.GATEKEEPER_MAX_ACTIONS_PER_CONTAINER_PER_HOUR,
            "verification_delay_seconds": self.GATEKEEPER_VERIFICATION_DELAY_SECONDS,
            "trigger_suppression_enabled": self.GATEKEEPER_TRIGGER_SUPPRESSION_ENABLED,
            "trigger_suppression_minutes": self.GATEKEEPER_TRIGGER_SUPPRESSION_MINUTES,
            "trigger_suppression_actions": [
                value.strip()
                for value in self.GATEKEEPER_TRIGGER_SUPPRESSION_ACTIONS.split(",")
                if value.strip()
            ],
            "trigger_suppression_rule_types": [
                value.strip()
                for value in self.GATEKEEPER_TRIGGER_SUPPRESSION_RULE_TYPES.split(",")
                if value.strip()
            ],
            "dedup_enabled": self.GATEKEEPER_DEDUP_ENABLED,
            "dedup_window_seconds": max(1, self.GATEKEEPER_DEDUP_WINDOW_SECONDS),
        }

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )


settings = Settings()
