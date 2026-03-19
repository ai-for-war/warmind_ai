"""Application configuration using Pydantic Settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

NOVA3_MONOLINGUAL_LANGUAGE_CODES = (
    "ar",
    "ar-ae",
    "ar-sa",
    "ar-qa",
    "ar-kw",
    "ar-sy",
    "ar-lb",
    "ar-ps",
    "ar-jo",
    "ar-eg",
    "ar-sd",
    "ar-td",
    "ar-ma",
    "ar-dz",
    "ar-tn",
    "ar-iq",
    "ar-ir",
    "be",
    "bn",
    "bs",
    "bg",
    "ca",
    "zh-hk",
    "hr",
    "cs",
    "da",
    "da-dk",
    "nl",
    "en",
    "en-us",
    "en-au",
    "en-gb",
    "en-in",
    "en-nz",
    "et",
    "fi",
    "nl-be",
    "fr",
    "fr-ca",
    "de",
    "de-ch",
    "el",
    "he",
    "hi",
    "hu",
    "id",
    "it",
    "ja",
    "kn",
    "ko",
    "ko-kr",
    "lv",
    "lt",
    "mk",
    "ms",
    "mr",
    "no",
    "fa",
    "pl",
    "pt",
    "pt-br",
    "pt-pt",
    "ro",
    "ru",
    "sr",
    "sk",
    "sl",
    "es",
    "es-419",
    "sv",
    "sv-se",
    "tl",
    "ta",
    "te",
    "th",
    "th-th",
    "tr",
    "uk",
    "ur",
    "vi",
)


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
    IMAGE_GENERATION_QUEUE_NAME: str = "image_generation_tasks"
    IMAGE_GENERATION_MAX_CONCURRENCY: int = 4

    # OpenAI
    OPENAI_API_KEY: str  # Required for LLM operations
    OPENAI_API_BASE: str | None = None  # Optional custom API base URL

    # MiniMax
    MINIMAX_API_KEY: str

    # Deepgram
    DEEPGRAM_API_KEY: str
    DEEPGRAM_MODEL: str = "nova-3"
    DEEPGRAM_ENDPOINTING_MS: int = 400
    DEEPGRAM_UTTERANCE_END_MS: int = 1000
    DEEPGRAM_KEEPALIVE_INTERVAL_SECONDS: int = 5

    # Interview STT
    INTERVIEW_STT_CHANNELS: int = 2
    INTERVIEW_STT_MULTICHANNEL: bool = True
    INTERVIEW_STT_ENDPOINTING_MS: int = 400
    INTERVIEW_STT_UTTERANCE_END_MS: int = 1000
    INTERVIEW_STT_KEEPALIVE_INTERVAL_SECONDS: int = 5
    INTERVIEW_TURN_CLOSE_GRACE_MS: int = 300

    # Meeting STT
    MEETING_STT_CHANNELS: int = 1
    MEETING_STT_MULTICHANNEL: bool = False
    MEETING_STT_ENDPOINTING_MS: int = 400
    MEETING_STT_UTTERANCE_END_MS: int = 1000
    MEETING_STT_KEEPALIVE_INTERVAL_SECONDS: int = 5
    # Stored in lowercase to match request payload normalization before validation.
    MEETING_SUPPORTED_LANGUAGES: list[str] = list(NOVA3_MONOLINGUAL_LANGUAGE_CODES)

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]  # Frontend origins


@lru_cache
def get_settings() -> Settings:
    """Dependency injection function for settings.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()
