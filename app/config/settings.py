"""Application configuration using Pydantic Settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "AI Service"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # MongoDB
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "ai_service"

    # JWT
    JWT_SECRET_KEY: str  # Required, no default for security
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_DAYS: int = 3

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Internal API
    INTERNAL_API_KEY: str  # API key for Cloud Scheduler

    # Google Sheets
    GOOGLE_SERVICE_ACCOUNT_JSON: str  # Service account credentials JSON
    GOOGLE_SERVICE_ACCOUNT_EMAIL: str  # Email to display to users

    # Sheet Crawler
    SHEET_SYNC_QUEUE_NAME: str = "sheet_sync_tasks"

    # OpenAI
    OPENAI_API_KEY: str  # Required for LLM operations
    OPENAI_API_BASE: str | None = None  # Optional custom API base URL

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]  # Frontend origins


@lru_cache
def get_settings() -> Settings:
    """Dependency injection function for settings.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()
