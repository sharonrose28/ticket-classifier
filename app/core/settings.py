"""Validated environment configuration for API and worker processes."""

from functools import lru_cache

from decimal import Decimal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_name: str = "AI Support Ticket Classifier"
    app_env: str = Field(default="local", validation_alias=AliasChoices("APP_ENV", "ENVIRONMENT"))
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ticket_classifier"
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)
    database_pool_recycle_seconds: int = Field(default=1800, ge=60)
    database_pool_timeout_seconds: float = Field(default=30.0, gt=0, le=120)

    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_task_max_retries: int = Field(default=3, ge=0, le=10)
    background_processing_enabled: bool = True

    openai_api_key: SecretStr | None = None
    openai_primary_model: str = "gpt-4.1"
    openai_fallback_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    openai_max_attempts: int = Field(default=5, ge=1, le=5)
    openai_backoff_base_seconds: float = Field(default=0.5, gt=0, le=10)
    openai_backoff_max_seconds: float = Field(default=8.0, gt=0, le=60)
    openai_retry_after_max_seconds: float = Field(default=60.0, gt=0, le=300)
    openai_primary_input_cost_per_million: Decimal = Field(default=Decimal("2.00"), ge=0)
    openai_primary_cached_input_cost_per_million: Decimal = Field(default=Decimal("0.50"), ge=0)
    openai_primary_output_cost_per_million: Decimal = Field(default=Decimal("8.00"), ge=0)
    openai_fallback_input_cost_per_million: Decimal = Field(default=Decimal("0.40"), ge=0)
    openai_fallback_cached_input_cost_per_million: Decimal = Field(default=Decimal("0.10"), ge=0)
    openai_fallback_output_cost_per_million: Decimal = Field(default=Decimal("1.60"), ge=0)

    cors_allowed_origins: list[str] = Field(default_factory=list)
    cors_allow_credentials: bool = False
    rate_limit_enabled: bool = True
    rate_limit_requests: int = Field(default=60, ge=1, le=10000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_fail_open: bool = True
    ticket_cache_ttl_seconds: int = Field(default=300, ge=1, le=3600)
    ticket_batch_max_size: int = Field(default=100, ge=1, le=1000)
    celery_worker_concurrency: int = Field(default=4, ge=1, le=64)
    celery_worker_prefetch_multiplier: int = Field(default=1, ge=1, le=16)
    shutdown_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    secret_key: SecretStr = SecretStr("development-only-change-me")
    jwt_secret_key: SecretStr = SecretStr("development-only-change-me")
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = Field(
        default=60,
        ge=5,
        le=1440,
        validation_alias=AliasChoices("JWT_ACCESS_TOKEN_MINUTES", "ACCESS_TOKEN_EXPIRE_MINUTES"),
    )
    refresh_token_expire_days: int = Field(default=7, ge=1, le=90)
    auth_cookie_name: str = "supportflow_access"
    auth_cookie_secure: bool = False

    @field_validator("openai_primary_model", "openai_fallback_model")
    @classmethod
    def model_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("OpenAI model names must not be blank")
        return value.strip()

    @field_validator("database_url")
    @classmethod
    def normalize_async_database_url(cls, value: str) -> str:
        """Railway exposes a standard PostgreSQL URL; the app requires asyncpg."""

        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        return value

    @field_validator("app_env")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.cors_allow_credentials and "*" in self.cors_allowed_origins:
            raise ValueError("Wildcard CORS origins cannot be used with credentials")
        if self.app_env == "production" and self.debug:
            raise ValueError("DEBUG must be false in production")
        if self.app_env == "production" and self.jwt_secret_key.get_secret_value() == "development-only-change-me":
            raise ValueError("JWT_SECRET_KEY must be configured in production")
        if self.app_env == "production" and self.secret_key.get_secret_value() == "development-only-change-me":
            raise ValueError("SECRET_KEY must be configured in production")
        if self.app_env == "production":
            jwt_secret = self.jwt_secret_key.get_secret_value()
            app_secret = self.secret_key.get_secret_value()
            if len(jwt_secret) < 32 or len(app_secret) < 32:
                raise ValueError("Production secrets must contain at least 32 characters")
            if jwt_secret == app_secret:
                raise ValueError("SECRET_KEY and JWT_SECRET_KEY must be independent")
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
