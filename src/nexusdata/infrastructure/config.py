"""Configuração central via Pydantic Settings.

Todos os segredos são `SecretStr` — nunca são logados nem serializados por
acidente. Em produção, um validador impede subir com segredo fraco/padrão.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "staging", "production"]

# Valores default de desenvolvimento — proibidos em produção.
_DEV_SECRET_SENTINEL = "CHANGE_ME_dev_only_secret_do_not_use_in_production_00000000"  # noqa: S105
_DEFAULT_DEV_PASSWORD = "nexus_dev_password"  # noqa: S105
_MIN_SECRET_LEN = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NEXUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---
    environment: Environment = "local"
    debug: bool = False
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"  # noqa: S104 - bind explícito em container
    api_port: int = 8000
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- Segurança (JWT) ---
    jwt_secret_key: SecretStr = SecretStr(_DEV_SECRET_SENTINEL)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # --- PostgreSQL ---
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "nexus"
    postgres_password: SecretStr = SecretStr("nexus_dev_password")
    postgres_db: str = "nexusdata"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # --- Redis ---
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: SecretStr = SecretStr("")

    # --- RabbitMQ ---
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "nexus"
    rabbitmq_password: SecretStr = SecretStr("nexus_dev_password")
    rabbitmq_vhost: str = "/"

    # --- Rate limiting ---
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # --- Limite de corpo da requisição (anti-DoS de memória) ---
    max_request_body_bytes: int = 2_097_152  # 2 MiB

    # --- Idempotência ---
    idempotency_ttl_seconds: int = 86_400

    # --- Webhooks ---
    webhook_timeout_seconds: float = 10.0
    webhook_max_retries: int = 5

    # --- Processamento / IA ---
    ai_provider: Literal["mock", "claude", "openai"] = "mock"
    ai_api_key: SecretStr = SecretStr("")
    ai_max_retries: int = 3
    circuit_breaker_fail_threshold: int = 5
    circuit_breaker_reset_seconds: float = 30.0

    # --- Qdrant ---
    qdrant_enabled: bool = False
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    # --- Observabilidade ---
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    metrics_enabled: bool = True

    # ------------------------------------------------------------------ #
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def database_url(self) -> str:
        pwd = self.postgres_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{pwd}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """URL síncrona (psycopg) — usada só por ferramentas se necessário."""
        pwd = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{pwd}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        pwd = self.redis_password.get_secret_value()
        auth = f":{pwd}@" if pwd else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def celery_broker_url(self) -> str:
        pwd = self.rabbitmq_password.get_secret_value()
        return (
            f"amqp://{self.rabbitmq_user}:{pwd}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/{self.rabbitmq_vhost}"
        )

    @property
    def celery_result_backend(self) -> str:
        # Backend de resultado no Redis (DB isolado do cache).
        pwd = self.redis_password.get_secret_value()
        auth = f":{pwd}@" if pwd else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/1"

    @model_validator(mode="after")
    def _enforce_production_hardening(self) -> Settings:
        if not self.is_production:
            return self
        secret = self.jwt_secret_key.get_secret_value()
        if secret == _DEV_SECRET_SENTINEL:
            raise ValueError("NEXUS_JWT_SECRET_KEY não pode usar o valor padrão em produção")
        if len(secret) < _MIN_SECRET_LEN:
            raise ValueError(f"NEXUS_JWT_SECRET_KEY deve ter >= {_MIN_SECRET_LEN} caracteres")
        if self.debug:
            raise ValueError("NEXUS_DEBUG deve ser false em produção")
        if self.postgres_password.get_secret_value() == _DEFAULT_DEV_PASSWORD:
            raise ValueError("NEXUS_POSTGRES_PASSWORD não pode usar o default em produção")
        if self.rabbitmq_password.get_secret_value() == _DEFAULT_DEV_PASSWORD:
            raise ValueError("NEXUS_RABBITMQ_PASSWORD não pode usar o default em produção")
        if self.ai_provider != "mock" and not self.ai_api_key.get_secret_value():
            raise ValueError(f"NEXUS_AI_API_KEY é obrigatório para o provider '{self.ai_provider}'")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings em cache (singleton por processo)."""
    return Settings()
