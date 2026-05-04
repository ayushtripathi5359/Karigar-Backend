from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/karigar",
    )
    stack_project_id: str = Field(default="set-me-in-env")
    stack_api_base_url: str = "https://api.stack-auth.com"

    @property
    def stack_api_base(self) -> str:
        u = self.stack_api_base_url.rstrip("/")
        return u

    @property
    def stack_jwks_url(self) -> str:
        return f"{self.stack_api_base}/api/v1/projects/{self.stack_project_id}/.well-known/jwks.json"

    @property
    def stack_issuer_user(self) -> str:
        return f"{self.stack_api_base}/api/v1/projects/{self.stack_project_id}"

    @property
    def stack_issuer_anonymous(self) -> str:
        return f"{self.stack_api_base}/api/v1/projects-anonymous-users/{self.stack_project_id}"


def get_settings() -> Settings:
    return Settings()
