from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field(default="development", validation_alias="ENV")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/karigar_app",
    )

    jwt_secret: str = Field(default="change-me-in-production")
    jwt_issuer: str = Field(default="karigar")
    jwt_token_ttl_days: int = Field(default=30)

    otp_expiry_seconds: int = Field(default=300)
    otp_max_attempts: int = Field(default=3)
    otp_code_length: int = Field(default=6)

    pii_encryption_key: str = Field(default="dev-encryption-key-change-me")
    phone_hash_pepper: str = Field(default="dev-phone-pepper-change-me")

    notifications_push_enabled: bool = Field(default=False)
    notifications_push_provider: str = Field(default="stub")
    notifications_batch_size: int = Field(default=100)
    notifications_max_attempts: int = Field(default=3)
    notifications_retry_seconds: int = Field(default=300)
    notifications_worker_enabled: bool = Field(default=False)
    notifications_worker_interval_seconds: int = Field(default=15)

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:8081",
            "http://localhost:19006",
            "http://localhost:3000",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ]
    )
    cors_origin_regex: str | None = Field(
        default=r"^http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+):\d+$"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
