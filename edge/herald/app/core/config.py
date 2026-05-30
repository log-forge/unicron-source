import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DOCKER_ENDPOINT: str = "unix:///var/run/docker.sock"
    HOST_PROC: str = "/host/proc"
    HOST_SYS: str = "/host/sys"
    HOST_ROOT: str = "/host/root"
    ENVIRONMENT: str = "production"
    PING_INTERVAL: int = 60  # 1 minute
    INVENTORY_INTERVAL: int = 300  # 5 minutes
    HERALD_ID: str = ""
    HERALD_NAME: str = ""
    HERALD_PORT: int = 9443
    CENTRAL_URL: str = ""
    CENTRAL_MTLS_URL: str = ""
    UNICRON_CENTRAL_FQDN: str = ""
    HERALD_ENROLL_TOKEN: str = ""
    CA_FINGERPRINT: str = ""
    HERALD_CERT_SUBJECTS: str = ""
    HERALD_CERT_NOT_AFTER_SECONDS: int = 43200
    HERALD_CERT_RENEW_EXPIRES_IN_SECONDS: int = 3600
    API_BASE_URL: str = "/unicron/api"
    HERALD_CA_ROOT: str = "/herald-data/certs/root_ca.crt"
    HERALD_CERT: str = "/herald-data/certs/unicron-herald-leaf.crt"
    HERALD_KEY: str = "/herald-data/certs/unicron-herald-leaf.key"
    SIO_PATH: str = "/unicron/api/socket.io"
    HERALD_CORS_ORIGINS: str = ""
    HERALD_CORS_ORIGIN_REGEX: str = ""
    HERALD_CORS_ALLOW_CREDENTIALS: bool = True
    HERALD_CORS_MAX_AGE: int = 600

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
