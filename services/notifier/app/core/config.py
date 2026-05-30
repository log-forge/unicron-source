"""Configuration settings for notifier service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Notifier service configuration."""

    # Service identification
    ENVIRONMENT: str = "production"
    SERVICE_NAME: str = "notifier"
    SERVICE_VERSION: str = "1.0.0"
    ROOT_PATH: str = "/notifier"
    API_PREFIX: str = "/api"

    # Central connection
    CENTRAL_URL: str = "http://unicron-central:8000"
    CENTRAL_VERIFY_TLS: bool = True
    CENTRAL_AUTH_BASE_URL: str = "http://central-auth:3020"
    CENTRAL_AUTH_VERIFY_TLS: bool = True

    # PostgreSQL (shared with Central - notifications schema)
    POSTGRES_USER: str = "unicron"
    POSTGRES_PASSWORD: str = "unicron_password"
    POSTGRES_DB: str = "unicron_db"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50
    # Keep read timeout above XREADGROUP BLOCK to avoid idle long-poll false errors.
    REDIS_SOCKET_TIMEOUT_SECONDS: float = 10.0
    REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS: float = 5.0

    # Redis Streams consumer (for alert consumption)
    REDIS_STREAM_ALERTS: str = "unicron:alerts"
    REDIS_CONSUMER_GROUP: str = "notifier-workers"
    REDIS_CONSUMER_BATCH_SIZE: int = 10
    REDIS_CONSUMER_CONCURRENCY: int = 10
    REDIS_CONSUMER_BLOCK_MS: int = 5000
    REDIS_RECLAIM_ENABLED: bool = True
    REDIS_RECLAIM_IDLE_MS: int = 60000
    REDIS_RECLAIM_BATCH_SIZE: int = 50
    REDIS_RECLAIM_INTERVAL_SECONDS: int = 5
    REDIS_DLQ_ENABLED: bool = True
    REDIS_DLQ_MAX_LEN: int = 50000
    REDIS_STREAM_ALERTS_DLQ: str = "unicron:alerts:dlq"
    REDIS_MAX_DELIVERY_ATTEMPTS: int = 5
    REDIS_ATTEMPT_TTL_SECONDS: int = 86400
    NOTIFIER_IDEMPOTENCY_ENABLED: bool = True
    NOTIFIER_IDEMPOTENCY_TTL_SECONDS: int = 86400
    NOTIFIER_RATE_LIMIT_ENABLED: bool = True
    NOTIFIER_RATE_LIMIT_WINDOW_SECONDS: int = 60
    NOTIFIER_RATE_LIMIT_GLOBAL_PER_WINDOW: int = 2000
    NOTIFIER_RATE_LIMIT_CHANNEL_TYPE_PER_WINDOW: int = 500
    NOTIFIER_RATE_LIMIT_CHANNEL_PER_WINDOW: int = 120
    STREAM_PENDING_WARN: int = 500
    STREAM_PENDING_CRITICAL: int = 2000
    STREAM_LAG_WARN: int = 1000
    STREAM_LAG_CRITICAL: int = 5000
    STREAM_DLQ_WARN: int = 10
    STREAM_DLQ_CRITICAL: int = 100

    # Celery (for notification task queue)
    CELERY_BROKER_URL: str = ""  # Defaults to REDIS_URL if empty

    # CORS
    CORS_ORIGINS: str = ""
    CORS_ALLOW_CREDENTIALS: bool = True

    # Encryption
    ENCRYPTION_KEY_PATH: str = "/data/encryption.key"

    # Logging
    LOG_LEVEL: str = "INFO"

    # AI / Ollama configuration
    OLLAMA_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "gemma3:1b"
    AI_ENABLED: bool = False  # Off by default -- explicit opt-in
    AI_TIMEOUT: int = 15  # Seconds for Ollama API call
    AI_CACHE_TTL: int = 3600  # Seconds to cache AI results (1 hour)
    AI_DEFAULT_PREPROMPT: str = (
        "You are an AI specialized in analyzing technical documents and logs. "
        "Extract and present only the useful details in a clear, concise format. "
        "Provide the answer directly without any additional text, greetings, or commentary."
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    @property
    def celery_broker(self) -> str:
        """Return Celery broker URL, defaulting to Redis URL."""
        return self.CELERY_BROKER_URL or self.REDIS_URL


settings = Settings()
