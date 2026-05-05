from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field(default="development", validation_alias="ENV")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/karigar",
    )
    stack_project_id: str = Field(default="set-me-in-env")
    stack_api_base_url: str = "https://api.stack-auth.com"

    otp_secret: str = Field(default="change-me-in-production")
    otp_expiry_seconds: int = Field(default=300)
    otp_max_attempts: int = Field(default=3)
    otp_token_ttl_days: int = Field(default=30)

    @property
    def stack_api_base(self) -> str:
        return self.stack_api_base_url.rstrip("/")

    @property
    def stack_jwks_url(self) -> str:
        return f"{self.stack_api_base}/api/v1/projects/{self.stack_project_id}/.well-known/jwks.json"

    @property
    def stack_issuer_user(self) -> str:
        return f"{self.stack_api_base}/api/v1/projects/{self.stack_project_id}"

    @property
    def stack_issuer_anonymous(self) -> str:
        return f"{self.stack_api_base}/api/v1/projects-anonymous-users/{self.stack_project_id}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
