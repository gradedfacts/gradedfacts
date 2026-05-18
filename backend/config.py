from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./gradedfacts.db"
    anthropic_api_key: str = ""
    mistral_api_key: str = ""
    brave_api_key: str = ""
    searxng_url: str = ""
    rate_limit_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        # SQLAlchemy 2 requires postgresql:// — Jelastic/Heroku supply postgres://
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v


settings = Settings()
