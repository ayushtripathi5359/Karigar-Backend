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

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:8081",
            "http://localhost:19006",
            "http://localhost:3000",
        ]
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
