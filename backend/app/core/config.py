from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = (BASE_DIR / "data" / "legado_hub.sqlite3").as_posix()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    ENV: str = Field(default="dev", alias="APP_ENV")
    APP_NAME: str = "LegadoHub API"
    APP_VERSION: str = "3.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True
    RATE_LIMIT_PER_MINUTE: int = 120
    REPO_BACKEND: str = "sqlite"
    DB_PATH: str = DEFAULT_DB_PATH
    SECRET_KEY: str | None = Field(default=None, min_length=16)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    ALLOWED_ORIGINS: list[str] = ["http://127.0.0.1:3000", "http://localhost:3000"]
    LLM_API_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4.1-mini"
    LLM_PROVIDER_NAME: str = "local-llm"
    EVENT_DELIVERY_WORKER_ENABLED: bool = True
    EVENT_DELIVERY_POLL_SECONDS: float = 5.0
    EVENT_DELIVERY_BATCH_SIZE: int = 20
    SOURCE_BUILD_WORKER_ENABLED: bool = True
    SOURCE_BUILD_POLL_SECONDS: float = 5.0
    SOURCE_BUILD_BATCH_SIZE: int = 1
    SOURCE_HEALTH_PROBE_WORKER_ENABLED: bool = True
    SOURCE_HEALTH_PROBE_BATCH_SIZE: int = 10
    INTERACTIVE_BROWSER_PROFILE_ROOT: str = "/tmp/legado-hub-browser-sessions"
    INTERACTIVE_BROWSER_CHROMIUM_PATH: str = "chromium-browser"
    INTERACTIVE_BROWSER_XVFB_PATH: str = "Xvfb"
    INTERACTIVE_BROWSER_X11VNC_PATH: str = "x11vnc"
    INTERACTIVE_BROWSER_WEBSOCKIFY_PATH: str = "websockify"

    @field_validator("ENV")
    @classmethod
    def validate_env(cls, value: str) -> str:
        if value not in {"dev", "test", "prod"}:
            raise ValueError("APP_ENV must be one of dev/test/prod")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    if settings.ENV == "dev" and not settings.SECRET_KEY:
        object.__setattr__(settings, "SECRET_KEY", "dev-secret-key-32-bytes-minimum")
    if settings.ENV in {"test", "prod"} and not settings.SECRET_KEY:
        raise ValueError("SECRET_KEY is required")
    return settings


settings = get_settings()
