from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "production"
    API_BASE_URL: str = "/unicron/api"
    ROOT_PATH: str = "/unicron"
    CENTRAL_AUTH_BASE_URL: str = ""
    CENTRAL_AUTH_VERIFY_TLS: bool = True
    CENTRAL_AUTH_SESSION_CACHE_ENABLED: bool = True
    CENTRAL_AUTH_SESSION_CACHE_TTL_SECONDS: int = 10
    CENTRAL_AUTH_SESSION_CACHE_PREFIX: str = "unicron:auth:central_auth_session"
    CENTRAL_AUTH_SESSION_L1_CACHE_ENABLED: bool = True
    CENTRAL_AUTH_SESSION_L1_CACHE_TTL_SECONDS: int = 2
    CENTRAL_AUTH_SESSION_L1_STALE_GRACE_SECONDS: int = 2
    # Canonical browser origin allowlist for HTTP + Socket.IO.
    # Comma-separated origins, e.g. https://app.example.com,https://admin.example.com
    # When set, these origins are protected and cannot be removed from the UI.
    UNICRON_ALLOWED_ORIGINS: str = ""
    UNICRON_ALLOW_UI_ORIGIN_ADDITIONS: bool = True
    CORS_ORIGINS: str = ""
    CORS_ORIGIN_REGEX: Optional[str] = None
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_MAX_AGE: int = 600
    ORIGIN_POLICY_INVALIDATION_CHANNEL: str = "unicron:origin-policy:invalidate"
    UNICRON_CENTRAL_FQDN: str = "unicron.central"
    UNICRON_CENTRAL_PORT: int = 443
    UNICRON_CENTRAL_MTLS_PORT: int = 8443
    UNICRON_PUBLIC_CENTRAL_MTLS_PORT: Optional[int] = None
    UNICRON_DATA_DIR: str = "/var/lib/unicron"
    POSTGRES_USER: str = "unicron"
    POSTGRES_PASSWORD: str = "unicron_password"
    POSTGRES_DB: str = "unicron_db"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_POOL_SIZE: int = 10
    POSTGRES_MAX_OVERFLOW: int = 20
    POSTGRES_POOL_TIMEOUT: int = 30
    POSTGRES_POOL_RECYCLE: int = 3600

    # Redis configuration
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_DEDUP_TTL_SECONDS: int = 300  # 5 min deduplication window
    REDIS_RATE_LIMIT_WINDOW_SECONDS: int = 60  # 1 min rate limit window

    # Redis Streams configuration
    REDIS_STREAM_ALERTS: str = "unicron:alerts"
    REDIS_STREAM_NOTIFICATIONS: str = "unicron:notifications"
    REDIS_CONSUMER_GROUP: str = "alerting-workers"
    REDIS_STREAM_MAX_LEN: int = 100000  # Max stream length before trimming

    # Redis Streams for log pipeline (real-time rule evaluation)
    REDIS_STREAM_LOGS: str = "unicron:logs"
    REDIS_LOG_STREAM_MAX_LEN: int = 500000  # ~500K entries (~5 min at 50K logs/sec)

    # Redis Stream for decoupled log ingest fanout (HTTP ingest -> queue -> workers)
    REDIS_STREAM_LOG_INGEST: str = "unicron:ingest:logs"
    REDIS_LOG_INGEST_CONSUMER_GROUP: str = "central-log-fanout"
    REDIS_LOG_INGEST_BATCH_SIZE: int = 100
    REDIS_LOG_INGEST_BLOCK_MS: int = 1000
    REDIS_LOG_INGEST_STREAM_MAX_LEN: int = 500000
    REDIS_LOG_INGEST_RECLAIM_ENABLED: bool = True
    REDIS_LOG_INGEST_RECLAIM_IDLE_MS: int = 60000
    REDIS_LOG_INGEST_RECLAIM_BATCH_SIZE: int = 100
    REDIS_LOG_INGEST_RECLAIM_INTERVAL_SECONDS: int = 5
    REALTIME_RULE_INDEX_VERSION_KEY: str = "unicron:alert-engine:rule-index:version"
    REALTIME_RULE_INDEX_VERSION_CHECK_SECONDS: float = 1.0

    # Redis Streams for container registry updates (monitoring state changes)
    REDIS_STREAM_CONTAINERS: str = "unicron:containers"
    REDIS_CONTAINER_STREAM_MAX_LEN: int = 10000

    # Redis Streams for container lifecycle events (stability rule evaluation)
    REDIS_STREAM_EVENTS: str = "unicron:events"
    REDIS_EVENT_STREAM_MAX_LEN: int = 10000  # Container events are low-frequency
    AGENT_COMMAND_CHANNEL: str = "unicron:agent:commands"
    AGENT_REVOCATION_CHANNEL: str = "unicron:agent:revocations"
    AGENT_REVOKED_SET_KEY: str = "unicron:agent:revoked"
    AGENT_REVOKED_CERT_FINGERPRINT_SET_KEY: str = "unicron:agent:revoked:cert:fingerprint"
    AGENT_REVOKED_CERT_SERIAL_SET_KEY: str = "unicron:agent:revoked:cert:serial"
    AGENT_CERT_METADATA_KEY_PREFIX: str = "unicron:agent:cert:last:"
    AGENT_HEARTBEAT_TIMEOUT_SECONDS: int = 60
    AGENT_HEARTBEAT_MONITOR_INTERVAL_SECONDS: int = 10
    REMOTE_AGENT_IMAGE: str = "logforge/unicron-agent:latest"
    LOCAL_AGENT_CENTRAL_URL: str = "https://traefik/unicron"
    LOCAL_AGENT_DOCKER_NETWORK: str = "unicron-network"
    INGEST_LOG_COUNTER_KEY: str = "unicron:ingest:logs:counters"
    INTERNAL_LOGS_MAX_BODY_BYTES: int = 2 * 1024 * 1024
    INTERNAL_LOGS_HARD_MAX_BODY_BYTES: int = 16 * 1024 * 1024
    MONITORING_METRICS_KEY: str = "unicron:monitoring:metrics"
    MONITORING_RECONCILE_ENABLED: bool = True
    MONITORING_RECONCILE_INTERVAL_SECONDS: int = 60
    MONITORING_RECONCILE_BATCH_SIZE: int = 1000
    HOST_FLAP_WINDOW_SECONDS: int = 120

    # Socket.IO Redis adapter
    SOCKETIO_REDIS_URL: str = ""
    # Rollout/operability kill switches.
    ENABLE_LOG_FANOUT_WORKER: bool = True
    ENABLE_CONTAINER_WS_RELAY: bool = True
    ENABLE_ALERT_WS_RELAY: bool = True
    ENABLE_AGENT_HEARTBEAT_MONITOR: bool = True
    ENABLE_SCHEDULER: bool = True
    ROOT_CA: str = "/ca/certs/root_ca.crt"
    CA_URL: str = "https://unicron-stepca:9000"
    RA_URL: str = "https://unicron-stepca-ra:9100"
    # RA JWK private key used to mint short-lived signing tokens for CSR signing.
    # Production compose mounts only this key, not the full stepca-data volume.
    RA_PROVISIONER_KEY: str = "/ca/ra/ra.jwk.json"
    RA_PROVISIONER_PASSWORD_FILE: str = "/ca/secrets/ra.jwk.pw"
    VLOGS_BASE: str = "http://unicron-victoria-logs:9428"
    VMETRICS_BASE: str = "http://unicron-victoria-metrics:8428"
    PING_INTERVAL: int = 60
    HERALD_STALE_GRACE: int = 3
    CLEANUP_INTERVAL_SECONDS: int = 3600  # 1 hour
    TOKEN_EXPIRY_SECONDS: int = 18000  # 5 hours
    HERALD_CORS_ORIGINS: str = ""
    HERALD_CORS_ORIGIN_REGEX: str = ""
    HERALD_CORS_ALLOW_CREDENTIALS: bool = True
    HERALD_CORS_MAX_AGE: int = 600

    # Internal API configuration (for service-to-service communication)
    INTERNAL_API_SECRET: str = ""  # Shared secret for alert-engine/notifier

    # Alert-engine service URL (for proxying acknowledge requests)
    ALERT_ENGINE_URL: str = "http://unicron-alert-engine:8000"
    APPLIANCE_UPDATER_URL: str = "http://127.0.0.1:7078"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")


settings = Settings()
